import os
import sqlite3
import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger("hermes.database")

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "hermes.db")

def _json_or_empty(raw: Any) -> Dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}

def init_db():
    """Initializes the database and creates the tables if they don't exist."""
    # Ensure data directory exists
    os.makedirs(DB_DIR, exist_ok=True)
    
    logger.info(f"Initializing SQLite database at: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
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
        ("role", "TEXT DEFAULT 'Specialist'"),
        ("status", "TEXT DEFAULT 'idle'"),
        ("is_enabled", "INTEGER DEFAULT 1"),
        ("model_provider", "TEXT DEFAULT 'openrouter'"),
        ("model_type", "TEXT DEFAULT 'external'"),
        ("model_params", "TEXT DEFAULT '{}'"),
        ("current_task", "TEXT DEFAULT ''"),
        ("last_action", "TEXT DEFAULT ''"),
        ("last_error", "TEXT DEFAULT ''"),
        ("progress", "INTEGER DEFAULT 0"),
        ("updated_at", "TEXT"),
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
                    'You are Jarvis, a highly intelligent AI orchestrator. Your job is to understand the user''s request and delegate it to the most appropriate sub-agent. Be concise, efficient, and always explain which agent you are routing to.',
                    'Вы — исследовательский агент. Ищите информацию в интернете с помощью web_search.',
                    'You are a research agent. Search for information on the internet using web_search.',
                    'Вы — Код-Инженер. Пишите и выполняйте Python скрипты.',
                    'You are a Code Engineer. Write and execute Python scripts.',
                    'Вы — Аналитик-Визуализатор. Создавайте графики.',
                    'You are an Analyst-Visualizer. Create charts.'
                )
            """, (agent_id, name, prompt, default_model, agent_type, parent_id, skills, x, y, 0.7))

        # Restore public Jarvis branding for databases that were temporarily migrated to Vexa.
        cursor.execute("""
            UPDATE subagents
            SET name = 'Jarvis (Main)',
                system_prompt = REPLACE(system_prompt, 'Vexa', 'Jarvis')
            WHERE id = 'jarvis'
              AND (name = 'Vexa (Main)' OR system_prompt LIKE '%Vexa%')
        """)
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

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL DEFAULT 'global',
            key TEXT NOT NULL,
            value TEXT NOT NULL,
            source TEXT DEFAULT 'auto',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(session_id, key)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_memory_session ON user_memory (session_id, updated_at DESC)
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    conn.close()
    logger.info("Database initialized successfully.")

def save_message(session_id: str, role: str, content: str, cost_usd: float = 0.0) -> Optional[int]:
    """Saves a single message to database with cost tracking and returns the new message ID."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO messages (session_id, role, content, cost_usd) VALUES (?, ?, ?, ?)",
            (session_id, role, content, cost_usd)
        )
        new_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return new_id
    except Exception as e:
        logger.error(f"Error saving message: {e}")
        return None

def get_chat_history(session_id: str, limit: int = 20) -> List[Dict[str, Any]]:
    """Retrieves the last N messages for a given chat session, in chronological order."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Select last limit messages and reverse to chronological order
        cursor.execute("""
            SELECT id, role, content, cost_usd FROM (
                SELECT id, role, content, cost_usd FROM messages 
                WHERE session_id = ? 
                ORDER BY id DESC LIMIT ?
            ) ORDER BY id ASC
        """, (session_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [{"id": r[0], "role": r[1], "content": r[2], "cost_usd": r[3]} for r in rows]
    except Exception as e:
        logger.error(f"Error retrieving chat history: {e}")
        return []

def clear_chat_history(session_id: str):
    """Deletes all messages in the database for a session."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        conn.commit()
        conn.close()
        logger.info(f"Cleared database history for session: {session_id}")
    except Exception as e:
        logger.error(f"Error clearing chat history: {e}")

