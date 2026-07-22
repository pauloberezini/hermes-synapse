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

    @abstractmethod
    def translate_placeholder(self, sql: str) -> str:
        """Translate SQLite '?' placeholder to backend placeholder (e.g. %s)."""
        ...

    @abstractmethod
    def init_schema(self) -> None:
        """Create tables, indexes, and run migrations for this backend."""
        ...


class SQLiteBackend(DatabaseBackend):
    """Default backend: SQLite with WAL mode enabled."""

    @contextmanager
    def connect(self):
        conn = _get_conn()
        try:
            yield conn
        finally:
            conn.close()

    def translate_placeholder(self, sql: str) -> str:
        return sql

    def init_schema(self) -> None:
        _init_sqlite_schema()


class PostgresBackend(DatabaseBackend):
    """Optional PostgreSQL backend — activated via DATABASE_URL env var.

    Requires: pip install sqlalchemy psycopg2-binary
    (or: uv add sqlalchemy psycopg2-binary)
    """

    def __init__(self, url: str):
        try:
            from sqlalchemy import create_engine  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "PostgreSQL backend requires SQLAlchemy and psycopg2.\n"
                "Install with: uv add sqlalchemy psycopg2-binary"
            ) from e
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

    def translate_placeholder(self, sql: str) -> str:
        return sql.replace("?", "%s")

    def init_schema(self) -> None:
        _init_postgres_schema()


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


# Module-level singleton backend
_backend: Optional[DatabaseBackend] = None


def _get_backend() -> DatabaseBackend:
    """Return the module-level backend, initializing lazily on first call."""
    global _backend
    if _backend is None:
        _backend = _create_backend()
    return _backend


def _set_backend_for_tests(backend: Optional[DatabaseBackend]) -> None:
    """Test-only hook to inject or reset the backend singleton."""
    global _backend
    _backend = backend


# ---------------------------------------------------------------------------
# Module-level helper execution functions (SQL parameter translation handled)
# ---------------------------------------------------------------------------

def _execute(sql: str, params: tuple = ()) -> list:
    backend = _get_backend()
    sql_translated = backend.translate_placeholder(sql)
    with backend.connect() as conn:
        cur = conn.cursor()
        cur.execute(sql_translated, params)
        conn.commit()
        try:
            return cur.fetchall()
        except Exception:
            return []


def _executemany(sql: str, params_list: list) -> None:
    backend = _get_backend()
    sql_translated = backend.translate_placeholder(sql)
    with backend.connect() as conn:
        cur = conn.cursor()
        cur.executemany(sql_translated, params_list)
        conn.commit()


def _lastrowid(sql: str, params: tuple = ()) -> Optional[int]:
    backend = _get_backend()
    sql_translated = backend.translate_placeholder(sql)
    if isinstance(backend, PostgresBackend):
        # PostgreSQL uses returning clause for insert ID
        if "returning" not in sql_translated.lower():
            sql_translated = sql_translated.rstrip(";") + " RETURNING id"
        with backend.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql_translated, params)
            row = cur.fetchone()
            conn.commit()
            return row[0] if row else None
    else:
        with backend.connect() as conn:
            cur = conn.cursor()
            cur.execute(sql_translated, params)
            last_id = cur.lastrowid
            conn.commit()
            return last_id


def _rowcount(sql: str, params: tuple = ()) -> int:
    backend = _get_backend()
    sql_translated = backend.translate_placeholder(sql)
    with backend.connect() as conn:
        cur = conn.cursor()
        cur.execute(sql_translated, params)
        conn.commit()
        return cur.rowcount



# ---------------------------------------------------------------------------
# Pluggable schema creation & migrations
# ---------------------------------------------------------------------------

def init_db():
    """Initializes the database and creates the tables if they don't exist."""
    _get_backend().init_schema()


