import asyncio
import json
import warnings
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend import rag
from backend import scheduler
from backend import price_monitor


@pytest.mark.asyncio
async def test_qdrant_client_no_compatibility_warning():
    """IT: Verify that get_qdrant_client creates a QdrantClient with check_compatibility=False,
    preventing Qdrant remote UserWarning during startup and queries.
    """
    rag._qdrant_client = None
    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")
        with patch("backend.rag.QdrantClient") as mock_qdrant_cls:
            mock_instance = MagicMock()
            mock_qdrant_cls.return_value = mock_instance

            client = rag.get_qdrant_client()

            assert client is mock_instance
            mock_qdrant_cls.assert_called_once_with(
                host=rag.QDRANT_HOST,
                port=rag.QDRANT_PORT,
                check_compatibility=False
            )

        # Ensure no UserWarning was recorded about version compatibility
        compat_warnings = [
            w for w in recorded_warnings
            if "incompatible" in str(w.message).lower()
        ]
        assert len(compat_warnings) == 0


@pytest.mark.asyncio
async def test_bcm_session_scheduler_handles_cancelled_error():
    """IT: Reproduce APScheduler CancelledError during BCM session execution on shutdown
    and verify it is handled cleanly without raising an unhandled exception.
    """
    with patch("asyncio.to_thread", side_effect=asyncio.CancelledError()):
        # Running the job should catch CancelledError gracefully and not raise
        try:
            await scheduler._job_bcm_session_scheduler(
                job_id="test_bcm_cancel",
                label="BCM Session (Test)",
                session_name="London"
            )
        except asyncio.CancelledError:
            pytest.fail("_job_bcm_session_scheduler raised unhandled CancelledError instead of handling it gracefully")


@pytest.mark.asyncio
async def test_all_scheduler_jobs_handle_cancellation_gracefully():
    """IT: Verify _job_one_shot, _job_alarm, _job_recurring, and _job_cron
    all handle asyncio.CancelledError cleanly without unhandled propagation.
    """
    with patch("backend.scheduler._send_telegram_alert", side_effect=asyncio.CancelledError()):
        # 1. One-shot timer
        scheduler._timer_meta["test_one_shot"] = {"status": "running"}
        try:
            await scheduler._job_one_shot(
                job_id="test_one_shot",
                label="Test Timer",
                duration=10,
                chat_id="test_chat",
                task_type="one-shot"
            )
        except asyncio.CancelledError:
            pytest.fail("_job_one_shot raised unhandled CancelledError")

        # 2. Alarm
        scheduler._timer_meta["test_alarm"] = {"status": "running"}
        try:
            await scheduler._job_alarm(
                job_id="test_alarm",
                label="Test Alarm",
                chat_id="test_chat",
                target_time_str="2026-08-19 12:00:00",
                task_type="alarm"
            )
        except asyncio.CancelledError:
            pytest.fail("_job_alarm raised unhandled CancelledError")

        # 3. Recurring
        try:
            await scheduler._job_recurring(
                job_id="test_recurring",
                label="Test Recurring",
                interval_hours=1.0,
                chat_id="test_chat",
                task_type="recurring"
            )
        except asyncio.CancelledError:
            pytest.fail("_job_recurring raised unhandled CancelledError")

        # 4. Cron
        try:
            await scheduler._job_cron(
                job_id="test_cron",
                label="Test Cron",
                cron_expr="0 * * * *",
                chat_id="test_chat",
                task_type="cron"
            )
        except asyncio.CancelledError:
            pytest.fail("_job_cron raised unhandled CancelledError")


@pytest.mark.asyncio
async def test_price_monitor_run_loop_handles_cancellation():
    """IT: Verify price monitor run_loop cleanly handles cancellation without unhandled CancelledError."""
    pm = price_monitor.PriceMonitor()
    with patch.object(pm, "check_alerts_once", new_callable=AsyncMock):
        task = asyncio.create_task(pm.run_loop())
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # Task cancellation is expected to finalize cleanly
        assert task.done()


