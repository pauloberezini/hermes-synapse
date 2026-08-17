import os
import sys
import tempfile
import pytest

# Force isolated temporary SQLite DB for all pytest runs so tests NEVER touch production DB
_temp_db_dir = tempfile.mkdtemp(prefix="jarvis_pytest_")
_temp_db_path = os.path.join(_temp_db_dir, "test_hermes.db")

os.environ["DATABASE_URL"] = ""

import backend.database as db_mod
db_mod.DB_DIR = _temp_db_dir
db_mod.DB_PATH = _temp_db_path
db_mod._backend = db_mod.SQLiteBackend()
@pytest.fixture(scope="function", autouse=True)
def clean_test_database():
    import backend.database as db_mod
    db_mod.init_db()
    with db_mod._get_backend().connect() as conn:
        cur = conn.cursor()
        for table in ["trade_traces", "app_settings", "tasks", "subagent_memory", "session_metadata", "rss_feed_items", "graph_nodes", "graph_edges", "messages", "market_activity", "distilled_skills", "subagents"]:
            try:
                cur.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        # Re-insert default settings
        try:
            cur.execute("INSERT INTO app_settings (key, value) VALUES ('language', 'en') ON CONFLICT(key) DO NOTHING")
        except Exception:
            pass
@pytest.fixture(scope="session", autouse=True)
def isolate_test_database():
    yield
    try:
        for f in os.listdir(_temp_db_dir):
            os.remove(os.path.join(_temp_db_dir, f))
        os.rmdir(_temp_db_dir)
    except Exception:
        pass
