"""
backend/tests/test_bcm_quantum.py — Unit & Integration Tests for BCM 2.0 Quantum Edition Modules.
"""

import pytest
from datetime import datetime, timezone, timedelta

from backend.bcm.frozen_windows import FrozenWindowsController, EventImpact
from backend.bcm.risk_engine import RiskEngine, DrawdownState
from backend.bcm.confluence_engine import ConfluenceEngine, ConfluenceDecision
from backend.bcm.trailing_stop import TrailingStopEngine
from backend.bcm.regime_detector import RegimeDetector, MarketRegime
from backend.bcm.fast_market_cache import FastMarketCache
from backend.bcm.watcher import ZeroCostWatcher


def test_frozen_windows_controller():
    controller = FrozenWindowsController(high_freeze_minutes=120, medium_freeze_minutes=15)
    base_time = datetime(2026, 8, 16, 14, 0, 0, tzinfo=timezone.utc)

    # 1. Register high impact FOMC event at 14:00
    controller.register_event("FOMC Rate Decision", base_time, impact=EventImpact.HIGH, affected_currencies=["USD"])

    # Test 30 mins before event -> should be FROZEN (PRE_EVENT)
    check_pre = base_time - timedelta(minutes=30)
    res_pre = controller.get_active_frozen_window("US500", check_pre)
    assert res_pre["is_frozen"] is True
    assert res_pre["window_type"] == "PRE_EVENT"
    assert "FOMC" in res_pre["reason"]

    # Test 30 mins after event -> should be FROZEN (POST_EVENT)
    check_post = base_time + timedelta(minutes=30)
    res_post = controller.get_active_frozen_window("BTC", check_post)
    assert res_post["is_frozen"] is True
    assert res_post["window_type"] == "POST_EVENT"

    # Test 150 mins after event -> should be UNLOCKED
    check_clear = base_time + timedelta(minutes=150)
    res_clear = controller.get_active_frozen_window("BTC", check_clear)
    assert res_clear["is_frozen"] is False
    assert res_clear["window_type"] == "NONE"


def test_risk_engine_drawdown_protocol():
    engine = RiskEngine(peak_equity=10000.0)

    # 0-2% DD -> NORMAL
    state, info = engine.evaluate_drawdown_state(9900.0) # 1% DD
    assert state == DrawdownState.NORMAL
    assert info["size_multiplier"] == 1.0
    assert info["allow_new_trades"] is True

    # 2-5% DD -> WARNING (50% size cut)
    state, info = engine.evaluate_drawdown_state(9600.0) # 4% DD
    assert state == DrawdownState.WARNING
    assert info["size_multiplier"] == 0.50
    assert info["allow_new_trades"] is True

    # 5-8% DD -> DANGER (Close-only)
    state, info = engine.evaluate_drawdown_state(9300.0) # 7% DD
    assert state == DrawdownState.DANGER
    assert info["size_multiplier"] == 0.0
    assert info["allow_new_trades"] is False

    # 8-10% DD -> CRITICAL
    state, info = engine.evaluate_drawdown_state(9100.0) # 9% DD
    assert state == DrawdownState.CRITICAL
    assert info["allow_new_trades"] is False

    # >10% DD -> KILL_SWITCH
    state, info = engine.evaluate_drawdown_state(8800.0) # 12% DD
    assert state == DrawdownState.KILL_SWITCH
    assert info["allow_new_trades"] is False


def test_risk_engine_var_and_stress_test():
    engine = RiskEngine(peak_equity=10000.0)

    # Parametric VaR 95%
    var_95 = engine.calculate_parametric_var(position_value_usd=1000.0, daily_volatility=0.02, confidence=0.95)
    assert round(var_95, 2) == 32.90 # 1000 * 0.02 * 1.645

    # Flash crash stress test
    positions = [
        {"symbol": "US500", "position_value_usd": 2000.0, "direction": "buy"},
        {"symbol": "BTC", "position_value_usd": 1500.0, "direction": "buy"},
        {"symbol": "GOLD", "position_value_usd": 1000.0, "direction": "buy"}
    ]
    stress_res = engine.run_flash_crash_stress_test(positions, account_equity=10000.0)
    assert "worst_scenario_loss_usd" in stress_res
    assert stress_res["passed"] is True  # Well under 5% equity threshold


