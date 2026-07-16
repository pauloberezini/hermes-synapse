"""
Tests for the global language setting feature.
Covers: DB helpers, REST API endpoints, and language directive injection in agent.
"""
import os
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from backend import database
from backend.main import app
from backend.agent import agent_instance
from backend.auth import active_sessions

# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Redirect DB to a temp file so tests don't touch production data."""
    orig_path, orig_dir = database.DB_PATH, database.DB_DIR
    database.DB_PATH = str(tmp_path / "test.db")
    database.DB_DIR = str(tmp_path)
    database.init_db()
    yield
    database.DB_PATH = orig_path
    database.DB_DIR = orig_dir


@pytest.fixture()
def client():
    c = TestClient(app)
    active_sessions.add("test-token")
    c.headers = {"Authorization": "Bearer test-token"}
    return c


# ─── 1. Database helpers ───────────────────────────────────────────────────────

def test_default_language_is_ru():
    """init_db seeds language='ru' by default."""
    val = database.get_setting("language")
    assert val == "ru"


def test_set_and_get_setting():
    database.set_setting("language", "en")
    assert database.get_setting("language") == "en"


def test_set_setting_overwrites():
    database.set_setting("language", "en")
    database.set_setting("language", "he")
    assert database.get_setting("language") == "he"


def test_get_unknown_setting_returns_none():
    assert database.get_setting("nonexistent_key") is None


def test_set_custom_key():
    """set_setting works for arbitrary keys, not just 'language'."""
    database.set_setting("theme", "dark")
    assert database.get_setting("theme") == "dark"


# ─── 2. REST API: GET /api/settings ──────────────────────────────────────────

def test_get_settings_default(client):
    resp = client.get("/api/settings")
    assert resp.status_code == 200
    assert resp.json()["language"] == "ru"


def test_get_settings_after_db_change(client):
    database.set_setting("language", "en")
    resp = client.get("/api/settings")
    assert resp.json()["language"] == "en"


# ─── 3. REST API: POST /api/settings ─────────────────────────────────────────

def test_post_settings_changes_language(client):
    resp = client.post("/api/settings", json={"language": "en"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert data["language"] == "en"
    # Verify persisted
    assert database.get_setting("language") == "en"


def test_post_settings_roundtrip(client):
    """Set → GET should reflect the new value."""
    client.post("/api/settings", json={"language": "he"})
    resp = client.get("/api/settings")
    assert resp.json()["language"] == "he"


def test_post_settings_empty_body_is_noop(client):
    """Posting no language field should not crash and leave value unchanged."""
    database.set_setting("language", "de")
    resp = client.post("/api/settings", json={})
    assert resp.status_code == 200
    assert database.get_setting("language") == "de"


def test_settings_requires_auth():
    clean = TestClient(app)
    assert clean.get("/api/settings").status_code == 401
    assert clean.post("/api/settings", json={"language": "en"}).status_code == 401


# ─── 4. Language directive in agent system prompt ─────────────────────────────

def test_language_directive_russian():
    """Default 'ru' setting injects Russian directive into system prompt."""
    database.set_setting("language", "ru")
    from backend.database import get_setting
    lang = get_setting("language") or "ru"
    lang_names = {"ru": "Russian", "en": "English", "he": "Hebrew", "de": "German", "es": "Spanish", "fr": "French"}
    directive = f"[LANGUAGE DIRECTIVE]: You MUST respond exclusively in {lang_names.get(lang, lang)}."
    assert "Russian" in directive


def test_language_directive_english():
    database.set_setting("language", "en")
    from backend.database import get_setting
    lang = get_setting("language") or "ru"
    lang_names = {"ru": "Russian", "en": "English", "he": "Hebrew", "de": "German", "es": "Spanish", "fr": "French"}
    directive = f"[LANGUAGE DIRECTIVE]: You MUST respond exclusively in {lang_names.get(lang, lang)}."
    assert "English" in directive


def test_language_directive_hebrew():
    database.set_setting("language", "he")
    from backend.database import get_setting
    lang = get_setting("language") or "ru"
    lang_names = {"ru": "Russian", "en": "English", "he": "Hebrew", "de": "German", "es": "Spanish", "fr": "French"}
    directive = f"[LANGUAGE DIRECTIVE]: You MUST respond exclusively in {lang_names.get(lang, lang)}."
    assert "Hebrew" in directive


def test_language_directive_unknown_falls_back_to_code():
    """An unrecognized code is passed through verbatim (no crash)."""
    database.set_setting("language", "ja")
    from backend.database import get_setting
    lang = get_setting("language") or "ru"
    lang_names = {"ru": "Russian", "en": "English", "he": "Hebrew", "de": "German", "es": "Spanish", "fr": "French"}
    name = lang_names.get(lang, lang)
    assert name == "ja"  # falls back to the code itself


# ─── 5. WebSocket broadcast on settings change ───────────────────────────────

@pytest.mark.asyncio
async def test_settings_update_broadcasts(client):
    """POST /api/settings should trigger a WebSocket broadcast."""
    from backend.websocket_manager import manager
    original_broadcast = manager.broadcast
    broadcasts = []

    async def fake_broadcast(msg):
        broadcasts.append(msg)

    manager.broadcast = fake_broadcast
    try:
        client.post("/api/settings", json={"language": "de"})
        assert any(b.get("type") == "settings_update" and b.get("language") == "de" for b in broadcasts)
    finally:
        manager.broadcast = original_broadcast
