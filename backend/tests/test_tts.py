from pathlib import Path

import pytest

from backend.tts import VoiceSynthesisError, get_tts_status, synthesize_speech


def test_tts_is_opt_in_and_never_downloads_models(monkeypatch):
    monkeypatch.setenv("VOICE_TTS_ENABLED", "false")
    monkeypatch.setenv("VOICE_TTS_PROVIDER", "auto")

    status = get_tts_status()

    assert status["enabled"] is False
    assert status["available"] is False
    assert status["browser_fallback"] is True
    assert status["downloads_models"] is False


def test_disabled_tts_rejects_synthesis_without_creating_audio(monkeypatch, tmp_path):
    monkeypatch.setenv("VOICE_TTS_ENABLED", "false")
    output = tmp_path / "answer.wav"

    with pytest.raises(VoiceSynthesisError, match="VOICE_TTS_ENABLED"):
        synthesize_speech("Привет. Я Vexa.", str(output))

    assert not Path(output).exists()


def test_tts_status_api_reports_safe_fallback(monkeypatch):
    from backend.auth import active_sessions
    from backend.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("VOICE_TTS_ENABLED", "false")
    active_sessions.add("tts-test-token")
    client = TestClient(app, headers={"Authorization": "Bearer tts-test-token"})

    response = client.get("/api/voice/tts/status")

    assert response.status_code == 200
    assert response.json()["browser_fallback"] is True


def test_tts_api_returns_service_unavailable_when_not_configured(monkeypatch):
    from backend.auth import active_sessions
    from backend.main import app
    from fastapi.testclient import TestClient

    monkeypatch.setenv("VOICE_TTS_ENABLED", "false")
    active_sessions.add("tts-test-token")
    client = TestClient(app, headers={"Authorization": "Bearer tts-test-token"})

    response = client.post("/api/voice/synthesize", json={"text": "Проверка Vexa."})

    assert response.status_code == 503
    assert "VOICE_TTS_ENABLED" in response.json()["detail"]
