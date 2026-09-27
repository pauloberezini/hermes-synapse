"""
==============================================================================
IT & Cross-Service Regression Suite: Docker Backend Live Log Issues (2026-09-06)
==============================================================================
Reproduces and verifies all issues observed in jarvis-backend Docker logs on 2026-09-06:

ISSUE-1 (IT):    Telegram Polling Network Flap Log Flood (`telegram.ext.Updater`):
                 Transient network / DNS drops ([Errno -5] No address associated with hostname)
                 cause PTB's internal updater loop to spam multi-page tracebacks at ERROR level.
                 Verified: Filter downgrades to WARNING, strips traceback, and rate-limits.

ISSUE-2 (IT):    Preservation of genuine errors:
                 Non-network application or syntax errors retain ERROR level and full traceback.

ISSUE-3 (IT):    Obsidian Offline Graceful Fallback (`hermes.obsidian`):
                 When Obsidian Local REST API is unreachable/offline (All connection attempts failed),
                 `list_notes` and `read_note` fall back to RAG index seamlessly without emitting
                 repetitive WARNING logs.

ISSUE-4 (Cross): Background Scheduler Alert Resilience (`_send_telegram_alert`):
                 Transient network errors during scheduled alert dispatch are handled with
                 a single concise WARNING rather than an unhandled ERROR.

ISSUE-5 (Cross): FastAPI Lifecycle + Obsidian + Telegram Resilience:
                 Full API endpoints (/api/status, /api/obsidian/status, /api/obsidian/notes)
                 remain healthy (200 OK) during simulated network flaps and offline Obsidian.
==============================================================================
"""

import sys
import logging
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

import httpx

# Imports from backend
from backend.bot import (
    TelegramPollingNetworkFilter,
    setup_telegram_logging_filters,
    telegram_error_handler,
)
from backend import obsidian
from backend import scheduler
import backend.main as main_mod


# ==============================================================================
# ISSUE-1 (IT): Telegram Polling Network Filter & Traceback Suppression
# ==============================================================================

def test_telegram_polling_network_filter_downgrades_and_suppresses_traceback_it():
    """IT: Verify transient DNS/network exceptions are downgraded to WARNING and traceback is stripped."""
    filt = TelegramPollingNetworkFilter(throttle_interval_seconds=60.0)

    logger = logging.getLogger("telegram.ext.test_updater")
    logger.filters.clear()
    logger.addFilter(filt)

    # Simulate PTB Updater network error: [Errno -5] No address associated with hostname
    try:
        raise httpx.ConnectError("[Errno -5] No address associated with hostname")
    except Exception as exc:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="telegram.ext.Updater",
        level=logging.ERROR,
        pathname="updater.py",
        lineno=100,
        msg="Exception happened while polling for updates.",
        args=(),
        exc_info=exc_info,
    )

    should_log = filt.filter(record)
    assert should_log is True, "First network error within window must be logged"
    assert record.levelno == logging.WARNING, "Log level must be downgraded from ERROR to WARNING"
    assert record.levelname == "WARNING"
    assert record.exc_info is None, "exc_info traceback must be stripped to prevent multi-line log spam"
    assert "Telegram polling transient network issue" in record.msg
    assert "No address associated with hostname" in record.msg


def test_telegram_polling_network_filter_rate_limits_repetitive_errors_it(monkeypatch):
    """IT: Verify repetitive transient network errors within throttle window are suppressed."""
    current_time = 1000.0

    def mock_time():
        return current_time

    filt = TelegramPollingNetworkFilter(throttle_interval_seconds=60.0)
    monkeypatch.setattr("time.time", mock_time)

    def create_network_record():
        try:
            raise httpx.ConnectError("[Errno -5] No address associated with hostname")
        except Exception:
            return logging.LogRecord(
                name="telegram.ext.Updater",
                level=logging.ERROR,
                pathname="updater.py",
                lineno=100,
                msg="Exception happened while polling for updates.",
                args=(),
                exc_info=sys.exc_info(),
            )

    # 1. First event -> Allowed
    rec1 = create_network_record()
    assert filt.filter(rec1) is True

    # 2. Next 3 events within 60s -> Suppressed
    current_time += 5.0
    assert filt.filter(create_network_record()) is False
    current_time += 5.0
    assert filt.filter(create_network_record()) is False
    current_time += 5.0
    assert filt.filter(create_network_record()) is False

    # 3. After 60s has passed -> Allowed with count of suppressed occurrences
    current_time += 50.0  # now 65s since first log
    rec2 = create_network_record()
    assert filt.filter(rec2) is True
    assert "suppressed 3 repetitive errors" in rec2.msg


# ==============================================================================
# ISSUE-2 (IT): Preservation of Non-Network Errors
# ==============================================================================

def test_telegram_polling_network_filter_preserves_genuine_errors_it():
    """IT: Genuine non-network application/runtime exceptions must retain ERROR level and traceback."""
    filt = TelegramPollingNetworkFilter(throttle_interval_seconds=60.0)

    try:
        raise ValueError("Invalid bot authentication token syntax")
    except Exception:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="telegram.ext.Updater",
        level=logging.ERROR,
        pathname="updater.py",
        lineno=120,
        msg="Exception happened while polling for updates.",
        args=(),
        exc_info=exc_info,
    )

    should_log = filt.filter(record)
    assert should_log is True
    assert record.levelno == logging.ERROR, "Non-network errors must remain ERROR"
    assert record.levelname == "ERROR"
    assert record.exc_info is not None, "exc_info traceback must NOT be stripped for real errors"