def _init_sqlite_schema():
    logger.info(f"Initializing SQLite database (path={DB_PATH})")
    os.makedirs(DB_DIR, exist_ok=True)
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

    # Migration: add agent_id, completion_tokens_estimate, cost_usd to decision_logs
    cursor.execute("PRAGMA table_info(decision_logs)")
    existing_dec_cols = [row[1] for row in cursor.fetchall()]
    if "agent_id" not in existing_dec_cols:
        try:
            cursor.execute("ALTER TABLE decision_logs ADD COLUMN agent_id TEXT DEFAULT 'jarvis'")
            logger.info("Migrated decision_logs table to include agent_id column.")
        except sqlite3.OperationalError:
            pass
    if "completion_tokens_estimate" not in existing_dec_cols:
        try:
            cursor.execute("ALTER TABLE decision_logs ADD COLUMN completion_tokens_estimate INTEGER DEFAULT 0")
            logger.info("Migrated decision_logs table to include completion_tokens_estimate column.")
        except sqlite3.OperationalError:
            pass
    if "cost_usd" not in existing_dec_cols:
        try:
            cursor.execute("ALTER TABLE decision_logs ADD COLUMN cost_usd REAL DEFAULT 0.0")
            logger.info("Migrated decision_logs table to include cost_usd column.")
        except sqlite3.OperationalError:
            pass

    # Create Graph RAG tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS graph_nodes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT,
            description TEXT,
            doc_id TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS graph_edges (
            source TEXT NOT NULL,
            target TEXT NOT NULL,
            description TEXT,
            weight REAL DEFAULT 1.0,
            doc_id TEXT,
            PRIMARY KEY (source, target, doc_id)
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

    # Create distilled skills table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS distilled_skills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            decision_log_id INTEGER,
            session_id TEXT NOT NULL,
            skill_name TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            file_path TEXT NOT NULL,
            trigger_conditions TEXT NOT NULL,
            content TEXT NOT NULL
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
            pass

    # Pre-populate default subagents if table is empty
    cursor.execute("SELECT COUNT(*) FROM subagents")
    if cursor.fetchone()[0] == 0:
        logger.info("Pre-populating default subagents.")
        default_model = os.environ.get("LLM_MODEL", "google/gemini-2.5-flash")
        default_agents = _get_default_agents(default_model)
        cursor.executemany("""
            INSERT INTO subagents (id, name, system_prompt, model, agent_type, parent_id, skills, x, y, temperature)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [t + (0.7,) for t in default_agents])
        logger.info("Successfully seeded default agents.")
    else:
        _migrate_existing_subagents_sqlite(cursor)

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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            message TEXT NOT NULL,
            status TEXT DEFAULT 'info',
            task TEXT DEFAULT '',
            metadata TEXT DEFAULT '{}'
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_events_agent_id ON agent_events (agent_id, id DESC)
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
    logger.info("SQLite Database initialized successfully.")


def _init_postgres_schema():
    logger.info("Initializing PostgreSQL database schema")
    backend = _get_backend()
    with backend.connect() as conn:
        cursor = conn.cursor()

        # Create chat messages table (PostgreSQL uses SERIAL)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id SERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                cost_usd REAL DEFAULT 0.0
            )
        """)

        # Create index for fast session lookups
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_session_id ON messages (session_id)
        """)

        # Create decision logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS decision_logs (
                id SERIAL PRIMARY KEY,
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

        # PostgreSQL Migration helper: verify and add decision_logs columns
        for col, definition in [
            ("agent_id", "TEXT DEFAULT 'jarvis'"),
            ("completion_tokens_estimate", "INTEGER DEFAULT 0"),
            ("cost_usd", "REAL DEFAULT 0.0"),
        ]:
            cursor.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name='decision_logs' AND column_name=%s",
                (col,)
            )
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE decision_logs ADD COLUMN {col} {definition}")
                logger.info(f"PostgreSQL Migration: added column {col} to decision_logs table.")

        # Create Graph RAG tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT,
                description TEXT,
                doc_id TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                source TEXT NOT NULL,
                target TEXT NOT NULL,
                description TEXT,
                weight REAL DEFAULT 1.0,
                doc_id TEXT,
                PRIMARY KEY (source, target, doc_id)
            )
        """)


        # Create activity logs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id SERIAL PRIMARY KEY,
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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                agent_type TEXT DEFAULT 'agent',
                parent_id TEXT,
                skills TEXT DEFAULT '',
                x INTEGER DEFAULT 100,
                y INTEGER DEFAULT 100,
                temperature REAL DEFAULT 0.7
            )
        """)

        # Create distilled skills table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS distilled_skills (
                id SERIAL PRIMARY KEY,
                created_at TEXT NOT NULL,
                decision_log_id INTEGER,
                session_id TEXT NOT NULL,
                skill_name TEXT NOT NULL UNIQUE,
                title TEXT NOT NULL,
                file_path TEXT NOT NULL,
                trigger_conditions TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)

        # PostgreSQL Migration helper: verify and add subagents columns
        for col, definition in [
            ("agent_type", "TEXT DEFAULT 'agent'"),
            ("parent_id", "TEXT"),
            ("skills", "TEXT DEFAULT ''"),
            ("x", "INTEGER DEFAULT 100"),
            ("y", "INTEGER DEFAULT 100"),
            ("temperature", "REAL DEFAULT 0.7"),
        ]:
            cursor.execute(
                "SELECT 1 FROM information_schema.columns WHERE table_name='subagents' AND column_name=%s",
                (col,)
            )
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE subagents ADD COLUMN {col} {definition}")
                logger.info(f"PostgreSQL Migration: added column {col} to subagents table.")

        # Seed subagents if table is empty
        cursor.execute("SELECT COUNT(*) FROM subagents")
        if cursor.fetchone()[0] == 0:
            logger.info("Pre-populating default subagents in PostgreSQL.")
            default_model = os.environ.get("LLM_MODEL", "google/gemini-2.5-flash")
            default_agents = _get_default_agents(default_model)
            cursor.executemany("""
                INSERT INTO subagents (id, name, system_prompt, model, agent_type, parent_id, skills, x, y, temperature)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, [t + (0.7,) for t in default_agents])
            logger.info("Successfully seeded default agents in PostgreSQL.")
        else:
            _migrate_existing_subagents_postgres(cursor)

        # Create subagent memory table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS subagent_memory (
                subagent_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (subagent_id, key)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_events (
                id SERIAL PRIMARY KEY,
                agent_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                event_type TEXT NOT NULL,
                message TEXT NOT NULL,
                status TEXT DEFAULT 'info',
                task TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}'
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_agent_events_agent_id ON agent_events (agent_id, id DESC)
        """)

        # Global app settings (KV store)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cursor.execute("INSERT INTO app_settings (key, value) VALUES ('language', 'ru') ON CONFLICT (key) DO NOTHING")

        # Create session metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_metadata (
                session_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                agent_id TEXT
            )
        """)

        # PostgreSQL Migration helper: verify and add agent_id to session_metadata
        cursor.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name='session_metadata' AND column_name='agent_id'"
        )
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE session_metadata ADD COLUMN agent_id TEXT")
            logger.info("PostgreSQL Migration: added column agent_id to session_metadata table.")

        conn.commit()
    logger.info("PostgreSQL Database initialized successfully.")