def save_user_memory(key: str, value: str, session_id: str = "global", source: str = "auto") -> Optional[int]:
    """Stores a durable user memory fact. Existing keys are updated in place."""
    clean_key = (key or "").strip()[:120]
    clean_value = (value or "").strip()[:1200]
    clean_session = (session_id or "global").strip()[:120] or "global"
    if not clean_key or not clean_value:
        return None

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_memory (session_id, key, value, source, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id, key) DO UPDATE SET
                value = excluded.value,
                source = excluded.source,
                updated_at = CURRENT_TIMESTAMP
        """, (clean_session, clean_key, clean_value, source))
        memory_id = cursor.lastrowid
        conn.commit()
        conn.close()
        logger.info("User memory saved: %s/%s", clean_session, clean_key)
        return memory_id
    except Exception as e:
        logger.error(f"Error saving user memory: {e}")
        return None

def search_user_memory(query: str, session_id: str = "global", limit: int = 4) -> List[Dict[str, Any]]:
    """Fast SQLite retrieval for durable memory facts relevant to the current message."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, session_id, key, value, source, updated_at
            FROM user_memory
            WHERE session_id IN ('global', ?)
            ORDER BY updated_at DESC
            LIMIT 200
        """, ((session_id or "global"),))
        rows = cursor.fetchall()
        conn.close()

        terms = {
            token.lower()
            for token in (query or "").replace("\n", " ").split()
            if len(token.strip(".,!?;:()[]{}\"'`")) >= 3
        }

        scored = []
        for row in rows:
            text = f"{row[2]} {row[3]}".lower()
            score = sum(1 for term in terms if term.strip(".,!?;:()[]{}\"'`") in text)
            # Keep explicit profile facts available even if the question is short.
            if score > 0 or row[2].startswith(("user_", "preference_")):
                scored.append((score, row))

        scored.sort(key=lambda item: (item[0], item[1][5] or ""), reverse=True)
        return [
            {
                "id": row[0],
                "session_id": row[1],
                "key": row[2],
                "value": row[3],
                "source": row[4],
                "updated_at": row[5],
                "score": score,
            }
            for score, row in scored[: max(1, limit)]
        ]
    except Exception as e:
        logger.error(f"Error searching user memory: {e}")
        return []

def list_user_memory(session_id: str = "global", limit: int = 100) -> List[Dict[str, Any]]:
    """Lists durable memory facts, newest first."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, session_id, key, value, source, updated_at
            FROM user_memory
            WHERE session_id IN ('global', ?)
            ORDER BY updated_at DESC
            LIMIT ?
        """, ((session_id or "global"), limit))
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "session_id": row[1],
                "key": row[2],
                "value": row[3],
                "source": row[4],
                "updated_at": row[5],
            }
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Error listing user memory: {e}")
        return []

def save_app_settings(settings: Dict[str, Any]):
    """Persists runtime configuration edited from the dashboard."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        for key, value in settings.items():
            cursor.execute("""
                INSERT INTO app_settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = CURRENT_TIMESTAMP
            """, (key, json.dumps(value, ensure_ascii=False)))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving app settings: {e}")

def get_app_settings() -> Dict[str, Any]:
    """Loads persisted dashboard runtime configuration."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM app_settings")
        rows = cursor.fetchall()
        conn.close()
        settings = {}
        for key, value in rows:
            try:
                settings[key] = json.loads(value)
            except Exception:
                settings[key] = value
        return settings
    except Exception as e:
        logger.error(f"Error loading app settings: {e}")
        return {}

def save_decision_log(log: Dict[str, Any]):
    """Saves a single agent decision log to the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
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
            json.dumps(log.get("traces", []))
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving decision log to database: {e}")

def get_decision_logs(limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves the last N decision logs from the database, sorted by new first."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, session_id, model, latency_ms, success, 
                   error, prompt_tokens_estimate, user_message, assistant_response, traces 
            FROM decision_logs 
            ORDER BY id DESC LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        
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
                "traces": traces
            })
        return logs
    except Exception as e:
        logger.error(f"Error retrieving decision logs: {e}")
        return []