@pytest.mark.asyncio
async def test_telegram_error_handler_network_warning_it(caplog):
    """IT: Verify telegram_error_handler logs network errors as warning without crashing."""
    from telegram.error import NetworkError

    class DummyContext:
        error = NetworkError("httpx.ConnectError: [Errno -5] No address associated with hostname")

    with caplog.at_level(logging.WARNING):
        await telegram_error_handler(None, DummyContext())

    assert any(
        "Telegram network warning" in r.message and r.levelno == logging.WARNING
        for r in caplog.records
    )


# ==============================================================================
# ISSUE-3 (IT): Obsidian Offline Graceful Fallback & Clean Logging
# ==============================================================================

@pytest.mark.asyncio
async def test_obsidian_list_notes_offline_rag_fallback_it(caplog):
    """IT: When Obsidian app is offline, list_notes falls back to RAG without WARNING logs."""
    fake_rag_docs = [
        {"note_path": "Daily/2026-09-06.md", "title": "Daily Note"},
        {"note_path": "Projects/Jarvis.md", "title": "Jarvis Project"},
    ]

    with patch("backend.obsidian._get_api_key", return_value="configured-test-key"), \
         patch("backend.obsidian._client") as mock_client_func, \
         patch("backend.rag.list_documents", return_value=fake_rag_docs):

        client_inst = AsyncMock()
        client_inst.get.side_effect = httpx.ConnectError("All connection attempts failed")
        mock_client_func.return_value.__aenter__.return_value = client_inst

        with caplog.at_level(logging.WARNING, logger="hermes.obsidian"):
            notes = await obsidian.list_notes()

        # 1. Notes returned from RAG
        assert "Daily/2026-09-06.md" in notes
        assert "Projects/Jarvis.md" in notes

        # 2. No WARNING logs from hermes.obsidian
        obsidian_warnings = [r for r in caplog.records if r.name == "hermes.obsidian" and r.levelno >= logging.WARNING]
        assert len(obsidian_warnings) == 0, f"Expected 0 warnings when Obsidian is offline, got: {obsidian_warnings}"


@pytest.mark.asyncio
async def test_obsidian_read_note_offline_rag_fallback_it(caplog):
    """IT: When Obsidian app is offline, read_note falls back to RAG without WARNING logs."""
    with patch("backend.obsidian._get_api_key", return_value="configured-test-key"), \
         patch("backend.obsidian._client") as mock_client_func, \
         patch("backend.rag.get_note_text_by_path", return_value="# Note from RAG Cache"):

        client_inst = AsyncMock()
        client_inst.get.side_effect = httpx.ConnectError("All connection attempts failed")
        mock_client_func.return_value.__aenter__.return_value = client_inst

        with caplog.at_level(logging.WARNING, logger="hermes.obsidian"):
            content = await obsidian.read_note("Projects/Jarvis.md")

        assert content == "# Note from RAG Cache"
        obsidian_warnings = [r for r in caplog.records if r.name == "hermes.obsidian" and r.levelno >= logging.WARNING]
        assert len(obsidian_warnings) == 0, f"Expected 0 warnings when Obsidian is offline, got: {obsidian_warnings}"


# ==============================================================================
# ISSUE-4 (Cross): Scheduler Telegram Alert Transient Network Resilience
# ==============================================================================

@pytest.mark.asyncio
async def test_scheduler_send_telegram_alert_transient_network_error_cross(caplog):
    """Cross: Scheduler _send_telegram_alert logs a concise WARNING on network outage rather than ERROR."""
    from telegram.error import NetworkError

    mock_bot = AsyncMock()
    mock_bot.send_message.side_effect = NetworkError("httpx.ConnectError: [Errno -5] No address associated with hostname")

    mock_app = MagicMock()
    mock_app.bot = mock_bot

    with patch("backend.bot.telegram_app", mock_app), \
         caplog.at_level(logging.WARNING):

        await scheduler._send_telegram_alert("123456", "Test alert message")

        # Must log WARNING, not ERROR
        network_warnings = [
            r for r in caplog.records
            if "Telegram alert transient network issue" in r.message and r.levelno == logging.WARNING
        ]
        assert len(network_warnings) == 1, "Expected single WARNING for transient alert failure"

        errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(errors) == 0, f"Expected no ERROR logs, got: {errors}"


# ==============================================================================
# ISSUE-5 (Cross): FastAPI Endpoints Resilience with Offline Obsidian & Net Flap
# ==============================================================================

def test_fastapi_obsidian_and_status_endpoints_cross():
    """Cross: Ensure /api/obsidian/status and /api/obsidian/notes return HTTP 200 when Obsidian is offline."""
    client = TestClient(main_mod.app)
    headers = {"Authorization": "Bearer dev_master_token"}

    fake_rag_docs = [{"note_path": "Note1.md", "title": "Note 1"}]

    with patch("backend.obsidian.is_reachable", AsyncMock(return_value=False)), \
         patch("backend.obsidian._get_api_key", return_value="configured-key"), \
         patch("backend.rag.list_documents", return_value=fake_rag_docs), \
         patch("backend.obsidian.list_notes", AsyncMock(return_value=["Note1.md"])):

        # 1. /api/obsidian/status returns 200 OK with reachable=False and offline explanation
        resp = client.get("/api/obsidian/status", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["reachable"] is False
        assert data["knowledge_ok"] is True
        assert "Knowledge base online" in data["message"]

        # 2. /api/obsidian/notes returns 200 OK serving RAG notes
        resp_notes = client.get("/api/obsidian/notes", headers=headers)
        assert resp_notes.status_code == 200
        notes_data = resp_notes.json()
        assert "notes" in notes_data
        assert "Note1.md" in notes_data["notes"]

        # 3. /api/status returns 200 OK
        resp_status = client.get("/api/status")
        assert resp_status.status_code == 200
        status_data = resp_status.json()
        assert status_data["status"] == "online"
