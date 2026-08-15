import pytest
import sqlite3
import os
from backend.bcm.confluence_engine import ConfluenceEngine
from backend.database import DB_PATH, log_trade_trace

def test_cross_engine_veto_propagation():
    """
    Cross test to ensure that when ConfluenceEngine receives a signal that triggers
    a ContrarianAgent veto, the final decision is HOLD_SKIP, and the trace is generated.
    """
    engine = ConfluenceEngine()
    
    # We simulate a momentum trap: strong momentum, but very poor wyckoff structure
    # This should trigger the ContrarianAgent to veto a BUY decision.
    # ConfluenceEngine normally would compute a score based on weights, but let's 
    # force a scenario where raw confluence is positive but contrarian vetoes.
    
    # Setting wyckoff=0.0 (chop), momentum=1.0 (max), plus other signals to trigger a STRONG_BUY score
    result = engine.compute_confluence(
        wyckoff_score=0.0,
        momentum_score=1.0,
        vwap_score=1.0,
        remizov_score=1.0,
        ema_score=1.0,
        is_sideways_regime=False,
        higher_tf_trend="BULL"
    )
    
    # Assert trace_id was generated
    assert "trace_id" in result
    
    # Because wyckoff < 0.2 and momentum > 0.6, Contrarian Agent should veto it.
    assert result["veto_applied"] is True
    assert result["decision"] == "HOLD_SKIP"
    assert "Momentum trap" in str(result["veto_reasons"])
    
    # Ensure it can be logged without error
    try:
        log_trade_trace(
            trace_id=result["trace_id"],
            session_id="CROSS_TEST",
            symbol="BTC",
            layer_01="test_perception",
            layer_02=str(result),
            layer_03="SKIPPED",
            audit_status="PASSED"
        )
    except Exception as e:
        pytest.fail(f"Trace logging failed in cross test: {e}")

    # Verify trace is in DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT audit_status FROM trade_traces WHERE trace_id = ?", (result["trace_id"],))
    row = c.fetchone()
    conn.close()
    
    assert row is not None
    assert row[0] == "PASSED"
