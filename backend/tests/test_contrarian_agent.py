import pytest
from backend.bcm.contrarian_agent import ContrarianAgent

def test_contrarian_agent_agrees_with_hold():
    agent = ContrarianAgent()
    result = agent.evaluate_hypothesis({}, "HOLD_SKIP", 0.0)
    assert result["veto"] is False

def test_contrarian_agent_detects_momentum_trap():
    agent = ContrarianAgent()
    scores = {"wyckoff_structure": 0.1, "momentum": 0.9}
    result = agent.evaluate_hypothesis(scores, "STRONG_BUY", 0.7)
    assert result["veto"] is True
    assert any("Momentum trap" in r for r in result["reasons"])

def test_contrarian_agent_detects_volatility_anomaly():
    agent = ContrarianAgent()
    scores = {"odf_volatility": 0.9, "vwap_position": 0.1, "wyckoff_structure": 0.5}
    result = agent.evaluate_hypothesis(scores, "STRONG_BUY", 0.6)
    assert result["veto"] is True
    assert any("Volatility anomaly" in r for r in result["reasons"])

def test_contrarian_agent_detects_trend_conflict():
    agent = ContrarianAgent()
    scores = {"wyckoff_structure": -0.5, "momentum": 0.5, "vwap_position": 0.5}
    result = agent.evaluate_hypothesis(scores, "STRONG_BUY", 0.5)
    assert result["veto"] is True
    assert any("against bearish Wyckoff structure" in r for r in result["reasons"])

def test_contrarian_agent_fallback_free_exceptions():
    agent = ContrarianAgent()
    # Pass None to force an exception when trying to .get()
    result = agent.evaluate_hypothesis(None, "STRONG_BUY", 0.5)
    assert result["veto"] is True
    assert any("System Exception" in r for r in result["reasons"])
