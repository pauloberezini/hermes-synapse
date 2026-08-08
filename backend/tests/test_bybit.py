import pytest
import json
from backend.bcm.bybit_trader import BybitTrader
from backend.bcm.tools import bcm_execute_tool


def test_bybit_signature_generation():
    trader = BybitTrader(api_key="test_key", api_secret="test_secret")
    sig = trader._generate_signature("1672531199000", "category=linear&symbol=ETHUSDT")
    assert isinstance(sig, str)
    assert len(sig) == 64  # SHA256 hex string is 64 chars long


def test_bybit_analyze_option_position_short_put():
    trader = BybitTrader()
    # Test Short Put ETH @ 1300 with premium $50, current spot ETH $3100
    res = trader.analyze_option_position(
        symbol="ETH-DEC26-1300-P",
        strike=1300.0,
        option_type="Put",
        side="Sell",
        premium=50.0,
        exp_date="December",
        current_spot=3100.0
    )

    assert res["status"] == "success"
    assert res["strike"] == 1300.0
    assert res["breakeven_price"] == 1250.0  # 1300 - 50 = 1250
    assert res["is_in_the_money"] is False
    assert res["distance_to_strike_usd"] == 1800.0  # 3100 - 1300
    assert res["max_potential_profit_usd"] == 50.0
    assert res["max_potential_loss_usd"] == 1250.0  # (1300 - 50)
    assert "OTM" in res["recommendation"]


def test_bybit_analyze_option_position_itm_alert():
    trader = BybitTrader()
    # Test Short Put ETH @ 1300 when spot falls to $1100 (ITM)
    res = trader.analyze_option_position(
        symbol="ETH-DEC26-1300-P",
        strike=1300.0,
        option_type="Put",
        side="Sell",
        premium=50.0,
        exp_date="December",
        current_spot=1100.0
    )

    assert res["status"] == "success"
    assert res["is_in_the_money"] is True
    assert "WARNING" in res["recommendation"]


def test_bcm_tool_router_bybit_analyze_option():
    args = {
        "symbol": "ETH-DEC26-1300-P",
        "strike": 1300.0,
        "option_type": "Put",
        "side": "Sell",
        "premium": 45.0,
        "current_spot": 3150.0
    }
    raw_res = bcm_execute_tool("bybit_analyze_option_position", args)
    res = json.loads(raw_res)
    assert res["status"] == "success"
    assert res["breakeven_price"] == 1255.0


def test_bcm_crypto_orchestrator_db_registration():
    from backend.database import get_subagent, init_db
    init_db()
    orch = get_subagent("bcm_crypto_orchestrator")
    agent = get_subagent("bcm_crypto")
    vol_agent = get_subagent("bcm_crypto_volatility")
    news_agent = get_subagent("bcm_crypto_news")

    assert orch is not None
    assert orch["name"] == "BCM Crypto Orchestrator"
    assert orch["agent_type"] == "orchestrator"
    assert agent is not None
    assert agent["parent_id"] == "bcm_crypto_orchestrator"

    assert vol_agent is not None
    assert vol_agent["parent_id"] == "bcm_crypto_orchestrator"
    assert "bybit" in vol_agent["skills"]

    assert news_agent is not None
    assert news_agent["parent_id"] == "bcm_crypto_orchestrator"
    assert "web_search" in news_agent["skills"]


def test_bcm_crypto_trader_cycle():
    from backend.bcm.crypto_trader import BCMCryptoTrader
    trader = BCMCryptoTrader()
    res = trader.run_crypto_cycle("ETHUSDT")
    assert res["status"] == "success"
    assert res["symbol"] == "ETHUSDT"
    assert "option_risk_assessment" in res
    assert "portfolio_greeks" in res
    assert "margin_safety" in res


def test_bybit_portfolio_greeks_and_delta_hedge():
    trader = BybitTrader()
    greeks = trader.get_portfolio_greeks("ETH")
    assert greeks["status"] == "success"
    assert "net_delta_coin" in greeks
    assert "net_delta_usd" in greeks

    hedge = trader.calc_delta_hedge("ETH")
    assert hedge["status"] == "success"
    assert "hedge_required" in hedge


def test_bybit_margin_safety_stress_test():
    trader = BybitTrader()
    margin_res = trader.check_margin_safety("ETH", price_shocks=[-10.0, 10.0])
    assert margin_res["status"] == "success"
    assert "current_margin_utilization_pct" in margin_res
    assert len(margin_res["stress_test_scenarios"]) == 2


def test_bcm_tool_router_institutional_suite():
    greeks_raw = bcm_execute_tool("bybit_get_portfolio_greeks", {"base_coin": "ETH"})
    greeks = json.loads(greeks_raw)
    assert greeks["status"] == "success"

    hedge_raw = bcm_execute_tool("bybit_calc_delta_hedge", {"base_coin": "ETH"})
    hedge = json.loads(hedge_raw)
    assert hedge["status"] == "success"

    margin_raw = bcm_execute_tool("bybit_check_margin_safety", {"base_coin": "ETH"})
    margin = json.loads(margin_raw)
    assert margin["status"] == "success"


def test_non_ascii_session_id_header_safety():
    session_id = "chat_скнзеу_0280"
    safe_session_id = session_id.encode("ascii", "ignore").decode("ascii").strip() or "session"
    assert safe_session_id == "chat__0280"
    # Ensure safe_session_id can be encoded as ASCII without throwing UnicodeEncodeError
    safe_session_id.encode("ascii")



