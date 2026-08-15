import pytest
import sqlite3
import os
from backend.bcm.confluence_engine import ConfluenceEngine
from backend.database import log_trade_trace, DB_PATH

def test_traceability_generates_id():
    engine = ConfluenceEngine()
    result = engine.compute_confluence(wyckoff_score=0.8, momentum_score=0.8, vwap_score=0.8)
    assert "trace_id" in result
    assert result["trace_id"].startswith("trc_")

def test_traceability_db_insertion():
    # Insert a dummy trace
    trace_id = "test_trc_9999"
    log_trade_trace(trace_id, "test_session", "BTCUSD", "{}", "{}", "test_action", "PASSED")
    
    # Verify in SQLite DB
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT audit_status FROM trade_traces WHERE trace_id = ?", (trace_id,))
    row = c.fetchone()
    conn.close()
    
    assert row is not None
    assert row[0] == "PASSED"
