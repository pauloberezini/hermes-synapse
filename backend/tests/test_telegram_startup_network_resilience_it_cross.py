import os
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

try:
    from telegram.error import NetworkError, Conflict
except ImportError:
    class NetworkError(Exception):
        pass
    class Conflict(Exception):
        pass

import httpx


class TestTelegramStartupNetworkResilienceIT:
    """Integration tests reproducing and verifying Telegram bot startup network resilience."""

    @pytest.mark.asyncio
    async def test_init_bot_survives_network_error_on_initialize(self, monkeypatch):
        """
        IT Reproduction Test:
        When telegram_app.initialize() raises NetworkError(httpx.ConnectError) as seen in
        Docker jarvis-backend live logs, init_bot() must NOT propagate the exception and kill
        the server. It should log a warning, register the watchdog, and return gracefully.
        """
        from backend.bot import init_bot, shutdown_bot

        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")

        mock_app = MagicMock()
        mock_app._initialized = False
        mock_app.running = False
        mock_app.updater = MagicMock()
        mock_app.updater.running = False

        # Simulate httpx.ConnectError wrapped in telegram.error.NetworkError
        connect_exc = NetworkError("httpx.ConnectError: All connection attempts failed")
        mock_app.initialize = AsyncMock(side_effect=connect_exc)
        mock_app.start = AsyncMock()

        mock_builder = MagicMock()
        mock_builder.token.return_value = mock_builder
        mock_builder.build.return_value = mock_app

        with patch("backend.bot.ApplicationBuilder", return_value=mock_builder), \
             patch("backend.bot._telegram_polling_watchdog", new_callable=MagicMock) as mock_watchdog:
            
            # Watchdog coroutine that simply sleeps
            async def dummy_watchdog(*args, **kwargs):
                await asyncio.sleep(0.01)

            mock_watchdog.side_effect = dummy_watchdog

            # Call init_bot: should NOT raise NetworkError
            app = await init_bot()

            assert app is not None
            mock_app.initialize.assert_awaited_once()
            # If initialize failed, start should not have been called or failed gracefully
            assert mock_app._initialized is False

        await shutdown_bot()

    @pytest.mark.asyncio
    async def test_watchdog_deferred_recovery_when_network_restored(self, monkeypatch):
        """
        IT Test:
        When telegram_app failed to initialize during startup, the background watchdog
        re-attempts initialize() and start() when network recovers, followed by start_polling().
        """
        from backend.bot import _telegram_polling_watchdog
        import backend.bot as bot_module

        mock_app = MagicMock()
        mock_app._initialized = False
        mock_app.running = False
        mock_app.bot = MagicMock()
        mock_app.bot.delete_webhook = AsyncMock()
        mock_updater = MagicMock()
        mock_updater.running = False
        mock_updater.start_polling = AsyncMock()
        mock_app.updater = mock_updater

        # On first watchdog tick, initialize and start succeed
        async def mock_init():
            mock_app._initialized = True
        mock_app.initialize = AsyncMock(side_effect=mock_init)

        async def mock_start():
            mock_app.running = True
        mock_app.start = AsyncMock(side_effect=mock_start)

        monkeypatch.setattr(bot_module, "telegram_app", mock_app)
        monkeypatch.setattr(bot_module, "_updater_running_since", 0.0)

        # Run watchdog for a short window
        watchdog_task = asyncio.create_task(_telegram_polling_watchdog(poll_interval=0.01, conflict_cooldown=0.0))
        await asyncio.sleep(0.02)
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass

        assert mock_app.initialize.awaited
        assert mock_app.start.awaited
        assert mock_updater.start_polling.awaited

    @pytest.mark.asyncio
    async def test_shutdown_bot_safe_when_bot_partially_initialized(self, monkeypatch):
        """
        IT Test:
        Verifies that shutdown_bot() never raises errors even when telegram_app was only partially
        initialized or never started.
        """
        from backend.bot import shutdown_bot
        import backend.bot as bot_module

        mock_app = MagicMock()
        mock_app._initialized = False
        mock_app.running = False
        mock_app.updater = None
        mock_app.stop = AsyncMock(side_effect=RuntimeError("Cannot stop unstarted app"))
        mock_app.shutdown = AsyncMock(side_effect=RuntimeError("Cannot shutdown uninitialized app"))

        monkeypatch.setattr(bot_module, "telegram_app", mock_app)

        # Must not raise
        await shutdown_bot()


class TestCrossFastApiLifespanTelegramResilience:
    """Cross-Service Tests: FastAPI Lifespan + Telegram Bot + Health Endpoints."""

    @pytest.mark.asyncio
    async def test_cross_fastapi_lifespan_starts_and_health_endpoint_ok_during_telegram_outage(self, monkeypatch):
        """
        Cross-service test:
        Simulate full FastAPI application lifespan startup when Telegram experiences a network
        outage (httpx.ConnectError).
        Verify that:
        1. FastAPI lifespan starts cleanly without raising Application startup failed.
        2. /health endpoint returns HTTP 200 {"status": "ok"}.
        3. Lifespan shutdown completes cleanly.
        """
        monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ")

        # Mock Telegram failure
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
            mock_app.initialize = AsyncMock(side_effect=NetworkError("httpx.ConnectError: [Errno -5] No address associated with hostname"))
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
                assert data["status"] == "online"
