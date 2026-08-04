try:
    import pytest
except ImportError:
    pytest = None

import os
import sys

# Ensure backend directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.bcm.tools import (
    SYMBOL_MAP,
    YF_SYMBOL_MAP,
    _normalize_yf_symbol,
    handle_bcm_get_technical_indicators,
    handle_bcm_calculate_remizov_shift,
)

def test_symbol_mappings():
    """Verify all Pepperstone symbols have valid FIX Symbol IDs and Yahoo Finance tickers."""
    expected_symbols = ["BTCUSD", "EURUSD", "GBPUSD", "XAUUSD", "US500", "BRENT", "USOIL", "WTI", "AMZN", "GOOGL", "NVDA", "TSLA", "AAPL", "MSFT", "META", "SPY", "QQQ", "USO"]
    
    for sym in expected_symbols:
        assert sym in SYMBOL_MAP, f"Missing FIX symbol ID for {sym}"
        assert sym in YF_SYMBOL_MAP, f"Missing YF ticker for {sym}"
        assert isinstance(SYMBOL_MAP[sym], int), f"Symbol ID for {sym} must be integer"
        assert len(YF_SYMBOL_MAP[sym]) > 0, f"YF ticker for {sym} cannot be empty"

def test_yf_symbol_normalization():
    """Verify ticker normalization for Yahoo Finance."""
    assert _normalize_yf_symbol("BTCUSD") == "BTC-USD"
    assert _normalize_yf_symbol("EURUSD") == "EURUSD=X"
    assert _normalize_yf_symbol("GBPUSD") == "GBPUSD=X"
    assert _normalize_yf_symbol("XAUUSD") == "GC=F"
    assert _normalize_yf_symbol("US500") == "^GSPC"
    assert _normalize_yf_symbol("BRENT") == "BZ=F"
    assert _normalize_yf_symbol("USOIL") == "CL=F"
    assert _normalize_yf_symbol("WTI") == "CL=F"

def test_get_live_ctrader_positions_helper():
    """Verify get_live_ctrader_positions function loads safely without crashing."""
    from backend.bcm.autonomous_trader import get_live_ctrader_positions
    positions, summary = get_live_ctrader_positions()
    assert isinstance(positions, list)
    assert isinstance(summary, str)

def test_bcm_technical_indicators_all_assets():
    """Verify technical indicators fetch successfully for all 6 Pepperstone assets."""
    assets = ["BTCUSD", "EURUSD", "GBPUSD", "XAUUSD", "US500", "BRENT"]
    for asset in assets:
        res = handle_bcm_get_technical_indicators({"symbol": asset})
        assert isinstance(res, dict), f"Indicators for {asset} must be a dict"
        assert "error" not in res, f"Fetching indicators for {asset} failed with error: {res.get('error')}"
        assert len(res) > 0, f"Indicators for {asset} cannot be empty"

def test_bcm_remizov_shift_all_assets():
    """Verify Remizov Shift volatility calculation for all 6 Pepperstone assets."""
    assets = ["BTCUSD", "EURUSD", "GBPUSD", "XAUUSD", "US500", "BRENT"]
    for asset in assets:
        res = handle_bcm_calculate_remizov_shift({"symbol": asset})
        assert isinstance(res, dict), f"Remizov Shift for {asset} must be a dict"
        assert "error" not in res, f"Remizov Shift for {asset} failed: {res.get('error')}"
        assert "remizov_shift" in res, f"Missing remizov_shift key for {asset}"
        assert isinstance(res["remizov_shift"], (int, float)), f"Remizov Shift value for {asset} must be numeric"

if __name__ == "__main__":
    print("🚀 Running BCM Unit Tests...")
    test_symbol_mappings()
    print("  ✅ test_symbol_mappings: PASSED")
    test_yf_symbol_normalization()
    print("  ✅ test_yf_symbol_normalization: PASSED")
    test_get_live_ctrader_positions_helper()
    print("  ✅ test_get_live_ctrader_positions_helper: PASSED")
    test_bcm_technical_indicators_all_assets()
    print("  ✅ test_bcm_technical_indicators_all_assets: PASSED")
    test_bcm_remizov_shift_all_assets()
    print("  ✅ test_bcm_remizov_shift_all_assets: PASSED")
    print("\n🎉 ALL BCM UNIT TESTS PASSED SUCCESSFULLY!")
