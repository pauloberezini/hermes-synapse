"""
backend/tests/test_docker_cross_services_it.py — Cross-Service & Integration Test Suite.

Validates end-to-end interactions across:
  - FastMarketCache + RegimeDetector + ConfluenceEngine + AutonomousTrader
  - MCPServerClient + AutonomousTrader Macro Context
  - Scheduler + BCM Multi-Agent Cycle + DB + WebSocket
  - ExchangeFactory + ComplianceOfficer + Risk Management
  - PriceMonitor + WebSocket + Telegram Alerting
"""

import asyncio
import json
import warnings
import pytest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock, AsyncMock

bcm_available = False
try:
    from backend.bcm.fast_market_cache import (
        fast_market_cache,
        get_historical_data,
        get_remizov_shift
    )
    from backend.bcm.regime_detector import RegimeDetector
    from backend.bcm.confluence_engine import ConfluenceEngine, ConfluenceDecision
    from backend.bcm.compliance_officer import ComplianceOfficer
    from backend.bcm.exchange_factory import ExchangeFactory
    from backend.bcm.autonomous_trader import (
        ask_ai_decision,
        get_macro_terminal_context,
        format_any_bcm_response,
        check_liquidity_layer_0
    )
    bcm_available = True
except ImportError:
    pass

from backend.mcp_client import MCPServerClient
from backend import scheduler
from backend import price_monitor
from backend import database


@pytest.fixture(autouse=True)
def clean_cache_and_state():
    """Reset memory cache and test globals between test runs."""
    if bcm_available and "fast_market_cache" in globals():
        fast_market_cache._memory_store.clear()
    yield
    if bcm_available and "fast_market_cache" in globals():
        fast_market_cache._memory_store.clear()


# ==============================================================================
# 1. Cross-Service: Market Cache -> Regime Detector -> Confluence -> Decision
# ==============================================================================

@pytest.mark.skipif(not bcm_available, reason="Private BCM plugin not installed")
def test_cross_cache_regime_confluence_pipeline():
    """Cross-Service Test: Verify market data flow from FastMarketCache through
    RegimeDetector and ConfluenceEngine into ask_ai_decision.
    """
    ticker = "EURUSD"
    dates = pd.date_range("2026-08-01", periods=100, freq="h")
    # Upward trending price series with low volatility
    prices = 1.0800 + np.cumsum(np.random.normal(0.0002, 0.0001, 100))
    df = pd.DataFrame({
        "Close": prices,
        "High": prices + 0.0005,
        "Low": prices - 0.0005,
        "Open": prices,
        "Volume": 5000
    }, index=dates)

    # 1. Cache historical data in FastMarketCache with standard key format
    cache_key = f"hist_data:{ticker}:1d:60d"
    fast_market_cache.set(cache_key, df, ttl_sec=300)

    # 2. Verify get_historical_data retrieves the cached DataFrame directly
    fetched_df = get_historical_data(ticker, interval="1d", period="60d", limit=100)
    assert not fetched_df.empty
    assert len(fetched_df) == 100

    # 3. Compute Remizov acceleration shift
    remizov_val = get_remizov_shift(fetched_df)
    assert isinstance(remizov_val, float)

    # 4. Regime Detection
    regime_detector = RegimeDetector()
    regime_res = regime_detector.detect_regime(fetched_df["Close"].tolist())
    assert "regime" in regime_res
    regime = regime_res["regime"]
    assert regime in ("BULL", "BEAR", "SIDEWAYS", "RECOVERY")

    # 5. Confluence Engine Computation
    confluence = ConfluenceEngine()
    conf_res = confluence.compute_confluence(
        remizov_score=remizov_val,
        momentum_score=0.6,
        vwap_score=0.4,
        volume_profile_score=0.3,
        is_sideways_regime=(regime == "SIDEWAYS"),
        higher_tf_trend="BULL" if regime in ("BULL", "RECOVERY") else "BEAR"
    )
    assert "decision" in conf_res
    assert "confluence_score" in conf_res
    assert -1.0 <= conf_res["confluence_score"] <= 1.0


# ==============================================================================
# 2. Cross-Service: MCPServerClient -> AutonomousTrader Macro Context
# ==============================================================================

