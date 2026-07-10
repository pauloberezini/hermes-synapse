import os
import sqlite3
import logging
import json
from typing import List, Dict, Any, Optional

logger = logging.getLogger("hermes.database")

DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "hermes.db")

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
):
    """Saves or updates a subagent's configuration in the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
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
            SELECT id, name, system_prompt, model, created_at, agent_type, parent_id, skills, x, y, temperature
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
            SELECT id, name, system_prompt, model, created_at, agent_type, parent_id, skills, x, y, temperature
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

# ─── APP SETTINGS HELPERS ────────────────────────────────────────────────────

def get_setting(key: str) -> Optional[str]:
    """Returns a global app setting value by key, or None if not found."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return None

def set_setting(key: str, value: str) -> bool:
    """Saves or updates a global app setting."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO app_settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error setting {key}: {e}")
        return False

# Auto-initialize database schema on import to prevent missing tables
init_db()