def _get_default_agents(default_model: str) -> list:
    return [
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


def _migrate_existing_subagents_sqlite(cursor):
    upserts = _get_default_agents_migrations()
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


def _migrate_existing_subagents_postgres(cursor):
    upserts = _get_default_agents_migrations()
    default_model = os.environ.get("LLM_MODEL", "google/gemini-2.5-flash")
    for agent_id, name, prompt, agent_type, parent_id, skills, x, y in upserts:
        cursor.execute("""
            INSERT INTO subagents (id, name, system_prompt, model, agent_type, parent_id, skills, x, y, temperature)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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


def _get_default_agents_migrations() -> list:
    return [
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


def save_message(session_id: str, role: str, content: str, cost_usd: float = 0.0) -> Optional[int]:
    """Saves a single message to database with cost tracking and returns the new message ID."""
    try:
        return _lastrowid(
            "INSERT INTO messages (session_id, role, content, cost_usd) VALUES (?, ?, ?, ?)",
            (session_id, role, content, cost_usd),
        )
    except Exception as e:
        logger.error(f"Error saving message: {e}")
        return None

def get_chat_history(session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves the last N messages for a given chat session, in chronological order."""
    try:
        rows = _execute("""
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

def get_session_trajectory_data(session_id: str) -> Dict[str, Any]:
    """Retrieves full chronological message history and associated decision logs for a session."""
    try:
        rows = _execute("""
            SELECT id, role, content, cost_usd, timestamp FROM messages
            WHERE session_id = ?
            ORDER BY id ASC
        """, (session_id,))
        messages = [
            {"id": r[0], "role": r[1], "content": r[2], "cost_usd": r[3], "timestamp": r[4]}
            for r in rows
        ]

        dec_rows = _execute("""
            SELECT id, timestamp, session_id, model, latency_ms, success,
                   error, prompt_tokens_estimate, user_message, assistant_response, traces,
                   agent_id, completion_tokens_estimate, cost_usd
            FROM decision_logs
            WHERE session_id = ?
            ORDER BY id ASC
        """, (session_id,))
        decision_logs = []
        for r in dec_rows:
            try:
                traces = json.loads(r[10]) if isinstance(r[10], str) else r[10]
            except Exception:
                traces = []
            decision_logs.append({
                "id": r[0],
                "timestamp": r[1],
                "session_id": r[2],
                "model": r[3],
                "latency_ms": r[4],
                "success": bool(r[5]),
                "error": r[6],
                "prompt_tokens_estimate": r[7],
                "user_message": r[8],
                "assistant_response": r[9],
                "traces": traces,
                "agent_id": r[11] if len(r) > 11 else "jarvis",
                "completion_tokens_estimate": r[12] if len(r) > 12 else 0,
                "cost_usd": r[13] if len(r) > 13 else 0.0,
            })
        return {
            "session_id": session_id,
            "messages": messages,
            "decision_logs": decision_logs
        }
    except Exception as e:
        logger.error(f"Error retrieving session trajectory data for {session_id}: {e}")
        return {"session_id": session_id, "messages": [], "decision_logs": []}


def clear_chat_history(session_id: str):
    """Deletes all messages in the database for a session."""
    try:
        _rowcount("DELETE FROM messages WHERE session_id = ?", (session_id,))
        logger.info(f"Cleared database history for session: {session_id}")
    except Exception as e:
        logger.error(f"Error clearing chat history: {e}")

def save_decision_log(log: Dict[str, Any]):
    """Saves a single agent decision log to the database."""
    try:
        _execute("""
            INSERT INTO decision_logs (
                timestamp, session_id, model, latency_ms, success,
                error, prompt_tokens_estimate, user_message, assistant_response, traces,
                agent_id, completion_tokens_estimate, cost_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            log.get("agent_id", "jarvis"),
            log.get("completion_tokens_estimate", 0),
            log.get("cost_usd", 0.0),
        ))
    except Exception as e:
        logger.error(f"Error saving decision log to database: {e}")

def get_decision_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves the last N decision logs from the database, sorted by new first."""
    try:
        rows = _execute("""
            SELECT id, timestamp, session_id, model, latency_ms, success,
                   error, prompt_tokens_estimate, user_message, assistant_response, traces,
                   agent_id, completion_tokens_estimate, cost_usd
            FROM decision_logs
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        logs = []
        for r in rows:
            try:
                traces = json.loads(r[10]) if isinstance(r[10], str) else r[10]
            except Exception:
                traces = []
            logs.append({
                "id": r[0],
                "timestamp": r[1],
                "session_id": r[2],
                "model": r[3],
                "latency_ms": r[4],
                "success": bool(r[5]),
                "error": r[6],
                "prompt_tokens_estimate": r[7],
                "user_message": r[8],
                "assistant_response": r[9],
                "traces": traces,
                "agent_id": r[11] if len(r) > 11 else "jarvis",
                "completion_tokens_estimate": r[12] if len(r) > 12 else 0,
                "cost_usd": r[13] if len(r) > 13 else 0.0,
            })
        return logs
    except Exception as e:
        logger.error(f"Error retrieving decision logs: {e}")
        return []

def save_activity_log(log: Dict[str, Any]):
    """Saves a single activity log to the database."""
    try:
        _execute("""
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
        rows = _execute("""
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
        _rowcount("DELETE FROM activity_logs")
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
        _execute("""
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
        rows = _execute("""
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
        rows = _execute("""
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
        deleted = _rowcount("DELETE FROM subagents WHERE id = ?", (id,)) > 0
        if deleted:
            logger.info(f"Subagent deleted: {id}")
        return deleted
    except Exception as e:
        logger.error(f"Error deleting subagent {id}: {e}")
        return False

def _json_or_empty(val: Optional[str]) -> Dict[str, Any]:
    if not val:
        return {}
    try:
        return json.loads(val)
    except Exception:
        return {}

def log_agent_event(
    agent_id: str,
    event_type: str,
    message: str,
    status: str = "info",
    task: str = "",
    metadata: Optional[Dict[str, Any]] = None,
):
    """Stores a visible agent action for the office/admin screens."""
    try:
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _execute("""
            INSERT INTO agent_events (agent_id, timestamp, event_type, message, status, task, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            agent_id,
            timestamp,
            event_type,
            message,
            status,
            task,
            json.dumps(metadata or {}, ensure_ascii=False)
        ))
    except Exception as e:
        logger.error(f"Error logging agent event for {agent_id}: {e}")

def get_agent_events(agent_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        rows = _execute("""
            SELECT id, agent_id, timestamp, event_type, message, status, task, metadata
            FROM agent_events
            WHERE agent_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (agent_id, limit))
        return [
            {
                "id": r[0],
                "agent_id": r[1],
                "timestamp": r[2],
                "event_type": r[3],
                "message": r[4],
                "status": r[5],
                "task": r[6] or "",
                "metadata": _json_or_empty(r[7]),
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error fetching agent events for {agent_id}: {e}")
        return []

def get_agent_office_state() -> Dict[str, Any]:
    """Returns agents with their latest visible events for the live office screen."""
    agents = get_all_subagents()
    if not agents:
        logger.warning("Office state requested with no subagents present. Re-running DB initialization.")
        init_db()
        agents = get_all_subagents()
    return {
        "agents": [
            {
                **agent,
                "recent_events": get_agent_events(agent["id"], limit=5),
            }
            for agent in agents
        ]
    }

def db_save_subagent_memory(subagent_id: str, key: str, value: str):
    """Saves or updates a memory fact (key-value pair) for a specific subagent."""
    try:
        _execute("""
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
            rows = _execute(
                "SELECT key, value FROM subagent_memory WHERE subagent_id = ? AND key = ?",
                (subagent_id, key),
            )
        else:
            rows = _execute(
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
        return _rowcount(
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
        rows = _execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        return rows[0][0] if rows else None
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return None

def set_setting(key: str, value: str) -> bool:
    """Saves or updates a global app setting."""
    try:
        _execute(
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
        rows = _execute(
            "SELECT agent_id FROM session_metadata WHERE session_id = ?", (session_id,)
        )
        final_agent_id = agent_id
        if rows and agent_id is None:
            final_agent_id = rows[0][0]

        _execute("""
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
        rows = _execute(
            "SELECT agent_id FROM session_metadata WHERE session_id = ?", (session_id,)
        )
        return rows[0][0] if rows else None
    except Exception as e:
        logger.error(f"Error retrieving session agent ID for {session_id}: {e}")
        return None

def get_session_title(session_id: str) -> Optional[str]:
    """Retrieves the custom title of a session, if exists."""
    try:
        rows = _execute(
            "SELECT title FROM session_metadata WHERE session_id = ?", (session_id,)
        )
        return rows[0][0] if rows else None
    except Exception as e:
        logger.error(f"Error retrieving session title for {session_id}: {e}")
        return None

def delete_session_title(session_id: str) -> bool:
    """Deletes custom title metadata for a session."""
    try:
        return _rowcount(
            "DELETE FROM session_metadata WHERE session_id = ?", (session_id,)
        ) > 0
    except Exception as e:
        logger.error(f"Error deleting session title for {session_id}: {e}")
        return False

# ─── GRAPH DATABASE HELPERS ──────────────────────────────────────────────────

def db_save_graph_node(node_id: str, name: str, node_type: str, description: str, doc_id: str):
    """Saves or updates a graph node in the database."""
    try:
        _execute("""
            INSERT INTO graph_nodes (id, name, type, description, doc_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                description = excluded.description,
                doc_id = excluded.doc_id
        """, (node_id, name, node_type, description, doc_id))
    except Exception as e:
        logger.error(f"Error saving graph node: {e}")

def db_save_graph_edge(source: str, target: str, description: str, weight: float, doc_id: str):
    """Saves or updates a graph edge in the database."""
    try:
        _execute("""
            INSERT INTO graph_edges (source, target, description, weight, doc_id)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source, target, doc_id) DO UPDATE SET
                description = excluded.description,
                weight = excluded.weight
        """, (source, target, description, weight, doc_id))
    except Exception as e:
        logger.error(f"Error saving graph edge: {e}")

def db_get_graph_nodes(doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves graph nodes, optionally filtered by doc_id."""
    try:
        if doc_id:
            rows = _execute("SELECT id, name, type, description, doc_id FROM graph_nodes WHERE doc_id = ?", (doc_id,))
        else:
            rows = _execute("SELECT id, name, type, description, doc_id FROM graph_nodes")
        return [
            {"id": r[0], "name": r[1], "type": r[2], "description": r[3], "doc_id": r[4]}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error getting graph nodes: {e}")
        return []

def db_get_graph_edges(doc_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieves graph edges, optionally filtered by doc_id."""
    try:
        if doc_id:
            rows = _execute("SELECT source, target, description, weight, doc_id FROM graph_edges WHERE doc_id = ?", (doc_id,))
        else:
            rows = _execute("SELECT source, target, description, weight, doc_id FROM graph_edges")
        return [
            {"source": r[0], "target": r[1], "description": r[2], "weight": r[3], "doc_id": r[4]}
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error getting graph edges: {e}")
        return []

def db_clear_graph(doc_id: Optional[str] = None):
    """Deletes nodes and edges from the graph."""
    try:
        if doc_id:
            _rowcount("DELETE FROM graph_nodes WHERE doc_id = ?", (doc_id,))
            _rowcount("DELETE FROM graph_edges WHERE doc_id = ?", (doc_id,))
        else:
            _rowcount("DELETE FROM graph_nodes")
            _rowcount("DELETE FROM graph_edges")
    except Exception as e:
        logger.error(f"Error clearing graph: {e}")

# ─── AGGREGATED METRICS HELPER ───────────────────────────────────────────────

def db_get_aggregated_metrics() -> Dict[str, Any]:
    """Computes aggregated success rates and latency metrics by agent and by model."""
    try:
        # 1. Summary
        summary_row = _execute("""
            SELECT COUNT(*), AVG(latency_ms), SUM(success), 
                   SUM(prompt_tokens_estimate + completion_tokens_estimate),
                   SUM(cost_usd)
            FROM decision_logs
        """)
        
        total_calls = summary_row[0][0] if summary_row and summary_row[0][0] is not None else 0
        avg_latency = float(summary_row[0][1]) if summary_row and summary_row[0][1] is not None else 0.0
        sum_success = summary_row[0][2] if summary_row and summary_row[0][2] is not None else 0
        total_tokens = summary_row[0][3] if summary_row and summary_row[0][3] is not None else 0
        total_cost = float(summary_row[0][4]) if summary_row and summary_row[0][4] is not None else 0.0
        
        success_rate = (sum_success / total_calls * 100.0) if total_calls > 0 else 100.0
        
        summary = {
            "total_calls": total_calls,
            "avg_latency_ms": round(avg_latency, 1),
            "success_rate": round(success_rate, 1),
            "total_tokens": total_tokens,
            "total_cost_usd": round(total_cost, 6)
        }

        # 2. By Agent
        agent_rows = _execute("""
            SELECT agent_id, COUNT(*), SUM(success), AVG(latency_ms),
                   SUM(prompt_tokens_estimate + completion_tokens_estimate),
                   SUM(cost_usd)
            FROM decision_logs
            GROUP BY agent_id
        """)
        by_agent = []
        for r in agent_rows:
            agent_calls = r[1]
            agent_success = r[2] or 0
            agent_tokens = r[4] or 0
            agent_cost = float(r[5]) if r[5] is not None else 0.0
            
            by_agent.append({
                "agent_id": r[0],
                "total_calls": agent_calls,
                "success_rate": round((agent_success / agent_calls * 100.0), 1) if agent_calls > 0 else 100.0,
                "avg_latency_ms": round(float(r[3]), 1) if r[3] is not None else 0.0,
                "total_tokens": agent_tokens,
                "total_cost_usd": round(agent_cost, 6)
            })

        # 3. By Model
        model_rows = _execute("""
            SELECT model, COUNT(*), SUM(success), AVG(latency_ms),
                   SUM(prompt_tokens_estimate + completion_tokens_estimate),
                   SUM(cost_usd)
            FROM decision_logs
            GROUP BY model
        """)
        by_model = []
        for r in model_rows:
            model_calls = r[1]
            model_success = r[2] or 0
            model_tokens = r[4] or 0
            model_cost = float(r[5]) if r[5] is not None else 0.0
            
            by_model.append({
                "model": r[0],
                "total_calls": model_calls,
                "success_rate": round((model_success / model_calls * 100.0), 1) if model_calls > 0 else 100.0,
                "avg_latency_ms": round(float(r[3]), 1) if r[3] is not None else 0.0,
                "total_tokens": model_tokens,
                "total_cost_usd": round(model_cost, 6)
            })

        return {
            "summary": summary,
            "by_agent": by_agent,
            "by_model": by_model
        }
    except Exception as e:
        logger.error(f"Error computing aggregated metrics: {e}")
        return {
            "summary": {"total_calls": 0, "avg_latency_ms": 0.0, "success_rate": 100.0, "total_tokens": 0, "total_cost_usd": 0.0},
            "by_agent": [],
            "by_model": []
        }

def db_save_distilled_skill(skill_data: Dict[str, Any]) -> int:
    """Saves or updates a distilled skill entry in the database."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now_str = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S")
        _execute("""
            INSERT OR REPLACE INTO distilled_skills (
                created_at, decision_log_id, session_id, skill_name,
                title, file_path, trigger_conditions, content
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            skill_data.get("created_at", now_str),
            skill_data.get("decision_log_id"),
            skill_data.get("session_id", "default"),
            skill_data["skill_name"],
            skill_data["title"],
            skill_data["file_path"],
            skill_data.get("trigger_conditions", ""),
            skill_data["content"]
        ))
        rows = _execute("SELECT id FROM distilled_skills WHERE skill_name = ?", (skill_data["skill_name"],))
        return rows[0][0] if rows else 1
    except Exception as e:
        logger.error(f"Error saving distilled skill to database: {e}")
        return -1

def db_get_distilled_skills(limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieves distilled skills from database ordered by newest first."""
    try:
        rows = _execute("""
            SELECT id, created_at, decision_log_id, session_id, skill_name, title, file_path, trigger_conditions, content
            FROM distilled_skills
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        skills = []
        for r in rows:
            skills.append({
                "id": r[0],
                "created_at": r[1],
                "decision_log_id": r[2],
                "session_id": r[3],
                "skill_name": r[4],
                "title": r[5],
                "file_path": r[6],
                "trigger_conditions": r[7],
                "content": r[8]
            })
        return skills
    except Exception as e:
        logger.error(f"Error fetching distilled skills: {e}")
        return []

def db_is_log_distilled(decision_log_id: int) -> bool:
    """Returns True if a decision log ID has already been distilled into a skill."""
    try:
        rows = _execute("SELECT id FROM distilled_skills WHERE decision_log_id = ?", (decision_log_id,))
        return len(rows) > 0
    except Exception as e:
        logger.error(f"Error checking if decision log is distilled: {e}")
        return False

def db_get_undistilled_successful_logs(min_steps: int = 3, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves successful decision logs with at least min_steps execution traces that haven't been distilled yet."""
    try:
        rows = _execute("""
            SELECT id, timestamp, session_id, model, latency_ms, success,
                   error, prompt_tokens_estimate, user_message, assistant_response, traces,
                   agent_id, completion_tokens_estimate, cost_usd
            FROM decision_logs
            WHERE success = 1
              AND id NOT IN (SELECT decision_log_id FROM distilled_skills WHERE decision_log_id IS NOT NULL)
            ORDER BY id DESC LIMIT ?
        """, (limit * 3,))
        
        candidates = []
        for r in rows:
            try:
                traces = json.loads(r[10]) if isinstance(r[10], str) else r[10]
            except Exception:
                traces = []
            
            if isinstance(traces, list) and len(traces) >= min_steps:
                candidates.append({
                    "id": r[0],
                    "timestamp": r[1],
                    "session_id": r[2],
                    "model": r[3],
                    "latency_ms": r[4],
                    "success": bool(r[5]),
                    "error": r[6],
                    "prompt_tokens_estimate": r[7],
                    "user_message": r[8],
                    "assistant_response": r[9],
                    "traces": traces,
                    "agent_id": r[11],
                    "completion_tokens_estimate": r[12],
                    "cost_usd": r[13]
                })
                if len(candidates) >= limit:
                    break
        return candidates
    except Exception as e:
        logger.error(f"Error fetching undistilled logs: {e}")
        return []

# Auto-initialize database schema on import to prevent missing tables
init_db()