@pytest.mark.skipif(not bcm_available, reason="Private BCM plugin not installed")
@pytest.mark.asyncio
async def test_cross_macro_terminal_mcp_client_integration():
    """Cross-Service Test: Verify MCPServerClient starts, calls tools,
    and returns formatted macro context into AutonomousTrader with caching.
    """
    ticker = "GC=F"
    mock_news_response = json.dumps({
        "status": "success",
        "ticker": ticker,
        "sentiment": "bullish",
        "summary": "Gold reaches new highs amid central bank purchases and rate cut expectations."
    })
    mock_sentiment_response = json.dumps({
        "status": "success",
        "overall_sentiment": "risk-off",
        "score": 0.72
    })

    with patch("backend.mcp_client.MCPServerClient.start", new_callable=AsyncMock) as mock_start, \
         patch("backend.mcp_client.MCPServerClient.call_tool", new_callable=AsyncMock) as mock_call:
        
        async def fake_call_tool(tool_name, args):
            if "news" in tool_name:
                return mock_news_response
            return mock_sentiment_response

        mock_call.side_effect = fake_call_tool

        # 1. Fetch macro context (first call -> executes MCP)
        context = get_macro_terminal_context(ticker)
        assert "TICKER NEWS & SENTIMENT" in context
        assert "MARKET SENTIMENT SUMMARY" in context
        assert mock_start.called

        # 2. Second call should hit FastMarketCache without re-invoking MCP
        mock_start.reset_mock()
        mock_call.reset_mock()
        cached_context = get_macro_terminal_context(ticker)
        assert cached_context == context
        assert not mock_start.called


# ==============================================================================
# 3. Cross-Service: Scheduler -> BCM Cycle -> DB Persistence -> WebSocket
# ==============================================================================

@pytest.mark.skipif(not bcm_available, reason="Private BCM plugin not installed")
@pytest.mark.asyncio
async def test_cross_scheduler_bcm_pipeline_and_db_persistence():
    """Cross-Service Test: Verify the full scheduler cycle invoking BCM agents,
    saving messages to SQLite/Postgres DB, and broadcasting updates via WebSocket.
    """
    job_id = "cross_test_bcm_cycle"
    chat_id = f"task_{job_id}"
    prompt = "Run BCM Multi-Agent Analysis for GBPUSD"

    mock_analysis_json = json.dumps({
        "ticker": "GBPUSD",
        "rsi": {"14": 58.0},
        "adx": {"14": 25.0},
        "vwap": {"daily": 1.2850}
    })

    mock_decision_json = json.dumps({
        "decision": "wait",
        "confidence": 60.0,
        "recommended_sl": None,
        "recommended_tp": None,
        "reasoning": "Holding for London session open liquidity confirmation."
    })

    with patch("backend.scheduler._register_scheduled_session") as mock_reg, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock) as mock_ws, \
         patch("backend.bcm.autonomous_trader.get_technical_analysis", return_value=mock_analysis_json), \
         patch("backend.bcm.autonomous_trader.ask_ai_decision", return_value=mock_decision_json), \
         patch("backend.database.save_message", return_value="msg_12345") as mock_save_msg, \
         patch("backend.scheduler._send_telegram_alert", new_callable=AsyncMock):

        await scheduler._trigger_agent_task(
            agent_id="bcm_orchestrator",
            prompt=prompt,
            chat_id=chat_id,
            job_id=job_id,
            label="Cross BCM Pipeline Test"
        )

        # 1. Verify scheduled session registration
        assert mock_reg.called
        # 2. Verify message saved to DB
        assert mock_save_msg.called
        assert mock_save_msg.call_args[0][0] == chat_id
        # 3. Verify websocket broadcasts were fired
        assert mock_ws.call_count >= 1


# ==============================================================================
# 4. Cross-Service: ExchangeFactory -> ComplianceOfficer -> Risk Guardrails
# ==============================================================================

