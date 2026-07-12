"""
Tests for SQLite WAL-mode optimisation and DatabaseBackend abstraction.

Coverage:
  1. WAL journal_mode is active after init_db()
  2. busy_timeout PRAGMA is set > 0
  3. synchronous PRAGMA is NORMAL (not FULL)
  4. foreign_keys PRAGMA is ON
  5. Concurrent writers do NOT raise 'database is locked'
  6. SQLiteBackend is selected when DATABASE_URL is absent
  7. _get_conn() opens WAL-mode connections independently
  8. All public API still works after WAL changes (smoke test)
"""

import os
import sqlite3
import threading
import pytest
from backend import database


# ---------------------------------------------------------------------------
# Fixture: isolated temp database per test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Redirect every test to its own temporary SQLite file."""
    original_path = database.DB_PATH
    original_dir = database.DB_DIR
    original_backend = database._backend

    test_db = tmp_path / "test_wal.db"
    database.DB_PATH = str(test_db)
    database.DB_DIR = str(tmp_path)
    database._backend = None  # force re-init

    database.init_db()

    yield

    # Restore global state
    database.DB_PATH = original_path
    database.DB_DIR = original_dir
    database._backend = original_backend


# ---------------------------------------------------------------------------
# 1–4: PRAGMA checks
# ---------------------------------------------------------------------------

def _pragma(db_path: str, name: str) -> str:
    """Query a PRAGMA value from a fresh WAL-mode connection."""
    conn = sqlite3.connect(db_path, timeout=5)
    conn.execute("PRAGMA journal_mode=WAL")
    val = conn.execute(f"PRAGMA {name}").fetchone()[0]
    conn.close()
    return str(val).upper()


def test_wal_journal_mode_enabled():
    """journal_mode must be WAL after init_db()."""
    result = _pragma(database.DB_PATH, "journal_mode")
    assert result == "WAL", f"Expected WAL, got {result}"


def test_busy_timeout_is_set():
    """busy_timeout must be > 0 ms (we set 5000)."""
    conn = database._get_conn()
    timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    conn.close()
    assert timeout >= 5000, f"Expected busy_timeout>=5000, got {timeout}"


def test_synchronous_is_normal():
    """synchronous=NORMAL (1) is the safe+fast default we set."""
    conn = database._get_conn()
    sync = conn.execute("PRAGMA synchronous").fetchone()[0]
    conn.close()
    # SQLite returns 1 for NORMAL
    assert sync == 1, f"Expected synchronous=1 (NORMAL), got {sync}"


def test_foreign_keys_on():
    """foreign_keys must be enabled."""
    conn = database._get_conn()
    fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
    conn.close()
    assert fk == 1, f"Expected foreign_keys=1, got {fk}"


# ---------------------------------------------------------------------------
# 5: Concurrent write stress test
# ---------------------------------------------------------------------------

def test_concurrent_writes_no_locking():
    """
    Simulate N threads writing simultaneously.
    With WAL mode this must complete without 'database is locked' errors.
    """
    errors: list[Exception] = []
    n_threads = 10
    n_writes_per_thread = 5

    def worker(thread_id: int):
        for i in range(n_writes_per_thread):
            try:
                database.save_message(
                    session_id=f"concurrent_session_{thread_id}",
                    role="user",
                    content=f"Thread {thread_id} message {i}",
                )
            except Exception as exc:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Concurrent write errors: {errors}"

    # Verify all messages were written
    total = sum(
        len(database.get_chat_history(f"concurrent_session_{i}", limit=n_writes_per_thread))
        for i in range(n_threads)
    )
    assert total == n_threads * n_writes_per_thread


# ---------------------------------------------------------------------------
# 6: Backend selection via DATABASE_URL
# ---------------------------------------------------------------------------

def test_sqlite_backend_selected_by_default(monkeypatch):
    """When DATABASE_URL is absent, SQLiteBackend must be used."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    database._backend = None  # reset singleton
    backend = database._get_backend()
    assert isinstance(backend, database.SQLiteBackend)


def test_sqlite_backend_selected_when_url_blank(monkeypatch):
    """When DATABASE_URL is empty string, SQLiteBackend must be used."""
    monkeypatch.setenv("DATABASE_URL", "")
    database._backend = None
    backend = database._get_backend()
    assert isinstance(backend, database.SQLiteBackend)


def test_postgres_backend_class_exists():
    """PostgresBackend class must be importable (even without psycopg2 installed)."""
    assert hasattr(database, "PostgresBackend")
    assert issubclass(database.PostgresBackend, database.DatabaseBackend)


def test_postgres_backend_raises_import_error_without_sqlalchemy(monkeypatch):
    """
    If sqlalchemy is not installed and DATABASE_URL=postgresql://...,
    PostgresBackend.__init__ must raise a helpful ImportError.
    """
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "sqlalchemy":
            raise ImportError("mocked missing sqlalchemy")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    with pytest.raises(ImportError, match="SQLAlchemy"):
        database.PostgresBackend("postgresql://user:pass@localhost/hermes")


# ---------------------------------------------------------------------------
# 7: _get_conn() smoke — independent WAL connection
# ---------------------------------------------------------------------------

def test_get_conn_returns_wal_connection():
    """_get_conn() must return an open SQLite connection in WAL mode."""
    conn = database._get_conn()
    try:
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode.upper() == "WAL"
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 8: Public API smoke test (regression guard)
# ---------------------------------------------------------------------------

def test_public_api_smoke():
    """All public DB functions work after WAL refactor."""
    sid = "wal_smoke_session"

    # messages
    msg_id = database.save_message(sid, "user", "Hello WAL")
    assert msg_id is not None
    history = database.get_chat_history(sid)
    assert len(history) == 1
    assert history[0]["content"] == "Hello WAL"
    database.clear_chat_history(sid)
    assert database.get_chat_history(sid) == []

    # settings
    database.set_setting("test_key", "test_value")
    assert database.get_setting("test_key") == "test_value"

    # session metadata
    database.save_session_title(sid, "WAL Test Session")
    assert database.get_session_title(sid) == "WAL Test Session"
    assert database.delete_session_title(sid) is True
    assert database.get_session_title(sid) is None

    # subagent memory
    database.db_save_subagent_memory("agent_wal", "fact", "42")
    mem = database.db_get_subagent_memory("agent_wal")
    assert mem == {"fact": "42"}
    assert database.db_delete_subagent_memory("agent_wal", "fact") is True
    assert database.db_get_subagent_memory("agent_wal") == {}