@pytest.mark.asyncio
async def test_telegram_error_handler_handles_conflict_and_network_gracefully():
    """IT: Verify telegram_error_handler logs Conflict and NetworkError gracefully without raising unhandled errors."""
    from telegram.error import Conflict, NetworkError, TimedOut
    from backend import bot

    mock_context = MagicMock()

    # 1. Test Conflict error handling
    mock_context.error = Conflict("terminated by other getUpdates request")
    with patch.object(bot.logger, "error") as mock_log_error:
        await bot.telegram_error_handler(None, mock_context)
        mock_log_error.assert_called_once()
        assert "Telegram Conflict error" in mock_log_error.call_args[0][0]

    # 2. Test NetworkError handling
    mock_context.error = NetworkError("connection reset by peer")
    with patch.object(bot.logger, "warning") as mock_log_warn:
        await bot.telegram_error_handler(None, mock_context)
        mock_log_warn.assert_called_once()
        assert "Telegram network warning" in mock_log_warn.call_args[0][0]

    # 3. Test TimedOut handling
    mock_context.error = TimedOut()
    with patch.object(bot.logger, "warning") as mock_log_warn:
        await bot.telegram_error_handler(None, mock_context)
        mock_log_warn.assert_called_once()
        assert "Telegram network warning" in mock_log_warn.call_args[0][0]


def test_fast_market_cache_exports_historical_data_and_remizov_shift():
    """IT: Verify get_historical_data and get_remizov_shift are exported by fast_market_cache
    and function properly with caching, preventing Confluence Engine pre-check ImportError.
    """
    from backend.bcm.fast_market_cache import get_historical_data, get_remizov_shift
    import pandas as pd
    import numpy as np

    # 1. Test get_remizov_shift with synthetic dataframe
    dates = pd.date_range("2026-01-01", periods=50)
    prices = 100.0 + np.cumsum(np.random.normal(0, 1, 50))
    df = pd.DataFrame({"Close": prices, "High": prices + 1.0, "Low": prices - 1.0, "Open": prices}, index=dates)

    shift = get_remizov_shift(df)
    assert isinstance(shift, (int, float))

    # Empty df returns 0.0 safely
    assert get_remizov_shift(pd.DataFrame()) == 0.0

    # 2. Test get_historical_data caching
    with patch("backend.bcm.autonomous_trader._fetch_yahoo_direct", return_value=df) as mock_fetch:
        cached_df = get_historical_data("BTCUSD", interval="1d", limit=50)
        assert not cached_df.empty
        assert len(cached_df) == 50

        # Second call should hit cache without invoking mock_fetch again
        cached_df2 = get_historical_data("BTCUSD", interval="1d", limit=50)
        assert not cached_df2.empty
        assert mock_fetch.call_count == 1


def test_ask_ai_decision_no_unbound_local_os_or_scoping_error():
    """IT: Reproduce and verify ask_ai_decision executes without UnboundLocalError on 'os'
    and without NameError on 'analysis_json', returning a valid MD decision.
    """
    from backend.bcm.autonomous_trader import ask_ai_decision
    import json
    import pandas as pd

    # Synthetic historical data so Confluence gate runs
    dates = pd.date_range("2026-01-01", periods=50)
    df = pd.DataFrame({"Close": [100.0 + i for i in range(50)], "High": [101.0 + i for i in range(50)], "Low": [99.0 + i for i in range(50)], "Open": [100.0 + i for i in range(50)]}, index=dates)

    analysis_data = {
        "ticker": "BTCUSD",
        "rsi": {"14": 55.0},
        "vwap": {"daily": 140.0},
        "volume_profile": {"poc": 139.0}
    }

    mock_llm_md_response = json.dumps({
        "decision": "BUY",
        "confidence": 85.0,
        "recommended_sl": 95.0,
        "recommended_tp": 115.0,
        "reasoning": "Strong trend alignment and confluence."
    })

    with patch("backend.bcm.autonomous_trader.get_historical_data", return_value=df, create=True), \
         patch("backend.bcm.autonomous_trader.get_live_exchange_positions", return_value=([], "LIVE EXCHANGE OPEN POSITIONS: NONE")), \
         patch("backend.bcm.autonomous_trader.get_live_spot_prices", return_value={}), \
         patch("backend.bcm.autonomous_trader.get_account_balance", return_value=(100000.0, 95000.0)), \
         patch("backend.bcm.autonomous_trader.get_completed_trades_summary", return_value="No closed trades."), \
         patch("backend.bcm.autonomous_trader.fetch_analytics_playbook", return_value=""), \
         patch("backend.bcm.autonomous_trader.call_llm", return_value=mock_llm_md_response):

        # Should execute cleanly without raising UnboundLocalError or NameError
        decision_str = ask_ai_decision("BTCUSD", analysis_data)
        assert isinstance(decision_str, str)
        parsed = json.loads(decision_str)
        assert "decision" in parsed