@pytest.mark.skipif(not bcm_available, reason="Private BCM plugin not installed")
def test_cross_exchange_factory_and_compliance_officer():
    """Cross-Service Test: Verify ExchangeFactory broker retrieval and
    ComplianceOfficer pre-trade audit limits (drawdown, max leverage, spread check).
    """
    # 1. Spot Broker Retrieval from Factory
    broker = ExchangeFactory.get_spot_broker()
    assert broker is not None

    # 2. Compliance Officer Validation
    officer = ComplianceOfficer()
    
    # Valid trade parameters
    valid_audit = officer.check_hard_limits(
        symbol="BTCUSD",
        action="buy",
        volume=0.01,
        base_volume=0.01,
        sl=58000.0,
        tp=65000.0,
        entry_price=60000.0,
        current_equity=100000.0
    )
    assert isinstance(valid_audit, tuple)
    passed, reason = valid_audit
    assert passed is True

    # Invalid trade: Missing Stop Loss (Hard Rule)
    invalid_audit = officer.check_hard_limits(
        symbol="BTCUSD",
        action="buy",
        volume=0.01,
        base_volume=0.01,
        sl=None,
        tp=65000.0,
        entry_price=60000.0,
        current_equity=100000.0
    )
    passed_no_sl, reason_no_sl = invalid_audit
    assert passed_no_sl is False
    assert "Stop Loss" in reason_no_sl


# ==============================================================================
# 5. Cross-Service: PriceMonitor -> WebSocket -> Telegram Alerting
# ==============================================================================

@pytest.mark.asyncio
async def test_cross_price_monitor_alerting_and_graceful_cancellation():
    """Cross-Service Test: Verify PriceMonitor checks alert triggers,
    broadcasts alerts via WebSocket and Telegram, and handles cancellation cleanly.
    """
    pm = price_monitor.PriceMonitor()
    pm.alerts = [{
        "id": "alert_999",
        "symbol": "BTCUSD",
        "display_name": "BTCUSD",
        "is_crypto": True,
        "target_price": 60000.0,
        "condition": "above",
        "chat_id": "tg_chat_1",
        "created_at": "2026-08-20 12:00:00"
    }]

    with patch.object(pm.provider, "get_price", new_callable=AsyncMock) as mock_price, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock) as mock_ws, \
         patch("backend.activity_logger.log_activity"), \
         patch("backend.price_monitor.PriceMonitor.save_alerts"), \
         patch("backend.scheduler._send_telegram_alert", new_callable=AsyncMock):

        mock_price.return_value = 60500.0

        # Run one monitoring iteration
        await pm.check_alerts_once()

        # Alert should trigger and broadcast because 60500.0 > 60000.0
        assert mock_ws.called

    # Verify background run_loop cancels without unhandled exceptions
    with patch.object(pm, "check_alerts_once", new_callable=AsyncMock):
        task = asyncio.create_task(pm.run_loop())
        await asyncio.sleep(0.01)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert task.done()


# ==============================================================================
# 6. Cross-Service: CTraderOpenApiClient -> Protocol Messages -> Symbol Lookup
# ==============================================================================

