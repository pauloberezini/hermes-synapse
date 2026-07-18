from fastapi.testclient import TestClient
from backend.main import app
from backend.agent import agent_instance
from backend.auth import active_sessions
from unittest.mock import AsyncMock, patch

client = TestClient(app)
client.headers = {"Authorization": "Bearer test-token"}
active_sessions.add("test-token")


def test_get_status():
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "online"
    assert "agent" in data
    assert data["agent"]["model"] == agent_instance.model

def test_get_config():
    response = client.get("/api/config")
    assert response.status_code == 200
    data = response.json()
    assert "system_prompt" in data
    assert "model" in data
    assert data["system_prompt"] == agent_instance.system_prompt

def test_update_config():
    original_prompt = agent_instance.system_prompt
    original_model = agent_instance.model
    original_provider = agent_instance.provider
    
    try:
        with patch(
            "backend.ollama_client.OllamaClient.list_models",
            new=AsyncMock(return_value=[{"name": "qwen-test:latest"}]),
        ):
            response = client.post(
                "/api/config",
                json={
                    "system_prompt": "Новый тестовый промпт",
                    "model": "qwen-test",
                    "provider": "ollama",
                }
            )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["config"]["system_prompt"] == "Новый тестовый промпт"
        assert data["config"]["model"] == "qwen-test:latest"
        
        # Verify in agent
        assert agent_instance.system_prompt == "Новый тестовый промпт"
        assert agent_instance.model == "qwen-test:latest"
    finally:
        # Restore defaults
        agent_instance.system_prompt = original_prompt
        agent_instance.model = original_model
        agent_instance.provider = original_provider


def test_update_config_rejects_missing_local_model():
    original_model = agent_instance.model
    original_provider = agent_instance.provider
    try:
        with patch(
            "backend.ollama_client.OllamaClient.list_models",
            new=AsyncMock(return_value=[{"name": "installed:latest"}]),
        ):
            response = client.post("/api/config", json={"model": "missing-model", "provider": "ollama"})

        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "ollama_model_not_installed"
        assert agent_instance.model == original_model
    finally:
        agent_instance.model = original_model
        agent_instance.provider = original_provider

def test_upload_and_list_files():
    import io
    import os
    # Test uploading a file
    file_content = b"month,revenue\nJan,100\nFeb,150\n"
    file_name = "test_sales.csv"
    
    response = client.post(
        "/api/upload",
        files={"file": (file_name, io.BytesIO(file_content), "text/csv")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["filename"] == file_name
    
    # Test listing uploads
    response = client.get("/api/uploads")
    assert response.status_code == 200
    uploads = response.json()
    assert any(u["name"] == file_name for u in uploads)
    
    # Clean up uploaded file
    try:
        uploads_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "uploads")
        file_path = os.path.join(uploads_dir, file_name)
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass


def test_auth_flow():
    import backend.auth
    import backend.bot
    import os
    from unittest.mock import AsyncMock, MagicMock
    
    # 1. Test unauthorized request
    clean_client = TestClient(app)
    resp = clean_client.get("/api/status")
    assert resp.status_code == 401
    
    # 2. Test request code
    # Mock bot to avoid actual sending
    original_bot = backend.bot.telegram_app
    backend.bot.telegram_app = MagicMock()
    backend.bot.telegram_app.bot = AsyncMock()
    
    original_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    os.environ["TELEGRAM_CHAT_ID"] = "12345"
    
    try:
        resp = clean_client.post("/api/auth/request-code")
        assert resp.status_code == 200
        assert resp.json()["status"] == "success"
        
        # Check that OTP was generated
        assert backend.auth.current_otp != {}
        otp_code = backend.auth.current_otp["code"]
        
        # 3. Test verify code - failure
        resp = clean_client.post("/api/auth/verify-code", json={"code": "000000"})
        assert resp.status_code == 401
        
        # 4. Test verify code - success
        resp = clean_client.post("/api/auth/verify-code", json={"code": otp_code})
        assert resp.status_code == 200
        token = resp.json()["token"]
        assert token in backend.auth.active_sessions
        
        # 5. Verify the token actually grants access
        clean_client.headers = {"Authorization": f"Bearer {token}"}
        resp = clean_client.get("/api/status")
        assert resp.status_code == 200
        
    finally:
        # Restore mocks and env
        backend.bot.telegram_app = original_bot
        if original_chat_id is not None:
            os.environ["TELEGRAM_CHAT_ID"] = original_chat_id
        else:
            os.environ.pop("TELEGRAM_CHAT_ID", None)