def save_activity_log(log: Dict[str, Any]):
    """Saves a single activity log to the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO activity_logs (timestamp, type, source, message, token_cost)
            VALUES (?, ?, ?, ?, ?)
        """, (
            log["timestamp"],
            log["type"],
            log["source"],
            log["message"],
            log["token_cost"]
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error saving activity log to database: {e}")

def get_activity_logs(limit: int = 200) -> List[Dict[str, Any]]:
    """Retrieves the last N activity logs from the database, sorted chronologically."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT timestamp, type, source, message, token_cost FROM (
                SELECT timestamp, type, source, message, token_cost, id FROM activity_logs
                ORDER BY id DESC LIMIT ?
            ) ORDER BY id DESC
        """, (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        logs = []
        for r in rows:
            logs.append({
                "timestamp": r[0],
                "type": r[1],
                "source": r[2],
                "message": r[3],
                "token_cost": r[4]
            })
        return logs
    except Exception as e:
        logger.error(f"Error retrieving activity logs: {e}")
        return []

def clear_activity_logs():
    """Deletes all activity logs in the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM activity_logs")
        conn.commit()
        conn.close()
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
    role: str = "Specialist",
    status: str = "idle",
    is_enabled: bool = True,
    model_provider: str = "openrouter",
    model_type: str = "external",
    model_params: Optional[Dict[str, Any]] = None,
):
    """Saves or updates a subagent's configuration in the database."""
    try:
        model_params_json = json.dumps(model_params or {}, ensure_ascii=False)
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subagents (
                id, name, system_prompt, model, agent_type, parent_id, skills, x, y,
                temperature, role, status, is_enabled, model_provider, model_type,
                model_params, updated_at
            ) 
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET 
                name=excluded.name,
                system_prompt=excluded.system_prompt,
                model=excluded.model,
                agent_type=excluded.agent_type,
                parent_id=excluded.parent_id,
                skills=excluded.skills,
                x=excluded.x,
                y=excluded.y,
                temperature=excluded.temperature,
                role=excluded.role,
                status=excluded.status,
                is_enabled=excluded.is_enabled,
                model_provider=excluded.model_provider,
                model_type=excluded.model_type,
                model_params=excluded.model_params,
                updated_at=CURRENT_TIMESTAMP
        """, (
            id, name, system_prompt, model, agent_type, parent_id, skills, x, y,
            temperature, role, status, 1 if is_enabled else 0, model_provider,
            model_type, model_params_json
        ))
        conn.commit()
        conn.close()
        logger.info(f"Subagent saved: {id} ({name})")
    except Exception as e:
        logger.error(f"Error saving subagent {id}: {e}")

def get_subagent(id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a subagent by its ID."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, system_prompt, model, created_at, agent_type, parent_id, skills,
                   x, y, temperature, role, status, is_enabled, model_provider, model_type,
                   model_params, current_task, last_action, last_error, progress, updated_at
            FROM subagents WHERE id = ?
        """, (id,))
        row = cursor.fetchone()
        conn.close()
        if row:
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
                "role": row[11] or "Specialist",
                "status": row[12] or "idle",
                "is_enabled": bool(row[13]),
                "model_provider": row[14] or "openrouter",
                "model_type": row[15] or "external",
                "model_params": _json_or_empty(row[16]),
                "current_task": row[17] or "",
                "last_action": row[18] or "",
                "last_error": row[19] or "",
                "progress": row[20] if row[20] is not None else 0,
                "updated_at": row[21],
            }
        return None
    except Exception as e:
        logger.error(f"Error retrieving subagent {id}: {e}")
        return None