@pytest.mark.skipif(not bcm_available, reason="Private BCM plugin not installed")
@pytest.mark.asyncio
async def test_cross_ctrader_openapi_client_and_lookup_pipeline():
    """Cross-Service Test: Verify CTraderOpenApiClient proto message framing,
    app/account authentication flows, and symbol lookup pipeline execution.
    """
    import sys, os
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    from backend.bcm.openapi_client import CTraderOpenApiClient, pb2, common_pb2
    from scripts.ctrader_lookup import lookup

    mock_client = MagicMock(spec=CTraderOpenApiClient)
    mock_client.connect = AsyncMock(return_value=True)
    mock_client.authorize_app = AsyncMock(return_value=True)
    mock_client.authorize_account = AsyncMock(return_value=True)
    mock_client.close = AsyncMock()
    mock_client.ctid = "123456"

    # Mock Symbol List Response Proto
    symbols_res = pb2.ProtoOASymbolsListRes()
    symbols_res.ctidTraderAccountId = 123456
    sym = symbols_res.symbol.add()
    sym.symbolId = 1
    sym.symbolName = "EURUSD"
    sym.baseAssetId = 1
    sym.quoteAssetId = 2
    sym.symbolCategoryId = 1

    mock_msg_symbols = common_pb2.ProtoMessage()
    mock_msg_symbols.payloadType = 2115
    mock_msg_symbols.payload = symbols_res.SerializeToString()

    # Mock Symbol Details Response Proto
    details_res = pb2.ProtoOASymbolByIdRes()
    details_res.ctidTraderAccountId = 123456
    sym_detail = details_res.symbol.add()
    sym_detail.symbolId = 1
    sym_detail.digits = 5
    sym_detail.pipPosition = 4
    sym_detail.minVolume = 100000
    sym_detail.maxVolume = 10000000
    sym_detail.stepVolume = 100000
    sym_detail.lotSize = 10000000

    mock_msg_details = common_pb2.ProtoMessage()
    mock_msg_details.payloadType = 2117
    mock_msg_details.payload = details_res.SerializeToString()

    async def fake_send_message(payload_type, payload, client_msg_id=None):
        if payload_type == 2114: # ProtoOASymbolsListReq
            return mock_msg_symbols
        elif payload_type == 2116: # ProtoOASymbolByIdReq
            return mock_msg_details
        return mock_msg_symbols

    mock_client.send_message = AsyncMock(side_effect=fake_send_message)

    with patch("scripts.ctrader_lookup.CTraderOpenApiClient", return_value=mock_client):
        # Execute lookup script pipeline
        await lookup("EURUSD")

        # Verify all steps were invoked across the protocol
        assert mock_client.connect.called
        assert mock_client.authorize_app.called
        assert mock_client.authorize_account.called
        assert mock_client.send_message.call_count == 2
        assert mock_client.close.called


# ==============================================================================
# 7. Cross-Service: Complexity Classifier -> RAG -> Agent Execution -> Decision Log
# ==============================================================================

@pytest.mark.asyncio
async def test_cross_agent_llm_error_recovery_and_decision_logging():
    """Cross-Service Test: End-to-end multi-layer pipeline test across:
      Classifier (recovering from null content) -> RAG memory search ->
      Agent completion (recovering gracefully from upstream OpenRouter errors) ->
      Database Decision Logs & User-facing message.
    """
    from backend.agent import JarvisAgent
    import backend.database as db

    agent = JarvisAgent()
    agent.api_key = "sk-test-cross"

    user_query = "Проверь 20/08 17:00 IDT 🚫 BCM Blocked — US500"
    session_id = "cross_test_session_error_recovery"

    # 1. Classifier returns 200 with null content (reproducing docker log warning)
    mock_classifier_resp = MagicMock()
    mock_classifier_resp.status_code = 200
    mock_classifier_resp.json.return_value = {"choices": [{"message": {"content": None}}]}

    # 2. Main agent LLM call returns 200 with error payload (reproducing docker log KeyError: 'choices')
    mock_agent_err_resp = MagicMock()
    mock_agent_err_resp.status_code = 200
    mock_agent_err_resp.text = '{"error": {"message": "OpenRouter provider temporary unavailable", "code": 503}}'
    mock_agent_err_resp.json.return_value = {"error": {"message": "OpenRouter provider temporary unavailable", "code": 503}}

    async def fake_post(url, *args, **kwargs):
        if "chat/completions" in str(url):
            # First call is classifier, subsequent is agent
            if kwargs.get("json", {}).get("max_tokens") == 5:
                return mock_classifier_resp
            return mock_agent_err_resp
        return mock_agent_err_resp

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=fake_post), \
         patch("backend.rag.search_memory", return_value=[{"title": "BCM Guide", "content": "Risk compliance rules."}]), \
         patch("backend.database.save_decision_log") as mock_save_decision:

        response = await agent.respond(user_query, session_id=session_id)

        # Verify graceful user-facing apology with provider error context
        assert "Apologies, Sir." in response
        assert "OpenRouter provider temporary unavailable" in response or "OpenRouter" in response

        # Verify decision log was saved to DB with failure flag and error details
        assert mock_save_decision.called
        saved_log = mock_save_decision.call_args[0][0]
        assert saved_log["session_id"] == session_id
        assert saved_log["success"] is False
        assert "OpenRouter provider temporary unavailable" in str(saved_log["error"]) or "LLM API Error" in str(saved_log["error"])