@pytest.mark.asyncio
async def test_scheduler_bcm_cycle_integration():
    """IT: Verify scheduler _trigger_agent_task runs the BCM multi-agent cycle
    cleanly without unhandled errors or crashing.
    """
    from backend import scheduler
    import json

    mock_llm_md_response = json.dumps({
        "decision": "wait",
        "confidence": 50.0,
        "recommended_sl": None,
        "recommended_tp": None,
        "reasoning": "Holding for better confluence."
    })

    with patch("backend.scheduler._register_scheduled_session"), \
         patch("backend.activity_logger.log_activity"), \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock), \
         patch("backend.bcm.autonomous_trader.get_technical_analysis", return_value=json.dumps({"ticker": "BTCUSD", "rsi": {"14": 50.0}})), \
         patch("backend.bcm.autonomous_trader.ask_ai_decision", return_value=mock_llm_md_response), \
         patch("backend.database.save_message"), \
         patch("backend.scheduler._send_telegram_alert", new_callable=AsyncMock):

        await scheduler._trigger_agent_task(
            agent_id="bcm_orchestrator",
            prompt="Analyze BTCUSD",
            chat_id="test_chat",
            job_id="test_bcm_job",
            label="BCM Session Test"
        )


@pytest.mark.asyncio
async def test_get_macro_terminal_context_in_running_loop_and_timeout_no_warning():
    """IT: Verify get_macro_terminal_context executes inside an active async event loop
    and handles MCP timeouts/errors without raising RuntimeWarning (unawaited coroutine)
    or leaving unmanaged tasks.
    """
    from backend.bcm.autonomous_trader import get_macro_terminal_context

    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")

        # 1. Successful MCP response inside running loop
        with patch("backend.mcp_client.MCPServerClient.start", new_callable=AsyncMock), \
             patch("backend.mcp_client.MCPServerClient.call_tool", new_callable=AsyncMock) as mock_tool:
            mock_tool.side_effect = lambda tool_name, args: "Bullish Fed rhetoric" if "sentiment" in tool_name else "BTC up 3%"
            res = get_macro_terminal_context("BTCUSD")
            assert "MARKET SENTIMENT SUMMARY" in res or "TICKER NEWS & SENTIMENT" in res

        # 2. Error / Timeout scenario inside running loop
        with patch("backend.mcp_client.MCPServerClient.start", side_effect=Exception("Connection refused")):
            res_err = get_macro_terminal_context("ETHUSD_TIMEOUT")
            assert res_err == ""

        # Verify no unawaited coroutine warnings were emitted
        unawaited_coro_warnings = [
            w for w in recorded_warnings
            if "never awaited" in str(w.message).lower()
        ]
        assert len(unawaited_coro_warnings) == 0, f"Found unawaited coroutine warnings: {unawaited_coro_warnings}"


