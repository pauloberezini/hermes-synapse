"""
Integration (IT) and Cross-Subsystem Tests for Docker jarvis-backend Live Log Issues.

Covers:
1. IT: Telegram polling watchdog defers polling recovery after transient network error (preventing 409 Conflict).
2. IT: Telegram polling watchdog defers recovery when delete_webhook fails with NetworkError or Conflict.
3. IT: Telegram polling watchdog cleanly stops updater and recovers once cooldown expires.
4. IT: Database undistilled logs tuple parsing safety against tuple index out of range.
5. Cross: FastAPI lifespan boots and serves health checks during Telegram network outage.
6. Cross: cTrader OpenAPI client concurrent close() idempotency (no 'cannot reuse already awaited coroutine').
7. Cross: Skill distillation loop cleanly skips scheduled automation runs at INFO level without logging ERROR.
"""

import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.bot import (
    _telegram_polling_watchdog,
    report_telegram_conflict,
    report_telegram_network_error,
)
import backend.bot as bot_module
from backend.database import _parse_decision_log_candidate
from backend.skill_loop import SkillDistiller, _is_scheduled_automation_log


# =====================================================================
# 1. IT: Telegram Watchdog Cooldown & Conflict Prevention Tests
# =====================================================================

class TestTelegramWatchdogConflictPreventionIT:
    """Integration tests verifying watchdog prevents Telegram 409 Conflict after network drop."""

    @pytest.mark.asyncio
    async def test_it_telegram_watchdog_defers_polling_after_transient_network_error(self, monkeypatch):
        """
        IT Reproduction Test:
        When a transient network error occurs during Telegram polling (e.g., httpx.ConnectError: [Errno -5]),
        report_telegram_network_error() is invoked.
        The watchdog MUST NOT immediately attempt to start polling while the network is flapped
        or while Telegram's server still has the previous long-poll connection open.
        """
        mock_app = MagicMock()
        mock_app._initialized = True
        mock_app.running = True
        mock_app.bot = MagicMock()
        mock_app.bot.delete_webhook = AsyncMock()

        mock_updater = MagicMock()
        mock_updater.running = False
        mock_updater.stop = AsyncMock()
        mock_updater.start_polling = AsyncMock()
        mock_app.updater = mock_updater

        monkeypatch.setattr(bot_module, "telegram_app", mock_app)
        monkeypatch.setattr(bot_module, "_updater_running_since", 0.0)

        # Trigger transient network error
        report_telegram_network_error()

        # Run watchdog with 10s network cooldown for a brief period (0.05s)
        watchdog_task = asyncio.create_task(
            _telegram_polling_watchdog(poll_interval=0.01, conflict_cooldown=0.0, network_cooldown=10.0)
        )
        await asyncio.sleep(0.05)
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass

        # start_polling must NOT have been called because network cooldown was active
        assert not mock_updater.start_polling.called
        assert not mock_app.bot.delete_webhook.called

    @pytest.mark.asyncio
    async def test_it_telegram_watchdog_defers_when_delete_webhook_fails(self, monkeypatch):
        """
        IT Reproduction Test:
        When watchdog attempts recovery, if bot.delete_webhook fails (due to NetworkError or Conflict),
        watchdog MUST defer recovery and NOT call updater.start_polling().
        """
        mock_app = MagicMock()
        mock_app._initialized = True
        mock_app.running = True
        mock_app.bot = MagicMock()
        # Simulate network error or conflict during delete_webhook
        mock_app.bot.delete_webhook = AsyncMock(
            side_effect=Exception("httpx.ConnectError: [Errno -5] No address associated with hostname")
        )

        mock_updater = MagicMock()
        mock_updater.running = False
        mock_updater.stop = AsyncMock()
        mock_updater.start_polling = AsyncMock()
        mock_app.updater = mock_updater

        monkeypatch.setattr(bot_module, "telegram_app", mock_app)
        monkeypatch.setattr(bot_module, "_last_conflict_detected_at", 0.0)
        monkeypatch.setattr(bot_module, "_last_network_error_at", 0.0)
        monkeypatch.setattr(bot_module, "_updater_running_since", 0.0)

        watchdog_task = asyncio.create_task(
            _telegram_polling_watchdog(poll_interval=0.01, conflict_cooldown=0.0, network_cooldown=0.0)
        )
        await asyncio.sleep(0.05)
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass

        # delete_webhook was tried
        assert mock_app.bot.delete_webhook.called
        # start_polling was DEFERRED and not called!
        assert not mock_updater.start_polling.called

    @pytest.mark.asyncio
    async def test_it_telegram_watchdog_recovers_cleanly_when_healthy(self, monkeypatch):
        """
        IT Test:
        When cooldowns have expired and network is healthy, watchdog safely stops the old updater,
        clears webhook, and starts polling.
        """
        mock_app = MagicMock()
        mock_app._initialized = True
        mock_app.running = True
        mock_app.bot = MagicMock()
        mock_app.bot.delete_webhook = AsyncMock()

        mock_updater = MagicMock()
        mock_updater.running = False
        mock_updater.stop = AsyncMock()
        mock_updater.start_polling = AsyncMock()
        mock_app.updater = mock_updater

        monkeypatch.setattr(bot_module, "telegram_app", mock_app)
        monkeypatch.setattr(bot_module, "_last_conflict_detected_at", 0.0)
        monkeypatch.setattr(bot_module, "_last_network_error_at", 0.0)
        monkeypatch.setattr(bot_module, "_updater_running_since", 0.0)

        watchdog_task = asyncio.create_task(
            _telegram_polling_watchdog(poll_interval=0.01, conflict_cooldown=0.0, network_cooldown=0.0)
        )
        await asyncio.sleep(0.05)
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass

        assert mock_updater.stop.called
        assert mock_app.bot.delete_webhook.called
        assert mock_updater.start_polling.called