# ==============================================================================
# 5. Cross-Service: BCM Session + US100 Multi-Asset Pipeline + DB Logging
# ==============================================================================

@pytest.mark.skipif(not bcm_available, reason="Private BCM plugin not installed")
@pytest.mark.asyncio
async def test_cross_bcm_scheduler_us100_market_analysis_pipeline():
    """Cross-Service Test: Verify end-to-end BCM market cycle execution for US100
    from Scheduler through Technical Analysis, Confluence, AI Decision synthesis,
    and DB persistence without 404 or unhandled errors.
    """
    from backend.bcm.autonomous_trader import get_technical_analysis, ask_ai_decision
    from backend.bcm.tools import _normalize_yf_symbol

    symbol = "US100"
    normalized_ticker = _normalize_yf_symbol(symbol)
    assert normalized_ticker == "^NDX"

    dates = pd.date_range("2026-08-01", periods=100, freq="h")
    prices = 19800.0 + np.cumsum(np.random.normal(0.5, 5, 100))
    mock_df = pd.DataFrame({
        "Open": prices,
        "High": prices + 20,
        "Low": prices - 20,
        "Close": prices,
        "Volume": [15000] * 100
    }, index=dates)

    # 1. Technical Analysis on US100
    with patch("backend.bcm.autonomous_trader._fetch_yahoo_direct", return_value=mock_df) as mock_fetch:
        analysis = get_technical_analysis(symbol)
        assert analysis is not None
        assert "rsi" in analysis.lower()
        assert "macd" in analysis.lower()
        assert "close" in analysis.lower()
        assert mock_fetch.called

    # 2. AI Decision Synthesis for US100
    mock_llm_decision = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": json.dumps({
                        "decision": "WAIT",
                        "confidence": 75,
                        "reasoning": "NASDAQ 100 consolidating at key VWAP resistance level.",
                        "trade_parameters": {}
                    })
                }
            }
        ]
    }

    with patch("requests.post") as mock_post, \
         patch("backend.database.save_decision_log") as mock_db_log:
        
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = mock_llm_decision
        mock_post.return_value = mock_resp

        decision_result = ask_ai_decision(symbol, analysis)
        assert decision_result is not None
        assert "decision" in str(decision_result) or "WAIT" in str(decision_result)


# ==============================================================================
# 6. Cross-Service: HttpProvider Multi-Asset Yahoo Resolution + Resilience
# ==============================================================================

@pytest.mark.asyncio
async def test_cross_http_provider_multi_asset_yahoo_resolution():
    """Cross-Service Test: Verify HttpProvider maps commodity, index, forex,
    and crypto symbols to valid Yahoo endpoints, successfully parsing price metadata
    and handling non-200 / network errors gracefully without crashing.
    """
    from backend.market_data import HttpProvider

    provider = HttpProvider()

    # Mock successful Yahoo response
    def create_mock_yahoo_resp(price_val: float):
        mock_r = MagicMock()
        mock_r.status_code = 200
        mock_r.json.return_value = {
            "chart": {
                "result": [
                    {
                        "meta": {
                            "regularMarketPrice": price_val
                        }
                    }
                ]
            }
        }
        return mock_r

    test_symbols = {
        "US100": 19850.50,
        "US500": 5600.25,
        "GOLD": 2510.40,
        "BRENT": 77.80,
        "EURUSD": 1.0875,
        "BTCUSD": 61200.00
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        for sym, expected_price in test_symbols.items():
            mock_get.return_value = create_mock_yahoo_resp(expected_price)
            price = await provider._fetch_yahoo(sym)
            assert price == expected_price
            assert mock_get.called

        # Test error resilience: 404 / 500 / Network Exception
        mock_404 = MagicMock()
        mock_404.status_code = 404
        mock_get.return_value = mock_404
        res_404 = await provider._fetch_yahoo("UNKNOWN_TICKER")
        assert res_404 is None

        mock_get.side_effect = Exception("Connection timeout")
        res_err = await provider._fetch_yahoo("US100")
        assert res_err is None






