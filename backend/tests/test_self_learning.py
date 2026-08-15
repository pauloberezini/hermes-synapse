import pytest
from backend.bcm.self_learning_pipeline import SelfLearningEngine

def test_self_learning_initialization():
    engine = SelfLearningEngine()
    assert engine.performance_threshold_delta == 0.5
    assert engine.bcm_memory_db is not None

def test_self_learning_graceful_no_data():
    engine = SelfLearningEngine()
    # If the DB doesn't exist or is empty, it shouldn't crash
    # It might return None if no DB, or "no_data" if DB is empty.
    engine.bcm_memory_db = "nonexistent_db.db"
    result = engine.analyze_closed_trades()
    assert result is None