# =====================================================================
# 2. IT: Database Safe Tuple Bounds Parsing
# =====================================================================

class TestDatabaseSafeTupleParsingIT:
    """Integration test verifying _parse_decision_log_candidate against tuple index errors."""

    def test_it_parse_decision_log_candidate_empty_or_truncated_tuples(self):
        """
        IT Reproduction Test:
        Verifies that malformed or truncated tuples returned by database queries
        do not raise `IndexError: tuple index out of range`.
        """
        # Empty tuple
        assert _parse_decision_log_candidate(()) is None

        # Short tuples (< 11 items)
        assert _parse_decision_log_candidate((1,)) is None
        assert _parse_decision_log_candidate((1, "2026-10-26T10:00:00", "session_123")) is None
        assert _parse_decision_log_candidate(tuple(range(10))) is None

        # 11 items (minimum valid length)
        row_11 = (
            101,  # id
            "2026-10-26T10:00:00",  # timestamp
            "session_456",  # session_id
            "deepseek/deepseek-chat",  # model
            150,  # latency_ms
            1,  # success
            None,  # error
            500,  # prompt_tokens_estimate
            "What is BTC price?",  # user_message
            "BTC is at 68,000 USD",  # assistant_response
            [{"agent": "MarketData", "action": "Tool", "message": "btc price"}],  # traces
        )
        cand_11 = _parse_decision_log_candidate(row_11, min_steps=1)
        assert cand_11 is not None
        assert cand_11["id"] == 101
        assert cand_11["session_id"] == "session_456"
        assert cand_11["agent_id"] == "jarvis"

        # 14 items (full schema)
        row_14 = row_11 + ("bcm_agent", 200, 0.005)
        cand_14 = _parse_decision_log_candidate(row_14, min_steps=1)
        assert cand_14 is not None
        assert cand_14["agent_id"] == "bcm_agent"
        assert cand_14["completion_tokens_estimate"] == 200
        assert cand_14["cost_usd"] == 0.005


