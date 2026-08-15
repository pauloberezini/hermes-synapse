import pytest
from unittest.mock import patch, MagicMock

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Import BCM modules
from backend.bcm.autonomous_trader import run_autonomous_cycle
from backend.bcm.compliance_officer import ComplianceOfficer
from backend.bcm.fast_market_cache import FastMarketCache

@pytest.fixture(autouse=True)
def setup_mock_environment():
    """Mock the external API and Exchange calls for all tests."""
    with patch('backend.bcm.autonomous_trader.TICKER_MAP', {"BTC": {"analysis": "BTC-USD", "trade_id": "1", "volume": 1.0}}), \
         patch('backend.bcm.autonomous_trader.get_live_exchange_positions', return_value=([], {})), \
         patch('backend.bcm.autonomous_trader.memory.has_open_position', return_value=False), \
         patch('backend.bcm.autonomous_trader.get_account_balance', return_value=(10000.0, 10000.0)), \
         patch('backend.bcm.frozen_windows.get_frozen_windows_controller') as mock_fw_ctrl, \
         patch('backend.bcm.autonomous_trader.get_notifier'), \
         patch('backend.bcm.autonomous_trader.subprocess.check_output', return_value=b"SUCCESS"):
         
         mock_fw_ctrl.return_value.get_active_frozen_window.return_value = {"is_frozen": False}
         yield

def test_redis_outage_fallback():
    """Test that if Redis fails, the FastMarketCache gracefully falls back to memory."""
    cache = FastMarketCache()
    # Force redis client to be None to simulate outage
    cache._redis_client = None
    
    # Store should succeed in memory
    cache.set("test_key", {"data": "test_val"})
    val = cache.get("test_key")
    
    assert val["data"] == {"data": "test_val"}
    assert val["_meta"]["is_stale"] is False
    assert val["_meta"]["source"] == "fast_cache"

@patch('backend.bcm.autonomous_trader._fetch_yahoo_direct')
@patch('backend.bcm.fast_market_cache.fast_market_cache.get')
def test_autonomous_cycle_stale_data_fallback(mock_cache_get, mock_fetch):
    """Test that stale cache triggers synchronous fallback or block."""
    # Mock cache to return stale data
    mock_cache_get.return_value = {
        "data": None,
        "_meta": {"is_stale": True}
    }
    
    # Mock yfinance to fail (simulate API outage)
    mock_fetch.side_effect = Exception("Yahoo Finance Down")
    
    # Mock technicals
    with patch('backend.bcm.autonomous_trader.get_technical_analysis', return_value="{}"):
        report = run_autonomous_cycle("BTC")
        
    assert "wait" in report.lower()

@patch('backend.bcm.fast_market_cache.fast_market_cache.get')
@patch('backend.bcm.autonomous_trader._fetch_yahoo_direct')
def test_compliance_officer_api_outage(mock_fetch, mock_cache_get):
    """Test that ComplianceOfficer gracefully handles LLM API failure."""
    import pandas as pd
    
    mock_cache_get.return_value = {
        "data": {"rsi": {"BTC-USD": 70}, "macd": {"BTC-USD": 1}, "close": {"BTC-USD": 60000}},
        "_meta": {"is_stale": False}
    }
    
    # Return some fake hist data
    df = pd.DataFrame({"Close": [60000]*60})
    mock_fetch.return_value = df
    
    cco = ComplianceOfficer()
    
    # Mock requests.post to raise an error
    with patch('backend.bcm.compliance_officer.requests.post') as mock_post:
        mock_post.side_effect = Exception("OpenRouter API Timeout")
        
        passed, reason = cco.audit_trade(
            symbol="BTC", action="buy", volume=1.0, base_volume=1.0,
            sl=59000, tp=62000, entry_price=60000,
            md_decision="test", risk_report="test"
        )
        
        assert passed is False
        assert "Compliance Agent System Error" in reason

def test_frozen_windows_blocks_cycle():
    """Test that Frozen Windows blocks execution early."""
    with patch('backend.bcm.autonomous_trader.TICKER_MAP', {"BTC": {"analysis": "BTC-USD", "trade_id": "1", "volume": 1.0}}), \
         patch('backend.bcm.autonomous_trader.get_live_exchange_positions', return_value=([], {})), \
         patch('backend.bcm.autonomous_trader.memory.has_open_position', return_value=False), \
         patch('backend.bcm.autonomous_trader.get_account_balance', return_value=(10000.0, 10000.0)), \
         patch('backend.bcm.autonomous_trader.get_notifier') as mock_notifier_cls, \
         patch('backend.bcm.frozen_windows.get_frozen_windows_controller') as mock_fw_ctrl:
         
        mock_fw_ctrl.return_value.get_active_frozen_window.return_value = {"is_frozen": True, "reason": "FOMC Meeting"}
        
        mock_notifier_instance = mock_notifier_cls.return_value
        
        report = run_autonomous_cycle("BTC")
        
        assert "WAIT" in report.upper()
        
        # Check that the notifier was called with the blocked reason
        # It's possible that get_notifier() is called multiple times, so we search all mock_calls on the class
        called = False
        for call in mock_notifier_cls.mock_calls:
            if "FOMC Meeting" in str(call):
                called = True
        assert called

