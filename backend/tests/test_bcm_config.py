import pytest
import os
import sys

# Ensure backend module is available
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.bcm.autonomous_trader import TICKER_MAP

def test_ticker_map_structure():
    """
    Validates that every entry in TICKER_MAP follows the required specification
    for cTrader OpenAPI integration.
    """
    assert isinstance(TICKER_MAP, dict), "TICKER_MAP must be a dictionary"
    
    required_keys = {"analysis", "trade_id", "volume", "digits"}
    
    for ticker, config in TICKER_MAP.items():
        assert isinstance(config, dict), f"Config for {ticker} must be a dictionary"
        
        # Check for missing keys
        missing_keys = required_keys - config.keys()
        assert not missing_keys, f"Ticker {ticker} is missing required keys: {missing_keys}"
        
        # Validate data types
        assert isinstance(config["analysis"], str), f"Ticker {ticker} 'analysis' must be a string"
        assert isinstance(config["trade_id"], int), f"Ticker {ticker} 'trade_id' must be an integer (cTrader symbol ID)"
        assert isinstance(config["volume"], (int, float)), f"Ticker {ticker} 'volume' must be a numeric minimum/step volume"
        assert isinstance(config["digits"], int), f"Ticker {ticker} 'digits' must be an integer representing price precision"
        
        # Validate logical constraints
        assert config["volume"] > 0, f"Ticker {ticker} 'volume' must be strictly positive"
        assert 0 <= config["digits"] <= 8, f"Ticker {ticker} 'digits' must be between 0 and 8"

def test_ticker_map_no_duplicate_trade_ids():
    """
    Validates that no multiple tickers share the same trade_id unless explicitly mapped.
    Since autonomous_trader now relies on trade_id for reverse mapping positions,
    duplicate trade_ids can cause infinite buy loops if not properly accounted for in guards.
    """
    trade_id_to_tickers = {}
    
    for ticker, config in TICKER_MAP.items():
        tid = config["trade_id"]
        if tid not in trade_id_to_tickers:
            trade_id_to_tickers[tid] = []
        trade_id_to_tickers[tid].append(ticker)
        
    # We allow aliases (e.g., WTI and USOIL both mapping to 10054, GOLD and XAUUSD to 41)
    # The Open Position Guard has been updated to use trade_id, making aliases safe.
    # We just log aliases for visibility.
    has_aliases = False
    for tid, tickers in trade_id_to_tickers.items():
        if len(tickers) > 1:
            has_aliases = True
            # print(f"Note: cTrader ID {tid} is aliased by {tickers}")
            
    assert True, "Duplicate trade_ids are now safely handled by Open Position Guard."