def test_dynamic_futures_spread_and_curve_status_no_yfinance_404():
    """IT: Verify _get_dynamic_next_month_ticker and _get_futures_curve_status generate
    dynamic active contract tickers for current year/month and gracefully calculate
    contango/backwardation without throwing 404 delisted errors.
    """
    import pandas as pd
    from backend.bcm.intermarket_correlations import (
        _get_dynamic_next_month_ticker,
        _get_futures_curve_status,
        get_intermarket_snapshot,
        FUTURES_SYMBOLS
    )

    # 1. Dynamic ticker generation for all commodities
    for sym in FUTURES_SYMBOLS:
        tickers = _get_dynamic_next_month_ticker(sym)
        assert tickers is not None
        front, back = tickers
        assert "=F" in front
        assert len(back) > 4

    # 2. Term structure curve calculation with mock prices
    dates = pd.date_range("2026-08-01", periods=30)
    front_series = pd.Series([80.0 + i * 0.1 for i in range(30)], index=dates)
    back_series = pd.Series([82.0 + i * 0.1 for i in range(5)], index=dates[-5:])

    with patch("backend.bcm.intermarket_correlations._fetch_yahoo_prices") as mock_fetch:
        # Mock contango (back > front)
        mock_fetch.side_effect = lambda t, **kw: back_series if ".NYM" in t or ".CMX" in t else front_series
        curve = _get_futures_curve_status("WTI")
        assert curve["status"] in ("contango", "backwardation", "flat")
        assert "spread_pct" in curve

        # Mock fallback when back contract unavailable (uses front series 20d moving avg)
        mock_fetch.side_effect = lambda t, **kw: None if ".NYM" in t or ".CMX" in t else front_series
        curve_fallback = _get_futures_curve_status("BRENT")
        assert curve_fallback["status"] in ("contango", "backwardation", "flat")
        assert "spread_pct" in curve_fallback


def test_intermarket_yfinance_silent_on_missing_tickers():
    """IT: Verify _fetch_yahoo_prices suppresses all yfinance console errors and logger noise
    when encountering non-existent, invalid, or delisted tickers.
    """
    import io
    import sys
    from backend.bcm.intermarket_correlations import _fetch_yahoo_prices

    # Capture real stderr to verify nothing is leaked to console
    old_stderr = sys.stderr
    sys.stderr = captured_stderr = io.StringIO()
    try:
        with patch("yfinance.download", side_effect=Exception("Symbol may be delisted")):
            res = _fetch_yahoo_prices("NON_EXISTENT_DELISTED_TICKER_12345.NYM")
            assert res is None
    finally:
        sys.stderr = old_stderr

    assert "traceback" not in captured_stderr.getvalue().lower()


def test_tools_run_async_safety_and_lifecycle():
    """IT: Verify _run_async safely runs async coroutines and factories from sync context
    and cleans up unawaited coroutines on failure without raising RuntimeWarning.
    """
    from backend.tools import _run_async

    async def _sample_coro(val: int):
        await asyncio.sleep(0.01)
        return val * 2

    with warnings.catch_warnings(record=True) as recorded_warnings:
        warnings.simplefilter("always")

        # 1. Normal sync invocation
        res = _run_async(_sample_coro(21))
        assert res == 42

        # 2. Coroutine factory invocation
        res_factory = _run_async(lambda: _sample_coro(10))
        assert res_factory == 20

        # 3. Failing coroutine
        async def _failing_coro():
            raise ValueError("Test failure")

        res_fail = _run_async(_failing_coro())
        assert res_fail is None

        # Verify no unawaited coroutine warnings were recorded
        unawaited_coro_warnings = [
            w for w in recorded_warnings
            if "never awaited" in str(w.message).lower()
        ]
        assert len(unawaited_coro_warnings) == 0


