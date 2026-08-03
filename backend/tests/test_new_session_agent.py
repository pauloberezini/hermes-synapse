import pytest
from fastapi.testclient import TestClient
from backend.main import app

from backend.auth import active_sessions

@pytest.fixture
def client():
    c = TestClient(app)
    c.headers = {"Authorization": "Bearer test-token"}
    active_sessions.add("test-token")
    return c

def test_new_session_creation_with_agent_and_title(client):
    session_id = "chat_test_orch_1234"
    agent_id = "test_orchestrator_agent"
    title = "Test Orchestrator Chat"
    
    # 1. Set agent for session
    res = client.post(f"/api/history/{session_id}/agent", json={"agent_id": agent_id})
    assert res.status_code == 200
    
    # 2. Rename session
    res = client.post(f"/api/history/{session_id}/rename", json={"title": title})
    assert res.status_code == 200
    
    # 3. Fetch all sessions (even with 0 messages)
    res = client.get("/api/history/sessions")
    assert res.status_code == 200
    sessions = res.json()
    
    target = next((s for s in sessions if s["id"] == session_id), None)
    assert target is not None, f"Session {session_id} not found in /api/history/sessions"
    assert target["title"] == title
    assert target["agent_id"] == agent_id