def get_all_subagents() -> List[Dict[str, Any]]:
    """Retrieves all registered subagents from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, name, system_prompt, model, created_at, agent_type, parent_id, skills,
                   x, y, temperature, role, status, is_enabled, model_provider, model_type,
                   model_params, current_task, last_action, last_error, progress, updated_at
            FROM subagents ORDER BY id ASC
        """)
        rows = cursor.fetchall()
        conn.close()
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
                "role": r[11] or "Specialist",
                "status": r[12] or "idle",
                "is_enabled": bool(r[13]),
                "model_provider": r[14] or "openrouter",
                "model_type": r[15] or "external",
                "model_params": _json_or_empty(r[16]),
                "current_task": r[17] or "",
                "last_action": r[18] or "",
                "last_error": r[19] or "",
                "progress": r[20] if r[20] is not None else 0,
                "updated_at": r[21],
            }
            for r in rows
        ]
    except Exception as e:
        logger.error(f"Error listing subagents: {e}")
        return []

def delete_subagent(id: str) -> bool:
    """Deletes a subagent from the database. Returns True if deleted, False otherwise."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subagents WHERE id = ?", (id,))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        if deleted:
            logger.info(f"Subagent deleted: {id}")
        return deleted
    except Exception as e:
        logger.error(f"Error deleting subagent {id}: {e}")
        return False

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
        from zoneinfo import ZoneInfo
        timestamp = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S")
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
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
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error logging agent event for {agent_id}: {e}")

def get_agent_events(agent_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, agent_id, timestamp, event_type, message, status, task, metadata
            FROM agent_events
            WHERE agent_id = ?
            ORDER BY id DESC
            LIMIT ?
        """, (agent_id, limit))
        rows = cursor.fetchall()
        conn.close()
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
        logger.error(f"Error reading agent events for {agent_id}: {e}")
        return []

def update_agent_runtime_state(
    agent_id: str,
    status: Optional[str] = None,
    current_task: Optional[str] = None,
    last_action: Optional[str] = None,
    last_error: Optional[str] = None,
    progress: Optional[int] = None,
):
    """Updates runtime-only agent state used by the AI office view."""
    fields = []
    values: List[Any] = []
    for name, value in [
        ("status", status),
        ("current_task", current_task),
        ("last_action", last_action),
        ("last_error", last_error),
        ("progress", progress),
    ]:
        if value is not None:
            fields.append(f"{name} = ?")
            values.append(value)
    if not fields:
        return
    fields.append("updated_at = CURRENT_TIMESTAMP")
    values.append(agent_id)
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(f"UPDATE subagents SET {', '.join(fields)} WHERE id = ?", values)
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating agent runtime state for {agent_id}: {e}")

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
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO subagent_memory (subagent_id, key, value, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (subagent_id, key, value))
        conn.commit()
        conn.close()
        logger.info(f"Subagent memory saved: {subagent_id} -> {key}")
    except Exception as e:
        logger.error(f"Error saving subagent memory: {e}")

def db_get_subagent_memory(subagent_id: str, key: Optional[str] = None) -> Dict[str, str]:
    """Retrieves saved facts for a specific subagent. Returns a dict of key -> value."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if key:
            cursor.execute("SELECT key, value FROM subagent_memory WHERE subagent_id = ? AND key = ?", (subagent_id, key))
        else:
            cursor.execute("SELECT key, value FROM subagent_memory WHERE subagent_id = ?", (subagent_id,))
        rows = cursor.fetchall()
        conn.close()
        return {r[0]: r[1] for r in rows}
    except Exception as e:
        logger.error(f"Error getting subagent memory: {e}")
        return {}

def db_delete_subagent_memory(subagent_id: str, key: str) -> bool:
    """Deletes a memory fact for a specific subagent."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM subagent_memory WHERE subagent_id = ? AND key = ?", (subagent_id, key))
        deleted = cursor.rowcount > 0
        conn.commit()
        conn.close()
        return deleted
    except Exception as e:
        logger.error(f"Error deleting subagent memory: {e}")
        return False

# Auto-initialize database schema on import to prevent missing tables
init_db()