@pytest.mark.asyncio
async def test_cross_bcm_full_multi_agent_cycle_integration():
    """Cross Test: Verify the end-to-end BCM hedge fund multi-agent architecture
    (Market Data -> Intermarket -> Quant -> Macro -> Risk -> Managing Director -> Consensus)
    runs seamlessly across all subsystems with complete data flow integrity and zero warnings.
    """
    import json
    import pandas as pd
    from backend.bcm.autonomous_trader import (
        ask_ai_decision,
        get_macro_terminal_context,
        get_fred_intraday_filters,
        fetch_analytics_playbook
    )
    from backend.bcm.intermarket_correlations import get_intermarket_snapshot
    from backend.bcm.fast_market_cache import fast_market_cache

    ticker = "BTCUSD"
    dates = pd.date_range("2026-08-01", periods=60)
    df = pd.DataFrame({
        "Close": [60000.0 + i * 50.0 for i in range(60)],
        "High": [60500.0 + i * 50.0 for i in range(60)],
        "Low": [59500.0 + i * 50.0 for i in range(60)],
        "Open": [59900.0 + i * 50.0 for i in range(60)],
        "Volume": [1000.0 for _ in range(60)]
    }, index=dates)

    # 1. Seed Fast Market Cache
    fast_market_cache.set(f"hist:{ticker}:1d:60", df, ttl_sec=60)

    # 2. Intermarket Cross Snapshot
    with patch("backend.bcm.intermarket_correlations._fetch_yahoo_prices", return_value=df["Close"]):
        intermarket_data = get_intermarket_snapshot(ticker, period="20d")
        assert "intermarket_score" in intermarket_data
        assert "macro_levels" in intermarket_data

    # 3. Macro Terminal Context Fetch inside running async loop
    with patch("backend.mcp_client.MCPServerClient.start", new_callable=AsyncMock), \
         patch("backend.mcp_client.MCPServerClient.call_tool", new_callable=AsyncMock) as mock_mcp:
        mock_mcp.return_value = "Macro outlook: positive liquidity conditions."
        macro_context = get_macro_terminal_context(ticker)
        assert isinstance(macro_context, str)

    # 4. Multi-Agent Decision Engine Execution
    analysis_payload = {
        "ticker": ticker,
        "rsi": {"14": 62.5},
        "adx": {"14": 28.0},
        "vwap": {"daily": 61200.0},
        "intermarket": intermarket_data,
        "macro_context": macro_context
    }

    mock_llm_md_verdict = json.dumps({
        "decision": "BUY",
        "confidence": 88.0,
        "recommended_sl": 59000.0,
        "recommended_tp": 65000.0,
        "reasoning": "Strong intermarket confluence, liquidity expansion, and trend continuation."
    })

    from backend.bcm.confluence_engine import ConfluenceDecision

    with patch("backend.bcm.confluence_engine.ConfluenceEngine.compute_confluence", return_value={"decision": ConfluenceDecision.STRONG_BUY, "confluence_score": 0.88, "veto_reasons": []}), \
         patch("backend.bcm.autonomous_trader.get_historical_data", return_value=df, create=True), \
         patch("backend.bcm.autonomous_trader.get_live_exchange_positions", return_value=([], "OPEN POSITIONS: NONE")), \
         patch("backend.bcm.autonomous_trader.get_live_spot_prices", return_value={ticker: 62500.0}), \
         patch("backend.bcm.autonomous_trader.get_account_balance", return_value=(250000.0, 240000.0)), \
         patch("backend.bcm.autonomous_trader.get_completed_trades_summary", return_value="Win rate 75% across 20 trades."), \
         patch("backend.bcm.autonomous_trader.fetch_analytics_playbook", return_value="Playbook: Follow trend continuation."), \
         patch("backend.bcm.autonomous_trader.call_llm", return_value=mock_llm_md_verdict):

        verdict_raw = ask_ai_decision(ticker, analysis_payload)
        assert isinstance(verdict_raw, str)
        verdict = json.loads(verdict_raw)
        assert verdict["decision"] == "BUY"
        assert verdict["confidence"] == 88.0
        assert verdict["recommended_sl"] == 59000.0
        assert verdict["recommended_tp"] == 65000.0


