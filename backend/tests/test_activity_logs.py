import os
import pytest
from backend import database
from backend.activity_logger import log_activity, ACTIVITY_LOGS

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    # Override database path to use temporary test file
    original_db_path = database.DB_PATH
    original_db_dir = database.DB_DIR
    
    test_db = tmp_path / "test_hermes.db"
    database.DB_PATH = str(test_db)
    database.DB_DIR = str(tmp_path)
    
    database.init_db()
    
    yield
    
    # Restore original paths
    database.DB_PATH = original_db_path
    database.DB_DIR = original_db_dir

def test_log_activity_records_entries_and_persists():
    # Clear logs before test
    ACTIVITY_LOGS.clear()
    
    # Write a test log
    log_activity(
        activity_type="active",
        source="TestAgent",
        message="Running model generation",
        token_cost=0.0015
    )
    
    # Check in-memory list
    assert len(ACTIVITY_LOGS) == 1
    log = ACTIVITY_LOGS[0]
    assert log["type"] == "active"
    assert log["source"] == "TestAgent"
    assert log["message"] == "Running model generation"
    assert log["token_cost"] == 0.0015
    assert "timestamp" in log

    # Check database persistence
    db_logs = database.get_activity_logs(10)
    assert len(db_logs) == 1
    db_log = db_logs[0]
    assert db_log["type"] == "active"
    assert db_log["source"] == "TestAgent"
    assert db_log["message"] == "Running model generation"
    assert db_log["token_cost"] == 0.0015

def test_clear_activity_logs():
    # Write a log
    log_activity(
        activity_type="idle",
        source="PriceMonitor",
        message="Checking price alerts",
        token_cost=0.0
    )
    
    db_logs = database.get_activity_logs(10)
    assert len(db_logs) > 0
    
    database.clear_activity_logs()
    assert len(database.get_activity_logs(10)) == 0
