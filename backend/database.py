import os
import sqlite3
import logging
import json
from abc import ABC, abstractmethod
from contextlib import contextmanager
from typing import List, Dict, Any, Optional

logger = logging.getLogger("hermes.database")

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "hermes.db")

# ---------------------------------------------------------------------------
# WAL-mode connection factory (SQLite)
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    """Open a SQLite connection with WAL journal mode and safe PRAGMA settings.

    WAL (Write-Ahead Logging) solves concurrent-write locking errors:
    - Multiple readers never block writers
    - A single writer never blocks readers
    - busy_timeout prevents 'database is locked' exceptions under load
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")       # enable WAL mode
    conn.execute("PRAGMA synchronous=NORMAL")      # safe & fast (vs FULL)
    conn.execute("PRAGMA busy_timeout=5000")       # wait 5s before giving up
    conn.execute("PRAGMA foreign_keys=ON")         # enforce FK constraints
    return conn


# ---------------------------------------------------------------------------
# Database Backend Abstraction (OSS-friendly: swap SQLite ↔ PostgreSQL via .env)
# ---------------------------------------------------------------------------

class DatabaseBackend(ABC):
    """Abstract interface for the persistence layer.
    Override to add a new backend (e.g. MySQL, DuckDB) without touching callers.
    """

    @abstractmethod
    @contextmanager
    def connect(self):
        """Yield a DB-API 2.0 compatible connection (auto-commit/close on exit)."""
        ...

    def execute(self, sql: str, params: tuple = ()) -> list:
        """Execute a single statement and return all rows."""
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.fetchall()

    def executemany(self, sql: str, params_list: list) -> None:
        """Execute a statement for multiple parameter tuples."""
        with self.connect() as conn:
            cur = conn.cursor()
            cur.executemany(sql, params_list)
            conn.commit()

    def lastrowid(self, sql: str, params: tuple = ()) -> Optional[int]:
        """Execute an INSERT and return the last inserted row id."""
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.lastrowid

    def rowcount(self, sql: str, params: tuple = ()) -> int:
        """Execute a DELETE/UPDATE and return affected row count."""
        with self.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
            return cur.rowcount


class SQLiteBackend(DatabaseBackend):
    """Default backend: SQLite with WAL mode enabled."""

    @contextmanager
    def connect(self):
        conn = _get_conn()
        try:
            yield conn
        finally:
            conn.close()


class PostgresBackend(DatabaseBackend):
    """Optional PostgreSQL backend — activated via DATABASE_URL env var.

    Requires: pip install sqlalchemy psycopg2-binary
    (or: uv add sqlalchemy psycopg2-binary)
    """

    def __init__(self, url: str):
        try:
            from sqlalchemy import create_engine, text  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "PostgreSQL backend requires SQLAlchemy and psycopg2.\n"
                "Install with: uv add sqlalchemy psycopg2-binary"
            ) from e
        from sqlalchemy import create_engine
        self._engine = create_engine(url, pool_pre_ping=True)

    @contextmanager
    def connect(self):
        """Yield a psycopg2 raw connection from the SQLAlchemy pool."""
        raw_conn = self._engine.raw_connection()
        try:
            yield raw_conn
            raw_conn.commit()
        except Exception:
            raw_conn.rollback()
            raise
        finally:
            raw_conn.close()


def _create_backend() -> DatabaseBackend:
    """Factory: read DATABASE_URL from environment and return the right backend.

    Configuration (in .env):
        # SQLite (default — no config needed, WAL enabled automatically)
        # DATABASE_URL=   ← leave blank or omit

        # PostgreSQL (optional):
        # DATABASE_URL=postgresql://user:password@localhost:5432/hermes
    """
    url = os.environ.get("DATABASE_URL", "").strip()
    if url.startswith("postgresql"):
        logger.info("Database backend: PostgreSQL (%s)", url.split("@")[-1])
        return PostgresBackend(url)
    logger.info("Database backend: SQLite with WAL mode (path=%s)", DB_PATH)
    return SQLiteBackend()


# Module-level singleton backend — replaced in tests via monkeypatch
_backend: DatabaseBackend = None  # type: ignore[assignment]


def _get_backend() -> DatabaseBackend:
    """Return the module-level backend, initializing lazily on first call."""
    global _backend
    if _backend is None:
        _backend = _create_backend()
    return _backend

def init_db():
    """Initializes the database and creates the tables if they don't exist."""
    # Ensure data directory exists
    os.makedirs(DB_DIR, exist_ok=True)

    # Reset the backend singleton so the next call re-reads DATABASE_URL.
    # This is important when init_db() is called after env vars are changed
    # (e.g. in tests using tmp_path fixtures).
    global _backend
    _backend = None

    logger.info(f"Initializing database (path={DB_PATH})")
    conn = _get_conn()
    cursor = conn.cursor()
    
    # Create chat messages table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            cost_usd REAL DEFAULT 0.0
        )
    """)
    
    # Create index for fast session lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_session_id ON messages (session_id)
    """)
    
    # Run migration to add cost_usd if table existed before
    try:
        cursor.execute("ALTER TABLE messages ADD COLUMN cost_usd REAL DEFAULT 0.0")
        logger.info("Migrated messages table to include cost_usd column.")
    except sqlite3.OperationalError:
        # Column already exists
        pass
        
    # Create decision logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS decision_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            session_id TEXT NOT NULL,
            model TEXT NOT NULL,
            latency_ms INTEGER NOT NULL,
            success INTEGER NOT NULL,
            error TEXT,
            prompt_tokens_estimate INTEGER NOT NULL,
            user_message TEXT NOT NULL,
            assistant_response TEXT NOT NULL,
            traces TEXT NOT NULL
        )
    """)
    
    # Create activity logs table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,
            source TEXT NOT NULL,
            message TEXT NOT NULL,
            token_cost REAL DEFAULT 0.0
        )
    """)

    # Create subagents table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subagents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            system_prompt TEXT NOT NULL,
            model TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Run migrations for dynamic agent network
    for col, definition in [
        ("agent_type", "TEXT DEFAULT 'agent'"),
        ("parent_id", "TEXT"),
        ("skills", "TEXT DEFAULT ''"),
        ("x", "INTEGER DEFAULT 100"),
        ("y", "INTEGER DEFAULT 100"),
        ("temperature", "REAL DEFAULT 0.7"),
    ]:
        try:
            cursor.execute(f"ALTER TABLE subagents ADD COLUMN {col} {definition}")
            logger.info(f"Added column {col} to subagents table.")
        except sqlite3.OperationalError:
            # Column already exists
            pass

    # Pre-populate default subagents if table is empty
    cursor.execute("SELECT COUNT(*) FROM subagents")
    if cursor.fetchone()[0] == 0:
        logger.info("Pre-populating default subagents.")
        default_model = os.environ.get("LLM_MODEL", "google/gemini-2.5-flash")
        default_agents = [
            (
                "jarvis", "Jarvis (Main)",
                "You are Jarvis, a highly intelligent AI orchestrator. Your job is to understand the user's request and delegate it to the most appropriate sub-agent. Be concise, efficient, and always explain which agent you are routing to.",
                default_model, "orchestrator", None, "", 100, 350
            ),
            (
                "research", "Search Agent",
                "You are a Research Agent. Use web_search to find accurate, up-to-date information. Always cite sources and summarize findings clearly. You can also check weather and fetch RSS news digests.",
                default_model, "agent", "jarvis", "web_search", 450, 100
            ),
            (
                "code", "Code Engineer",
                "You are a Code Engineer. Write clean, well-commented Python code and execute it using the python_sandbox tool. Always show the output and explain what the code does.",
                default_model, "agent", "jarvis", "python_sandbox", 450, 220
            ),
            (
                "analyst", "Data Analyst",
                "You are a Data Analyst. Analyze datasets, compute statistics, and create visualizations using Python (matplotlib, pandas). Always interpret the results and provide actionable insights.",
                default_model, "agent", "jarvis", "python_sandbox", 450, 340
            ),
            (
                "scheduler", "Scheduler",
                "You are a Scheduler Agent. Help the user set timers, reminders, and alarms. Confirm every timer or alarm you set and remind the user of the exact trigger time.",
                default_model, "agent", "jarvis", "timers_alarms", 450, 460
            ),
            (
                "monitor", "Market Monitor",
                "You are a Market Monitor Agent. Track stock prices, crypto rates, and market trends. Use the market_monitor skill to fetch real-time data and set price alerts when requested.",
                default_model, "agent", "jarvis", "market_monitor", 450, 580
            ),
            (
                "planner", "Daily Planner",
                "You are a Daily Planner Agent. Manage the user's calendar and to-do list. Use google_calendar to create and review events, and todoist_sync to manage tasks. Help prioritize and schedule the day effectively.",
                default_model, "agent", "jarvis", "google_calendar,todoist_sync", 450, 700
            ),
            (
                "sysops", "Sys Ops",
                "You are a Sys Ops Agent. Monitor system health (CPU, RAM, disk) and execute shell commands when needed. Always report system status clearly and warn about critical thresholds.",
                default_model, "agent", "jarvis", "shell_execution", 450, 820
            ),
            (
                "football", "Football Analyst",
                "You are a Football Analyst Agent. You have deep knowledge of football (soccer): tactics, player performance, match statistics, league standings, and transfer news. Use web_search to fetch the latest match results, lineups, and news. Provide detailed tactical breakdowns, score predictions, and injury updates. Support all major leagues: Premier League, La Liga, Serie A, Bundesliga, Champions League, and others.",
                default_model, "agent", "jarvis", "web_search", 450, 940
            ),
        ]
        cursor.executemany("""
            INSERT INTO subagents (id, name, system_prompt, model, agent_type, parent_id, skills, x, y, temperature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [t + (0.7,) for t in default_agents])
        logger.info("Successfully seeded default agents.")
    else:
        # Migration: upsert new default agents that don't exist yet,
        # and update existing ones if they still have old prompts.
        upserts = [
            ("jarvis", "Jarvis (Main)",
             "You are Jarvis, a highly intelligent AI orchestrator. Your job is to understand the user's request and delegate it to the most appropriate sub-agent. Be concise, efficient, and always explain which agent you are routing to.",
             "orchestrator", None, "", 100, 350),
            ("research", "Search Agent",
             "You are a Research Agent. Use web_search to find accurate, up-to-date information. Always cite sources and summarize findings clearly. You can also check weather and fetch RSS news digests.",
             "agent", "jarvis", "web_search", 450, 100),
            ("code", "Code Engineer",
             "You are a Code Engineer. Write clean, well-commented Python code and execute it using the python_sandbox tool. Always show the output and explain what the code does.",
             "agent", "jarvis", "python_sandbox", 450, 220),
            ("analyst", "Data Analyst",
             "You are a Data Analyst. Analyze datasets, compute statistics, and create visualizations using Python (matplotlib, pandas). Always interpret the results and provide actionable insights.",
             "agent", "jarvis", "python_sandbox", 450, 340),
            ("scheduler", "Scheduler",
             "You are a Scheduler Agent. Help the user set timers, reminders, and alarms. Confirm every timer or alarm you set and remind the user of the exact trigger time.",
             "agent", "jarvis", "timers_alarms", 450, 460),
            ("monitor", "Market Monitor",
             "You are a Market Monitor Agent. Track stock prices, crypto rates, and market trends. Use the market_monitor skill to fetch real-time data and set price alerts when requested.",
             "agent", "jarvis", "market_monitor", 450, 580),
            ("planner", "Daily Planner",
             "You are a Daily Planner Agent. Manage the user's calendar and to-do list. Use google_calendar to create and review events, and todoist_sync to manage tasks. Help prioritize and schedule the day effectively.",
             "agent", "jarvis", "google_calendar,todoist_sync", 450, 700),
            ("sysops", "Sys Ops",
             "You are a Sys Ops Agent. Monitor system health (CPU, RAM, disk) and execute shell commands when needed. Always report system status clearly and warn about critical thresholds.",
             "agent", "jarvis", "shell_execution", 450, 820),
            ("football", "Football Analyst",
             "You are a Football Analyst Agent. You have deep knowledge of football (soccer): tactics, player performance, match statistics, league standings, and transfer news. Use web_search to fetch the latest match results, lineups, and news. Provide detailed tactical breakdowns, score predictions, and injury updates. Support all major leagues: Premier League, La Liga, Serie A, Bundesliga, Champions League, and others.",
             "agent", "jarvis", "web_search", 450, 940),
        ]
        default_model = os.environ.get("LLM_MODEL", "google/gemini-2.5-flash")
        for agent_id, name, prompt, agent_type, parent_id, skills, x, y in upserts:
            cursor.execute("""
                INSERT INTO subagents (id, name, system_prompt, model, agent_type, parent_id, skills, x, y, temperature)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    system_prompt = excluded.system_prompt,
                    agent_type = excluded.agent_type,
                    parent_id = excluded.parent_id,
                    skills = excluded.skills
                WHERE subagents.system_prompt IN (
                    'Вы — Джарвис, высокоинтеллектуальный персональный ассистент Тони Старка.',
                    'You are Jarvis, a highly intelligent personal assistant to Tony Stark.',
                    'Вы — исследовательский агент. Ищите информацию в интернете с помощью web_search.',
                    'You are a research agent. Search for information on the internet using web_search.',
                    'Вы — Код-Инженер. Пишите и выполняйте Python скрипты.',
                    'You are a Code Engineer. Write and execute Python scripts.',
                    'Вы — Аналитик-Визуализатор. Создавайте графики.',
                    'You are an Analyst-Visualizer. Create charts.'
                )
            """, (agent_id, name, prompt, default_model, agent_type, parent_id, skills, x, y, 0.7))
        logger.info("Checked and migrated default subagents.")

    # Create subagent memory table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subagent_memory (
            subagent_id TEXT NOT NULL,
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (subagent_id, key)
        )
    """)

    # Global app settings (KV store)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    cursor.execute("INSERT OR IGNORE INTO app_settings VALUES ('language', 'ru')")

    # Create session metadata table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session_metadata (
            session_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Migration: add agent_id column to session_metadata if it doesn't exist
    cursor.execute("PRAGMA table_info(session_metadata)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    if "agent_id" not in existing_columns:
        try:
            cursor.execute("ALTER TABLE session_metadata ADD COLUMN agent_id TEXT")
            logger.info("Migrated session_metadata table to include agent_id column.")
        except sqlite3.OperationalError as e:
            logger.error("Failed to migrate session_metadata table to include agent_id column: %s", e)
            raise

    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")

def save_message(session_id: str, role: str, content: str, cost_usd: float = 0.0) -> Optional[int]:
    """Saves a single message to database with cost tracking and returns the new message ID."""
    try:
        return _get_backend().lastrowid(
            "INSERT INTO messages (session_id, role, content, cost_usd) VALUES (?, ?, ?, ?)",
            (session_id, role, content, cost_usd),
        )
    except Exception as e:
        logger.error(f"Error saving message: {e}")
        return None

def get_chat_history(session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves the last N messages for a given chat session, in chronological order."""
    try:
        rows = _get_backend().execute("""
            SELECT id, role, content, cost_usd FROM (
                SELECT id, role, content, cost_usd FROM messages
                WHERE session_id = ?
                ORDER BY id DESC LIMIT ?
            ) ORDER BY id ASC
        """, (session_id, limit))
        return [{"id": r[0], "role": r[1], "content": r[2], "cost_usd": r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Error retrieving chat history: {e}")
        return []

def clear_chat_history(session_id: str):
    """Deletes all messages in the database for a session."""
    try:
        _get_backend().rowcount("DELETE FROM messages WHERE session_id = ?", (session_id,))
        logger.info(f"Cleared database history for session: {session_id}")
    except Exception as e:
        logger.error(f"Error clearing chat history: {e}")

def save_decision_log(log: Dict[str, Any]):
    """Saves a single agent decision log to the database."""
    try:
        _get_backend().execute("""
            INSERT INTO decision_logs (
                timestamp, session_id, model, latency_ms, success,
                error, prompt_tokens_estimate, user_message, assistant_response, traces
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            log["timestamp"],
            log["session_id"],
            log["model"],
            log["latency_ms"],
            1 if log["success"] else 0,
            log["error"],
            log["prompt_tokens_estimate"],
            log["user_message"],
            log["assistant_response"],
            json.dumps(log.get("traces", [])),
        ))
    except Exception as e:
        logger.error(f"Error saving decision log to database: {e}")

def get_decision_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves the last N decision logs from the database, sorted by new first."""
    try:
        rows = _get_backend().execute("""
            SELECT timestamp, session_id, model, latency_ms, success,
                   error, prompt_tokens_estimate, user_message, assistant_response, traces
            FROM decision_logs
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        logs = []
        for r in rows:
            try:
                traces = json.loads(r[9])
            except Exception:
                traces = []
            logs.append({
                "timestamp": r[0],
                "session_id": r[1],
                "model": r[2],
                "latency_ms": r[3],
                "success": bool(r[4]),
                "error": r[5],
                "prompt_tokens_estimate": r[6],
                "user_message": r[7],
                "assistant_response": r[8],
                "traces": traces,
            })
        return logs
    except Exception as e:
        logger.error(f"Error retrieving decision logs: {e}")
        return []

def save_activity_log(log: Dict[str, Any]):
    """Saves a single activity log to the database."""
    try:
        _get_backend().execute("""
            INSERT INTO activity_logs (timestamp, type, source, message, token_cost)
            VALUES (?, ?, ?, ?, ?)
        """, (
            log["timestamp"],
            log["type"],
            log["source"],
            log["message"],
            log["token_cost"],
        ))
    except Exception as e:
        logger.error(f"Error saving activity log to database: {e}")

def get_activity_logs(limit: int = 200) -> List[Dict[str, Any]]:
    """Retrieves the last N activity logs from the database, sorted chronologically."""
    try:
        rows = _get_backend().execute("""
            SELECT timestamp, type, source, message, token_cost FROM (
                SELECT timestamp, type, source, message, token_cost, id FROM activity_logs
                ORDER BY id DESC LIMIT ?
            ) ORDER BY id DESC
        """, (limit,))
        return [
            {"timestamp": r[0], "type": r[1], "source": r[2], "message": r[3], "token_cost": r[4]}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error retrieving activity logs: {e}")
        return []

def clear_activity_logs():
    """Deletes all activity logs in the database."""
    try:
        _get_backend().rowcount("DELETE FROM activity_logs")
        logger.info("Cleared activity logs database.")
    except Exception as e:
        logger.error(f"Error clearing activity logs: {e}")

# ─── SUBAGENTS CRUD HELPERS ───────────────────────────────────────────────────

def save_subagent(
    id: str,
    name: str,
    system_prompt: str,
    model: str,
    agent_type: str = "agent",
    parent_id: Optional[str] = None,
    skills: str = "",
    x: int = 100,
    y: int = 100,
    temperature: float = 0.7,
):
    """Saves or updates a subagent's configuration in the database."""
    try:
        _get_backend().execute("""
            INSERT INTO subagents (id, name, system_prompt, model, agent_type, parent_id, skills, x, y, temperature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                system_prompt=excluded.system_prompt,
                model=excluded.model,
                agent_type=excluded.agent_type,
                parent_id=excluded.parent_id,
                skills=excluded.skills,
                x=excluded.x,
                y=excluded.y,
                temperature=excluded.temperature
        """, (id, name, system_prompt, model, agent_type, parent_id, skills, x, y, temperature))
        logger.info(f"Subagent saved: {id} ({name})")
    except Exception as e:
        logger.error(f"Error saving subagent {id}: {e}")

def get_subagent(id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a subagent by its ID."""
    try:
        rows = _get_backend().execute("""
            SELECT id, name, system_prompt, model, created_at, agent_type, parent_id, skills, x, y, temperature
            FROM subagents WHERE id = ?
        """, (id,))
        if rows:
            row = rows[0]
            return {
                "id": row[0],
                "name": row[1],
                "system_prompt": row[2],
                "model": row[3],
                "created_at": row[4],
                "agent_type": row[5] or "agent",
                "parent_id": row[6],
                "skills": row[7] or "",
                "x": row[8] if row[8] is not None else 100,
                "y": row[9] if row[9] is not None else 100,
                "temperature": row[10] if row[10] is not None else 0.7,
            }
        return None
    except Exception as e:
        logger.error(f"Error retrieving subagent {id}: {e}")
        return None

def get_all_subagents() -> List[Dict[str, Any]]:
    """Retrieves all registered subagents from the database."""
    try:
        rows = _get_backend().execute("""
            SELECT id, name, system_prompt, model, created_at, agent_type, parent_id, skills, x, y, temperature
            FROM subagents ORDER BY id ASC
        """)
        return [
            {
                "id": r[0],
                "name": r[1],
                "system_prompt": r[2],
                "model": r[3],
                "created_at": r[4],
                "agent_type": r[5] or "agent",
                "parent_id": r[6],
                "skills": r[7] or "",
                "x": r[8] if r[8] is not None else 100,
                "y": r[9] if r[9] is not None else 100,
                "temperature": r[10] if r[10] is not None else 0.7,
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error listing subagents: {e}")
        return []

def delete_subagent(id: str) -> bool:
    """Deletes a subagent from the database. Returns True if deleted, False otherwise."""
    try:
        deleted = _get_backend().rowcount("DELETE FROM subagents WHERE id = ?", (id,)) > 0
        if deleted:
            logger.info(f"Subagent deleted: {id}")
        return deleted
    except Exception as e:
        logger.error(f"Error deleting subagent {id}: {e}")
        return False

def db_save_subagent_memory(subagent_id: str, key: str, value: str):
    """Saves or updates a memory fact (key-value pair) for a specific subagent."""
    try:
        _get_backend().execute("""
            INSERT OR REPLACE INTO subagent_memory (subagent_id, key, value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (subagent_id, key, value))
        logger.info(f"Subagent memory saved: {subagent_id} -> {key}")
    except Exception as e:
        logger.error(f"Error saving subagent memory: {e}")

def db_get_subagent_memory(subagent_id: str, key: Optional[str] = None) -> Dict[str, str]:
    """Retrieves saved facts for a specific subagent. Returns a dict of key -> value."""
    try:
        if key:
            rows = _get_backend().execute(
                "SELECT key, value FROM subagent_memory WHERE subagent_id = ? AND key = ?",
                (subagent_id, key),
            )
        else:
            rows = _get_backend().execute(
                "SELECT key, value FROM subagent_memory WHERE subagent_id = ?",
                (subagent_id,),
            )
        return {r[0]: r[1] for r in rows}
    except Exception as e:
        logger.error(f"Error getting subagent memory: {e}")
        return {}

def db_delete_subagent_memory(subagent_id: str, key: str) -> bool:
    """Deletes a memory fact for a specific subagent."""
    try:
        return _get_backend().rowcount(
            "DELETE FROM subagent_memory WHERE subagent_id = ? AND key = ?",
            (subagent_id, key),
        ) > 0
    except Exception as e:
        logger.error(f"Error deleting subagent memory: {e}")
        return False

# ─── APP SETTINGS HELPERS ────────────────────────────────────────────────────

def get_setting(key: str) -> Optional[str]:
    """Returns a global app setting value by key, or None if not found."""
    try:
        rows = _get_backend().execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        return rows[0][0] if rows else None
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return None

def set_setting(key: str, value: str) -> bool:
    """Saves or updates a global app setting."""
    try:
        _get_backend().execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        return True
    except Exception as e:
        logger.error(f"Error setting {key}: {e}")
        return False

# ─── SESSION METADATA HELPERS ──────────────────────────────────────────────────

def save_session_metadata(session_id: str, title: str, agent_id: Optional[str] = None):
    """Saves or updates custom metadata (title and target agent) for a chat session."""
    try:
        # Check if row exists to preserve existing values if updating selectively
        rows = _get_backend().execute(
            "SELECT agent_id FROM session_metadata WHERE session_id = ?", (session_id,)
        )
        final_agent_id = agent_id
        if rows and agent_id is None:
            final_agent_id = rows[0][0]

        _get_backend().execute("""
            INSERT INTO session_metadata (session_id, title, agent_id, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                title = excluded.title,
                agent_id = excluded.agent_id,
                updated_at = CURRENT_TIMESTAMP
        """, (session_id, title, final_agent_id))
        logger.info(f"Saved custom metadata for session {session_id}: title={title}, agent_id={final_agent_id}")
    except Exception as e:
        logger.error(f"Error saving session metadata for {session_id}: {e}")

def save_session_title(session_id: str, title: str):
    """Saves or updates a custom title for a chat session."""
    save_session_metadata(session_id, title, agent_id=None)

def get_session_agent_id(session_id: str) -> Optional[str]:
    """Retrieves the mapped agent/orchestrator ID for a session."""
    try:
        rows = _get_backend().execute(
            "SELECT agent_id FROM session_metadata WHERE session_id = ?", (session_id,)
        )
        return rows[0][0] if rows else None
    except Exception as e:
        logger.error(f"Error retrieving session agent ID for {session_id}: {e}")
        return None

def get_session_title(session_id: str) -> Optional[str]:
    """Retrieves the custom title of a session, if exists."""
    try:
        rows = _get_backend().execute(
            "SELECT title FROM session_metadata WHERE session_id = ?", (session_id,)
        )
        return rows[0][0] if rows else None
    except Exception as e:
        logger.error(f"Error retrieving session title for {session_id}: {e}")
        return None

def delete_session_title(session_id: str) -> bool:
    """Deletes custom title metadata for a session."""
    try:
        return _get_backend().rowcount(
            "DELETE FROM session_metadata WHERE session_id = ?", (session_id,)
        ) > 0
    except Exception as e:
        logger.error(f"Error deleting session title for {session_id}: {e}")
        return False

# Auto-initialize database schema on import to prevent missing tables
init_db()