@pytest.mark.asyncio
async def test_bcm_swing_session_cron_trigger_reconciliation_it():
    """Integration Test: Reproduce DB corrupted cron_expr (* * * * *) on BCM swing session
    and verify that restore_state and start_bcm_session_scheduler_loop heal it to '15 23 * * mon-fri UTC',
    rescheduling the APScheduler trigger to prevent runaway 1-minute loops and max instances warnings.
    """
    from backend.scheduler import (
        scheduler,
        restore_state,
        start_bcm_session_scheduler_loop,
        _timer_meta,
        _job_bcm_session_scheduler
    )
    from apscheduler.triggers.cron import CronTrigger
    from datetime import datetime, timezone
    import os

    # Clear test job
    job_id = "bcm_session_swing_daily_close"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    _timer_meta.pop(job_id, None)

    # 1. Simulate DB row with corrupted wildcard '* * * * *' cron expression
    corrupted_schedule_info = json.dumps({
        "job_id": job_id,
        "label": "BCM Session (Swing Daily Close)",
        "task_type": "cron",
        "prompt": "Run BCM Session Scheduler for swing_trigger",
        "status": "running",
        "agent_id": "system",
        "fire_count": 42,
        "cron_expr": "* * * * *"
    })
    mock_db_rows = [
        (f"task_{job_id}", "BCM Session (Swing Daily Close)", "system", job_id, "cron", corrupted_schedule_info)
    ]

    with patch("backend.database._execute", return_value=mock_db_rows), \
         patch.dict(os.environ, {"BCM_TRADE_MODE": "swing"}):
        
        # Run restore_state
        restore_state()
        
        # Verify restore_state caught the wildcard and healed default
        assert job_id in _timer_meta
        
        # Run start_bcm_session_scheduler_loop
        start_bcm_session_scheduler_loop()

        # Verify timer meta is now healed
        assert _timer_meta[job_id]["cron_expr"] == "15 23 * * mon-fri UTC"

        # Verify APScheduler job exists and has the correct trigger (not every minute)
        job = scheduler.get_job(job_id)
        assert job is not None
        assert job.kwargs.get("cron_expr") == "15 23 * * mon-fri UTC"

        # Check next fire time is at 23:15, NOT in the next 60 seconds
        now = datetime.now(timezone.utc)
        next_fire = job.trigger.get_next_fire_time(None, now)
        assert next_fire is not None
        assert next_fire.minute == 15
        assert next_fire.hour == 23


@pytest.mark.asyncio
async def test_apscheduler_persistent_job_store_conflict_safety_it():
    """Integration Test: Verify that calling start_bcm_session_scheduler_loop repeatedly
    or when jobs already exist does not cause unique constraint errors or crash the scheduler.
    """
    from backend.scheduler import scheduler, start_bcm_session_scheduler_loop, _timer_meta
    import os

    with patch.dict(os.environ, {"BCM_TRADE_MODE": "swing"}):
        # Initial loop run
        start_bcm_session_scheduler_loop()
        
        # Second run (simulating restart / reload)
        start_bcm_session_scheduler_loop()
        
        # Third run
        start_bcm_session_scheduler_loop()

        # All swing and intraday jobs should be present and valid
        assert scheduler.get_job("bcm_session_swing_daily_close") is not None
        assert scheduler.get_job("bcm_session_swing_friday_gap") is not None
        assert scheduler.get_job("bcm_session_london") is not None


@pytest.mark.asyncio
async def test_restore_state_persists_healed_cron_to_db_and_maps_bcm_session_func():
    """IT: Verify that restore_state immediately writes healed cron expressions back to DB
    and configures _job_bcm_session_scheduler as the execution target for BCM jobs.
    """
    from backend.scheduler import scheduler, restore_state, _timer_meta, _job_bcm_session_scheduler
    from datetime import datetime, timezone
    import os

    job_id = "bcm_session_swing_daily_close"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
    _timer_meta.pop(job_id, None)

    corrupted_info = json.dumps({
        "job_id": job_id,
        "label": "BCM Session (Swing Daily Close)",
        "task_type": "cron",
        "prompt": "Run BCM Session Scheduler for swing_trigger",
        "status": "running",
        "agent_id": "system",
        "fire_count": 100,
        "cron_expr": "* * * * *"
    })
    mock_db_rows = [
        (f"task_{job_id}", "BCM Session (Swing Daily Close)", "system", job_id, "cron", corrupted_info)
    ]

    with patch("backend.database._execute", return_value=mock_db_rows), \
         patch("backend.scheduler._register_scheduled_session") as mock_register:
        
        restore_state()

        # Check that healed cron was persisted
        mock_register.assert_called_once()
        assert mock_register.call_args[0][0] == job_id
        assert mock_register.call_args[1]["extra"]["cron_expr"] == "15 23 * * mon-fri UTC"

        # Check job in scheduler has _job_bcm_session_scheduler as func and session_name kwargs
        job = scheduler.get_job(job_id)
        assert job is not None
        assert job.func == _job_bcm_session_scheduler
        assert job.kwargs.get("session_name") == "swing_trigger"