def test_confluence_engine():
    engine = ConfluenceEngine()

    # 1. Strong Bullish Setup
    res_bull = engine.compute_confluence(
        wyckoff_score=0.9,
        remizov_score=0.8,
        vwap_score=0.7,
        volume_profile_score=0.8,
        ema_score=0.9,
        momentum_score=0.7,
        odf_score=0.5,
        gex_score=0.6,
        is_sideways_regime=False,
        higher_tf_trend="BULL"
    )
    assert res_bull["decision"] == ConfluenceDecision.STRONG_BUY
    assert res_bull["confluence_score"] >= 0.60
    assert res_bull["recommended_rr"] == "1:3.0"

    # 2. Sideways Regime VETO test -> score must be capped at <= 0.40
    res_side = engine.compute_confluence(
        wyckoff_score=0.9,
        remizov_score=0.8,
        vwap_score=0.9,
        ema_score=0.9,
        is_sideways_regime=True # VETO triggered
    )
    assert res_side["veto_applied"] is True
    assert res_side["confluence_score"] <= 0.40
    assert res_side["decision"] == ConfluenceDecision.NORMAL_BUY


def test_trailing_stop_engine():
    # Buy trade: entry 100, initial SL 90 (1R = 10 pts)
    # Price rises to 112 (+1.2R) -> Move SL to Break-Even (100)
    res_be = TrailingStopEngine.evaluate_stop_adjustment(
        direction="buy",
        entry_price=100.0,
        current_price=112.0,
        initial_sl=90.0,
        current_sl=90.0,
        peak_price=112.0
    )
    assert res_be["should_update"] is True
    assert res_be["new_sl"] == 100.0

    # Price rises to 130 (+3.0R) -> Trail SL to lock in 50% profit (100 + 15 = 115)
    res_trail = TrailingStopEngine.evaluate_stop_adjustment(
        direction="buy",
        entry_price=100.0,
        current_price=128.0,
        initial_sl=90.0,
        current_sl=100.0,
        peak_price=130.0
    )
    assert res_trail["should_update"] is True
    assert res_trail["new_sl"] == 115.0


def test_regime_detector():
    detector = RegimeDetector()

    # Generate synthetic bull price series
    bull_prices = [100.0 + i * 1.5 for i in range(30)]
    reg_bull = detector.detect_regime(bull_prices)
    assert reg_bull["regime"] == MarketRegime.BULL

    # Test consensus gating
    passed, reason = detector.check_consensus("BUY", MarketRegime.BULL)
    assert passed is True

    # Counter-trend sell in strong bull should be gated
    passed_counter, reason_counter = detector.check_consensus("SELL", MarketRegime.BULL)
    assert passed_counter is False


def test_fast_market_cache():
    cache = FastMarketCache(default_ttl_sec=2)
    cache.set("BTC:technical", {"rsi": 65.0, "macd": "bullish"}, ttl_sec=2)

    item = cache.get("BTC:technical")
    assert item["_meta"]["is_stale"] is False
    assert item["data"]["rsi"] == 65.0

    # Non-existent key
    miss = cache.get("UNKNOWN:key")
    assert miss["_meta"]["is_stale"] is True


def test_zero_cost_watcher():
    watcher = ZeroCostWatcher()

    account = {"equity": 10000.0, "margin_used": 3500.0} # 35% margin -> CRITICAL
    positions = [
        {
            "symbol": "BTC",
            "direction": "buy",
            "entry_price": 60000.0,
            "sl": 59500.0,
            "initial_sl": 58000.0,
            "unrealized_pnl": 1200.0,
            "peak_price": 62500.0
        }
    ]
    spot_prices = {"BTC": 62000.0}

    report = watcher.inspect_portfolio(account, positions, spot_prices)
    assert report["is_critical"] is True
    assert report["should_wake_orchestrator"] is True
    assert any(a["type"] == "HIGH_MARGIN_USAGE" for a in report["alerts"])
    # Trailing stop should trigger adjustment for +2R peak
    assert len(report["trailing_stop_actions"]) > 0
