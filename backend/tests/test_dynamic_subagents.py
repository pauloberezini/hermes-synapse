import pytest
import os
from fastapi.testclient import TestClient
from backend import database
from backend.main import app
from backend.auth import active_sessions

client = TestClient(app)
client.headers = {"Authorization": "Bearer test-token"}
active_sessions.add("test-token")


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    original_db_path = database.DB_PATH
    original_db_dir = database.DB_DIR
    
    test_db = tmp_path / "test_hermes_subagents.db"
    database.DB_PATH = str(test_db)
    database.DB_DIR = str(tmp_path)
    
    database.init_db()
    
    # Clear pre-seeded subagents for testing CRUD from a clean state
    import sqlite3
    conn = sqlite3.connect(database.DB_PATH)
    conn.execute("DELETE FROM subagents")
    conn.commit()
    conn.close()
    
    yield
    
    database.DB_PATH = original_db_path
    database.DB_DIR = original_db_dir


def test_subagent_db_crud():
    # 1. Verify initially empty list
    assert len(database.get_all_subagents()) == 0
    
    # 2. Save a subagent
    database.save_subagent("sports_betting", "Sports Analyser", "You analyze sports odds.", "google/gemini-2.5-flash")
    
    # 3. Retrieve and verify
    agent = database.get_subagent("sports_betting")
    assert agent is not None
    assert agent["name"] == "Sports Analyser"
    assert agent["system_prompt"] == "You analyze sports odds."
    assert agent["model"] == "google/gemini-2.5-flash"
    
    # 4. Verify all list
    all_agents = database.get_all_subagents()
    assert len(all_agents) == 1
    assert all_agents[0]["id"] == "sports_betting"
    
    # 5. Delete and verify
    deleted = database.delete_subagent("sports_betting")
    assert deleted is True
    assert database.get_subagent("sports_betting") is None
    assert len(database.get_all_subagents()) == 0


def test_subagents_api_endpoints():
    # 1. GET empty list
    response = client.get("/api/subagents")
    assert response.status_code == 200
    assert response.json() == []

    # 2. POST create a subagent
    payload = {
        "id": "french_tutor",
        "name": "French Teacher",
        "system_prompt": "Enseignez le français.",
        "model": "google/gemini-2.5-pro"
    }
    response = client.post("/api/subagents", json=payload)
    assert response.status_code == 200
    assert response.json() == {"status": "success", "id": "french_tutor"}

    # 3. GET list containing the subagent
    response = client.get("/api/subagents")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == "french_tutor"
    assert data[0]["name"] == "French Teacher"

    # 4. DELETE subagent
    response = client.delete("/api/subagents/french_tutor")
    assert response.status_code == 200
    assert response.json() == {"status": "success"}

    # 5. Verify list is empty again
    response = client.get("/api/subagents")
    assert response.json() == []