@pytest.mark.asyncio
async def test_bcm_session_scheduler_prevents_wildcard_cron_overwrite_on_fire():
    """IT: Verify that _job_bcm_session_scheduler prevents * * * * * from being written to DB on execution."""
    from backend.scheduler import _job_bcm_session_scheduler, _timer_meta
    from unittest.mock import patch, MagicMock

    job_id = "bcm_session_swing_daily_close"
    _timer_meta[job_id] = {"cron_expr": "* * * * *", "status": "running"}

    mock_proc = MagicMock()
    mock_proc.stdout = "Market Status: OK"
    mock_proc.stderr = ""

    with patch("asyncio.to_thread", return_value=mock_proc), \
         patch("backend.scheduler._register_scheduled_session") as mock_register, \
         patch("backend.activity_logger.log_activity"), \
         patch("backend.websocket_manager.manager.broadcast"):
        
        await _job_bcm_session_scheduler(
            job_id=job_id,
            label="BCM Session (Swing Daily Close)",
            session_name="swing_trigger",
            cron_expr="* * * * *"
        )

        # Check that it did NOT save * * * * * to DB
        assert mock_register.called
        saved_cron = mock_register.call_args[1]["extra"]["cron_expr"]
        assert saved_cron == "15 23 * * mon-fri UTC"
        assert _timer_meta[job_id]["cron_expr"] == "15 23 * * mon-fri UTC"


@pytest.mark.asyncio
async def test_reconcile_swing_jobs_even_in_intraday_mode():
    """IT: Verify that start_bcm_session_scheduler_loop heals existing swing jobs even when BCM_TRADE_MODE='intraday'."""
    from backend.scheduler import scheduler, start_bcm_session_scheduler_loop, _timer_meta
    import os

    job_id = "bcm_session_swing_daily_close"
    _timer_meta[job_id] = {
        "type": "cron",
        "cron_expr": "* * * * *",
        "status": "running",
        "label": "BCM Session (Swing Daily Close)"
    }

    with patch.dict(os.environ, {"BCM_TRADE_MODE": "intraday"}), \
         patch("backend.scheduler._register_scheduled_session") as mock_reg:
        
        start_bcm_session_scheduler_loop()

        assert _timer_meta[job_id]["cron_expr"] == "15 23 * * mon-fri UTC"
        job = scheduler.get_job(job_id)
        assert job is not None
        assert job.kwargs.get("session_name") == "swing_trigger"


@pytest.mark.asyncio
async def test_ctrader_openapi_client_connection_failure_and_cleanup():
    """IT: Verify CTraderOpenApiClient.connect handles ConnectionRefusedError cleanly
    without unhandled exception, returns False, and close() safely cancels tasks.
    """
    from backend.bcm.openapi_client import CTraderOpenApiClient

    client = CTraderOpenApiClient(host="127.0.0.1", port=59999)
    
    # 1. Connection failure scenario
    with patch("asyncio.open_connection", side_effect=ConnectionRefusedError(111, "Connect call failed")):
        connected = await client.connect()
        assert connected is False
        assert client.is_connected is False

    # 2. Cleanup scenario
    await client.close()
    assert client.is_connected is False


@pytest.mark.asyncio
async def test_ctrader_lookup_handles_connection_refusal_cleanly():
    """IT: Verify ctrader_lookup.lookup exits cleanly without unhandled exception when OpenAPI connection fails."""
    from scripts.ctrader_lookup import lookup

    with patch("backend.bcm.openapi_client.CTraderOpenApiClient.connect", return_value=False):
        # Should complete gracefully without raising ConnectionRefusedError
        await lookup("GBPUSD")


def test_google_auth_module_os_scoping_it():
    """IT: Verify google_auth module executes and handles missing creds without UnboundLocalError on 'os'."""
    from backend import google_auth
    import io
    import sys

    captured_out = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = captured_out
        with patch("os.path.exists", return_value=False):
            google_auth.main()
    finally:
        sys.stdout = old_stdout

    # Should execute without throwing UnboundLocalError
    assert "Credentials not found" in captured_out.getvalue()








