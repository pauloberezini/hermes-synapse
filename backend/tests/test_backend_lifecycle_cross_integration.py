import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend import scheduler
from backend import price_monitor
from backend import rag
from backend.main import lifespan, app


@pytest.mark.asyncio
async def test_full_application_lifecycle_graceful_shutdown():
    """Cross Test: Run the full FastAPI lifespan lifecycle (startup -> running -> shutdown)
    and verify that all background tasks, scheduler, and monitoring loops terminate cleanly
    without raising unhandled exceptions or CancelledError tracebacks.
    """
    with patch("backend.main.init_bot", new_callable=AsyncMock) as mock_init_bot, \
         patch("backend.main.shutdown_bot", new_callable=AsyncMock) as mock_shutdown_bot, \
         patch("backend.mcp_client.init_mcp_servers", new_callable=AsyncMock), \
         patch("backend.mcp_client.shutdown_mcp_servers", new_callable=AsyncMock), \
         patch("backend.rag.raw_init_rag"), \
         patch("backend.obsidian.is_reachable", new_callable=AsyncMock, return_value=False):
        
        mock_init_bot.return_value = MagicMock()
        
        # Test startup phase
        async with lifespan(app):
            # Verify subsystems are active
            assert price_monitor.price_monitor.monitor_task is not None
            assert not price_monitor.price_monitor.monitor_task.done()

            # Schedule a test cron job to verify scheduler operation
            job_id = scheduler.add_cron_task(
                cron_expr="*/5 * * * *",
                label="Lifecycle Test Cron",
                chat_id="test_chat",
                prompt="test prompt"
            )
            assert job_id is not None
            
            # Let the event loop cycle briefly
            await asyncio.sleep(0.05)

        # Allow task cancellation to settle in loop
        await asyncio.sleep(0.01)

        # After exiting lifespan context (shutdown complete):
        assert price_monitor.price_monitor.monitor_task.done()
        mock_shutdown_bot.assert_awaited_once()


@pytest.mark.asyncio
async def test_cross_subsystem_scheduler_shutdown_cleanup():
    """Cross Test: Verify that starting skill distillation, RSS poller, watcher, and BCM loops
    can be cleanly torn down via shutdown_scheduler() with all tasks properly cancelled.
    """
    with patch("backend.skill_loop.get_skill_distiller"), \
         patch("backend.rss_service.fetch_all_active_rss_nodes", return_value=[]), \
         patch.dict("sys.modules", {"backend.bcm.watcher": MagicMock()}):
        
        # Start background loops
        distill_task = scheduler.start_skill_distillation_loop(interval_seconds=60)
        rss_task = scheduler.start_rss_poller_loop(interval_seconds=60)
        scheduler.start_watcher_loop(interval_seconds=60)

        assert distill_task is not None
        assert rss_task is not None

        # Give them a moment to initialize
        await asyncio.sleep(0.02)

        # Trigger graceful shutdown
        scheduler.shutdown_scheduler(wait=False)

        await asyncio.sleep(0.02)

        # Ensure tasks are cancelled and done
        assert distill_task.done()
        assert rss_task.done()


@pytest.mark.asyncio
async def test_cross_bcm_session_concurrent_cancellation():
    """Cross Test: Simulate a running BCM session being interrupted by sudden shutdown
    while broadcasting to websockets and saving messages, ensuring DB integrity is preserved.
    """
    from backend.database import _execute

    # Set up mock subprocess that gets cancelled mid-run
    async def _mock_cancelled_subprocess(*args, **kwargs):
        await asyncio.sleep(0.01)
        raise asyncio.CancelledError()

    with patch("asyncio.to_thread", side_effect=_mock_cancelled_subprocess), \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock) as mock_broadcast, \
         patch("backend.scheduler._send_telegram_alert", new_callable=AsyncMock):

        job_id = "test_bcm_cross_cancel"
        session_name = "Tokyo/Sydney"

        # Execute BCM session scheduler job
        await scheduler._job_bcm_session_scheduler(
            job_id=job_id,
            label="BCM Session (Tokyo/Sydney)",
            session_name=session_name
        )

        # Check that session metadata table recorded the task session without crash
        rows = _execute("SELECT session_id, schedule_info FROM session_metadata WHERE session_id = ?", (f"task_{job_id}",))
        assert len(rows) > 0


@pytest.mark.asyncio
async def test_cross_bcm_session_cron_schedule_and_db_persistence():
    """Cross Test: End-to-end verification of BCM session execution, metadata persistence
    into session_metadata table, restore_state DB hydration, and schedule verification.
    """
    from backend.database import _execute
    import json
    import os

    job_id = "bcm_session_london"
    label = "BCM Session (London)"
    cron_expr = "0 9 * * mon-fri Europe/London"

    # 1. Trigger BCM session job with mock subprocess
    mock_proc = MagicMock()
    mock_proc.stdout = "London analysis completed successfully."
    mock_proc.stderr = ""
    with patch("asyncio.to_thread", return_value=mock_proc), \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock), \
         patch("backend.scheduler._send_telegram_alert", new_callable=AsyncMock):

        await scheduler._job_bcm_session_scheduler(
            job_id=job_id,
            label=label,
            session_name="London",
            cron_expr=cron_expr
        )

    # 2. Verify row was created in session_metadata with valid non-wildcard cron_expr
    rows = _execute("SELECT schedule_info FROM session_metadata WHERE session_id = ?", (f"task_{job_id}",))
    assert len(rows) > 0
    info = json.loads(rows[0][0])
    assert info.get("cron_expr") == cron_expr
    assert info.get("task_type") == "cron"

    # 3. Simulate scheduler reboot and restore_state
    scheduler._timer_meta.clear()
    scheduler.restore_state()

    assert job_id in scheduler._timer_meta
    assert scheduler._timer_meta[job_id]["cron_expr"] == cron_expr

    # 4. Run BCM session loop initialization and check APScheduler trigger
    scheduler.start_bcm_session_scheduler_loop()
    job = scheduler.scheduler.get_job(job_id)
    assert job is not None
    assert job.name == label


def test_cross_watcher_memory_sync_scheduler_lifecycle_it():
    """Cross Test: Verify watcher memory synchronization job integration with APScheduler
    and ZeroCostWatcher memory state across the background scheduler lifecycle.
    """
    from backend.scheduler import scheduler, start_watcher_loop, _job_watcher_sync
    try:
        from backend.bcm.watcher import watcher
    except ImportError:
        pytest.skip("Private BCM module not installed")

    # 1. Initialize watcher with sample tracking history
    watcher._pnl_history["TEST_POS_1"] = [10.0, 20.0]
    watcher._pnl_history["TEST_POS_EMPTY"] = []

    # 2. Register watcher sync loop in scheduler
    start_watcher_loop(interval_seconds=120)
    job = scheduler.get_job("watcher_sync_loop")
    assert job is not None
    assert job.name == "Watcher Memory Sync"

    # 3. Trigger watcher sync job directly
    _job_watcher_sync()

    # 4. Verify cross-state modification
    assert "TEST_POS_1" in watcher._pnl_history
    assert "TEST_POS_EMPTY" not in watcher._pnl_history