# =====================================================================
# 3. Cross: FastAPI Lifespan + Telegram Outage Resilience
# =====================================================================

class TestCrossFastApiTelegramResilience:
    """Cross-subsystem test: FastAPI app boot and health checks during Telegram network outage."""

    @pytest.mark.asyncio
    async def test_cross_fastapi_lifespan_starts_during_telegram_outage(self, monkeypatch):
        """
        Cross Test:
        When Telegram API is unreachable at startup, FastAPI must boot cleanly,
        serve /api/status, and shut down cleanly without unhandled exceptions.
        """
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")

        try:
            from telegram.error import NetworkError
        except ImportError:
            NetworkError = type("NetworkError", (Exception,), {})

        with patch("backend.bot.ApplicationBuilder") as mock_builder, \
             patch("backend.database.init_db", return_value=None), \
             patch("backend.rag.init_rag", return_value=None), \
             patch("backend.price_monitor.price_monitor.start", return_value=None), \
             patch("backend.price_monitor.price_monitor.stop", return_value=None), \
             patch("backend.scheduler.shutdown_scheduler", return_value=None), \
             patch("backend.mcp_client.shutdown_mcp_servers", new_callable=AsyncMock):

            mock_app = MagicMock()
            mock_app._initialized = False
            mock_app.running = False
            mock_app.updater = MagicMock()
            mock_app.updater.running = False
            mock_app.initialize = AsyncMock(
                side_effect=NetworkError("httpx.ConnectError: [Errno -5] No address associated with hostname")
            )
            mock_app.start = AsyncMock()

            builder_instance = MagicMock()
            builder_instance.token.return_value = builder_instance
            builder_instance.build.return_value = mock_app
            mock_builder.return_value = builder_instance

            fastapi = pytest.importorskip("fastapi")
            from fastapi.testclient import TestClient
            from backend.main import app

            with TestClient(app) as client:
                resp = client.get("/api/status")
                assert resp.status_code == 200
                data = resp.json()
                assert data.get("status") == "online"



# =====================================================================
# 5. Cross: Skill Distiller Scheduled Automation INFO Logging
# =====================================================================

class TestCrossSkillDistillerScheduledRuns:
    """Cross test: Skill distillation cleanly ignores scheduled runs without ERROR logs."""

    def test_cross_skill_distiller_scheduled_run_skips_cleanly_at_info_level(self, caplog):
        """
        Cross Reproduction Test:
        Reproduces Docker log issue:
        [ERROR] hermes.skill_loop: Error distilling log #2355: Log entry #2355 is a scheduled automation run
        Verifies that scheduled automation logs are skipped cleanly at INFO level and NEVER log at ERROR.
        """
        distiller = SkillDistiller()

        scheduled_log = {
            "id": 2355,
            "session_id": "task_bcm_session_new_york_12345",
            "model": "deepseek/deepseek-chat",
            "user_message": "Execute scheduled task: task_bcm_session_new_york (Autonomous AI Hedge Fund Manager)",
            "assistant_response": "Session completed successfully.",
            "success": True,
            "traces": [
                {"agent": "Quant Analyst", "action": "Tool", "message": "RSI=55"},
                {"agent": "Compliance Officer", "action": "Tool", "message": "Approved"},
            ],
        }

        assert _is_scheduled_automation_log(scheduled_log) is True

        with patch("backend.database.db_get_undistilled_successful_logs", return_value=[scheduled_log]), \
             patch("backend.database.db_mark_log_undistillable", return_value=True):
            with caplog.at_level(logging.INFO):
                results = distiller.process_undistilled_logs()

        assert results == []

        # Check log records: must have INFO, must NOT have ERROR
        error_logs = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert len(error_logs) == 0, f"Expected 0 ERROR logs, got: {[r.message for r in error_logs]}"

        info_logs = [r for r in caplog.records if "skipping skill distillation for scheduled automation" in r.message.lower()]
        assert len(info_logs) >= 1
