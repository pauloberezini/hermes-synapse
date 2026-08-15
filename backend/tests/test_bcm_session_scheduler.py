import os
import json
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock

from backend.bcm.session_scheduler import _has_run_today, _record_run_today, run_analysis

@pytest.fixture
def state_file(tmp_path):
    file_path = tmp_path / "last_session_runs.json"
    with patch("backend.bcm.session_scheduler.STATE_FILE", str(file_path)):
        yield str(file_path)

def test_record_and_has_run_today(state_file):
    assert _has_run_today("London", "2026-08-16") == False
    
    _record_run_today("London", "2026-08-16")
    
    assert _has_run_today("London", "2026-08-16") == True
    assert _has_run_today("New York", "2026-08-16") == False
    assert _has_run_today("London", "2026-08-17") == False

    with open(state_file, "r") as f:
        data = json.load(f)
        assert data["London"] == "2026-08-16"

@patch("backend.bcm.session_scheduler.subprocess.check_output")
def test_run_one_symbol_success(mock_check_output):
    from backend.bcm.session_scheduler import run_one_symbol
    mock_check_output.return_value = b"Verdict: STRONG_BUY\nMD Reasoning: Wyckoff accumulation looks solid."
    
    symbol, verdict, reasoning, error = run_one_symbol("BTC", "London")
    
    assert symbol == "BTC"
    assert verdict == "STRONG_BUY"
    assert reasoning == "Wyckoff accumulation looks solid."
    assert error is None

@patch("backend.bcm.session_scheduler.subprocess.check_output")
def test_run_one_symbol_failure(mock_check_output):
    from backend.bcm.session_scheduler import run_one_symbol
    import subprocess
    mock_check_output.side_effect = subprocess.CalledProcessError(1, "cmd", output=b"Fatal error")
    
    symbol, verdict, reasoning, error = run_one_symbol("EURUSD", "New York")
    
    assert symbol == "EURUSD"
    assert verdict is None
    assert reasoning is None
    assert error == "Fatal error"

@patch("backend.bcm.session_scheduler.run_one_symbol")
def test_run_analysis(mock_run_one_symbol, capsys):
    # Mock symbols execution
    def side_effect(symbol, reason):
        if symbol == "BTC":
            return ("BTC", "STRONG_BUY", "Good structure", None)
        elif symbol == "GOLD":
            return ("GOLD", "HOLD_SKIP", "Too much chop", None)
        else:
            return (symbol, None, None, "Exit 1")
            
    mock_run_one_symbol.side_effect = side_effect
    
    with patch("backend.bcm.session_scheduler.SYMBOLS", ["BTC", "GOLD", "US500"]):
        run_analysis("London")
        
    captured = capsys.readouterr()
    assert "Market Status (London Session)" in captured.out
    assert "**BTC**: STRONG_BUY" in captured.out
    assert "**GOLD**: HOLD_SKIP" in captured.out
    assert "**US500**: Analysis failed" in captured.out
