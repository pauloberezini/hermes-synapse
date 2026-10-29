import os
import sys
import tempfile
import pytest

_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _project_root not in sys.path:
    sys.path.insert(0, _project_root)

# Force isolated temporary SQLite DB for all pytest runs so tests NEVER touch production DB
_temp_db_dir = tempfile.mkdtemp(prefix="jarvis_pytest_")
_temp_db_path = os.path.join(_temp_db_dir, "test_hermes.db")

os.environ["DATABASE_URL"] = ""

# Tests run inside the live container inherit prod secrets: never let a test
# send real notifications. Plugins strip their own secrets in their conftest.
os.environ["NOTIFICATION_PROVIDER"] = "console"
for _k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"):
    os.environ.pop(_k, None)

import backend.database as db_mod
db_mod.DB_DIR = _temp_db_dir
db_mod.DB_PATH = _temp_db_path
db_mod._backend = db_mod.SQLiteBackend()
@pytest.fixture(scope="function", autouse=True)
def clean_test_database():
    import backend.database as db_mod
    db_mod.DB_DIR = _temp_db_dir
    db_mod.DB_PATH = _temp_db_path
    if type(db_mod._backend) is not db_mod.SQLiteBackend or getattr(db_mod._backend, "db_path", None) != _temp_db_path:
        db_mod._set_backend_for_tests(db_mod.SQLiteBackend())
    
    backend = db_mod._get_backend()
    if type(backend) is not db_mod.SQLiteBackend or getattr(backend, "db_path", None) != _temp_db_path:
        db_mod._set_backend_for_tests(db_mod.SQLiteBackend())
        backend = db_mod._get_backend()

    db_mod.init_db()
    with backend.connect() as conn:
        cur = conn.cursor()
        for trigger in (
            "approval_decisions_no_update",
            "approval_decisions_no_delete",
            "approval_evidence_no_update",
        ):
            try:
                cur.execute(f"DROP TRIGGER IF EXISTS {trigger}")
            except Exception:
                pass
        for table in ["bcm_decision_traces", "trade_traces", "trades", "app_settings", "tasks", "subagent_memory", "session_metadata", "rss_feed_items", "graph_nodes", "graph_edges", "messages", "market_activity", "distilled_skills", "subagents", "approval_evidence", "approval_requests", "approval_decisions"]:
            try:
                cur.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        try:
            cur.execute("DELETE FROM sqlite_sequence WHERE name IN ('approval_decisions', 'approval_requests')")
        except Exception:
            pass
        db_mod.install_approval_decisions(cur)
        db_mod.install_approval_evidence(cur)

        # Re-insert default settings
        try:
            cur.execute("INSERT INTO app_settings (key, value) VALUES ('language', 'en') ON CONFLICT(key) DO NOTHING")
        except Exception:
            pass
        conn.commit()

    yield

    if type(db_mod._backend) is not db_mod.SQLiteBackend or getattr(db_mod._backend, "db_path", None) != _temp_db_path:
        db_mod._set_backend_for_tests(db_mod.SQLiteBackend())


@pytest.fixture
def tamper_decision_row():
    def _tamper(*, seq: int, reason: str = "forged", tenant_id: str = "default") -> None:
        import backend.database as db_mod
        backend = db_mod._get_backend()
        with backend.connect() as conn:
            cur = conn.cursor()
            cur.execute("DROP TRIGGER IF EXISTS approval_decisions_no_update")
            cur.execute("SELECT seq FROM approval_decisions WHERE tenant_id = ? ORDER BY seq ASC", (tenant_id,))
            seqs = [r[0] for r in cur.fetchall()]
            target = seq if seq in seqs else (seqs[seq - 1] if len(seqs) >= seq else seq)
            cur.execute(
                "UPDATE approval_decisions SET reason = ? WHERE seq = ? AND tenant_id = ?",
                (reason, target, tenant_id),
            )
            db_mod.install_approval_decisions(cur)
            conn.commit()

    return _tamper


@pytest.fixture(scope="function", autouse=True)
def reset_shared_test_state():
    yield
    try:
        from backend.mcp_client import mcp_clients
        mcp_clients.clear()
    except Exception:
        pass
    try:
        from backend.llm_model_manager import reset_endpoint_cooldowns
        reset_endpoint_cooldowns()
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

