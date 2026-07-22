"""
API integration tests for session trajectory export endpoints.
"""
import json
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import active_sessions
from backend.database import save_message, clear_chat_history


@pytest.fixture
def client():
    c = TestClient(app)
    c.headers = {"Authorization": "Bearer test-token"}
    active_sessions.add("test-token")
    return c


def test_export_trajectory_endpoint_default_sharegpt(client):
    session_id = "test_export_session_api"
    clear_chat_history(session_id)
    save_message(session_id, "user", "What is the capital of France?")
    save_message(session_id, "assistant", "The capital of France is Paris.")

    response = client.get(f"/api/sessions/{session_id}/export-trajectory")
    assert response.status_code == 200
    assert "attachment; filename=" in response.headers.get("content-disposition", "")
    assert "trajectory_test_export_session_api_sharegpt.jsonl" in response.headers.get("content-disposition", "")

    lines = response.text.strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["id"] == session_id
    assert "conversations" in data
    assert len(data["conversations"]) == 2
    assert data["conversations"][0]["from"] == "human"
    assert data["conversations"][0]["value"] == "What is the capital of France?"
    clear_chat_history(session_id)


def test_export_history_alias_endpoint_openai_json(client):
    session_id = "test_alias_openai_json"
    clear_chat_history(session_id)
    save_message(session_id, "user", "Hello world")
    save_message(session_id, "assistant", "Hello there!")

    response = client.get(f"/api/history/{session_id}/export?format=openai&extension=json&download=true")
    assert response.status_code == 200
    assert "trajectory_test_alias_openai_json_openai.json" in response.headers.get("content-disposition", "")

    data = response.json()
    assert data["id"] == session_id
    assert "messages" in data
    assert len(data["messages"]) == 2
    assert data["messages"][0]["role"] == "user"
    assert data["messages"][1]["role"] == "assistant"
    clear_chat_history(session_id)


def test_export_trajectory_unknown_format_falls_back_to_sharegpt(client):
    session_id = "test_export_unknown_format"
    clear_chat_history(session_id)
    save_message(session_id, "user", "Test message")
    save_message(session_id, "assistant", "Test response")

    response = client.get(f"/api/sessions/{session_id}/export-trajectory?format=unknown_format&extension=unknown_ext")
    assert response.status_code == 200

    # Extension defaults to jsonl for invalid extensions
    assert "trajectory_test_export_unknown_format_unknown_format.jsonl" in response.headers.get("content-disposition", "")
    lines = response.text.strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data["id"] == session_id
    assert "conversations" in data
    clear_chat_history(session_id)

