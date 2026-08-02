"""
Unit tests for hermes_sdk package (skill decorator, SkillBase, MockHermesContext, and manifest generation).
"""
import pytest
from hermes_sdk import skill, tool, SkillBase, SkillManifest
from hermes_sdk.testing import MockHermesContext


@skill(name="weather_helper", description="Weather forecast integration skill")
class WeatherSkill(SkillBase):

    @tool(description="Get current weather for location")
    def get_weather(self, location: str) -> str:
        api_key = self.get_env("WEATHER_API_KEY", required=False)
        if not api_key:
            return "API key missing"
        return f"Weather in {location}: sunny"


def test_skill_decorator_and_manifest():
    instance = WeatherSkill()
    assert hasattr(instance, "_manifest")
    assert instance._manifest.name == "weather_helper"
    assert instance._manifest.description == "Weather forecast integration skill"

    manifest = instance.get_manifest()
    assert isinstance(manifest, SkillManifest)
    assert manifest.name == "weather_helper"
    assert manifest.description == "Weather forecast integration skill"
    assert len(manifest.tools) == 1
    assert manifest.tools[0].name == "get_weather"


def test_mock_hermes_context():
    ctx = MockHermesContext(
        env={"WEATHER_API_KEY": "mock_secret_key"},
        tool_responses={"get_weather": "Weather in Paris: sunny"}
    )
    
    with ctx.activate():
        instance = WeatherSkill()
        result = instance.get_weather(location="Paris")
        assert result == "Weather in Paris: sunny"

    # Test without env var
    with MockHermesContext(env={}).activate():
        instance = WeatherSkill()
        result_missing = instance.get_weather(location="Paris")
        assert result_missing == "API key missing"


def test_mock_hermes_context_assertions():
    ctx = MockHermesContext()
    ctx.record_call("get_weather", {"location": "London"})

    ctx.assert_called_with("get_weather", location="London")
    ctx.assert_not_called("get_forecast")

    with pytest.raises(AssertionError):
        ctx.assert_called_with("get_weather", location="Tokyo")


# ─── Tests for validate_skill_env (Issue #7) ─────────────────────────────────

import os
import sys
from hermes_sdk import validate_skill_env


@skill(
    name="validated_service",
    description="Skill with declared env requirements",
    requires_env=["VALIDATED_API_KEY", "VALIDATED_SECRET"],
    optional_env=["VALIDATED_OPTIONAL"],
)
class ValidatedServiceSkill(SkillBase):

    @tool(description="Call the validated service")
    def call_service(self, query: str) -> str:
        key = self.get_env("VALIDATED_API_KEY", required=False)
        if not key:
            return self.missing_key_message("VALIDATED_API_KEY")
        return f"Result for {query}"


def test_validate_skill_env_all_present(monkeypatch):
    """validate_skill_env returns ok=True when all required vars are set."""
    monkeypatch.setenv("VALIDATED_API_KEY", "test-key-123")
    monkeypatch.setenv("VALIDATED_SECRET", "test-secret-456")

    instance = ValidatedServiceSkill()
    result = validate_skill_env(instance._manifest)

    assert result["ok"] is True
    assert result["missing"] == []


def test_validate_skill_env_one_missing(monkeypatch):
    """validate_skill_env returns the correct missing key when one var is absent."""
    monkeypatch.setenv("VALIDATED_API_KEY", "test-key-123")
    monkeypatch.delenv("VALIDATED_SECRET", raising=False)

    instance = ValidatedServiceSkill()
    result = validate_skill_env(instance._manifest)

    assert result["ok"] is False
    assert "VALIDATED_SECRET" in result["missing"]
    assert "VALIDATED_API_KEY" not in result["missing"]


def test_validate_skill_env_all_missing(monkeypatch):
    """validate_skill_env lists all missing required vars."""
    monkeypatch.delenv("VALIDATED_API_KEY", raising=False)
    monkeypatch.delenv("VALIDATED_SECRET", raising=False)

    instance = ValidatedServiceSkill()
    result = validate_skill_env(instance._manifest)

    assert result["ok"] is False
    assert set(result["missing"]) == {"VALIDATED_API_KEY", "VALIDATED_SECRET"}


def test_validate_skill_env_optional_missing(monkeypatch):
    """validate_skill_env separately tracks optional vars that are absent."""
    monkeypatch.setenv("VALIDATED_API_KEY", "k")
    monkeypatch.setenv("VALIDATED_SECRET", "s")
    monkeypatch.delenv("VALIDATED_OPTIONAL", raising=False)

    instance = ValidatedServiceSkill()
    result = validate_skill_env(instance._manifest)

    assert result["ok"] is True
    assert "VALIDATED_OPTIONAL" in result["optional_missing"]


def test_validate_skill_env_empty_string_counts_as_missing(monkeypatch):
    """An env var set to an empty string is treated as missing."""
    monkeypatch.setenv("VALIDATED_API_KEY", "")
    monkeypatch.setenv("VALIDATED_SECRET", "s")

    instance = ValidatedServiceSkill()
    result = validate_skill_env(instance._manifest)

    assert result["ok"] is False
    assert "VALIDATED_API_KEY" in result["missing"]


def test_validate_skill_env_no_requirements():
    """Skills with no requires_env always validate as ok."""
    @skill(name="no_env_skill_test", description="No env skill")
    class NoEnvSkill(SkillBase):
        @tool(description="noop")
        def noop(self) -> str:
            return "ok"

    instance = NoEnvSkill()
    result = validate_skill_env(instance._manifest)
    assert result["ok"] is True
    assert result["missing"] == []


# ─── API integration tests for validate-env and runtime env endpoints ─────────

from fastapi.testclient import TestClient as _TestClient


def test_validate_env_api_endpoint(monkeypatch):
    """GET /api/marketplace/skills/{name}/validate-env returns correct payload."""
    from backend.auth import create_session
    from backend.main import app

    monkeypatch.setenv("VALIDATED_API_KEY", "k")
    monkeypatch.setenv("VALIDATED_SECRET", "s")

    token = create_session()
    with _TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
        response = client.get("/api/marketplace/skills/validated_service/validate-env")

    assert response.status_code == 200
    data = response.json()
    assert data["skill"] == "validated_service"
    assert "ok" in data
    assert "missing" in data
    assert "optional_missing" in data


def test_validate_env_api_404_for_unknown_skill():
    """GET /api/marketplace/skills/{name}/validate-env returns 404 for unknown skill."""
    from backend.auth import create_session
    from backend.main import app

    token = create_session()
    with _TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
        response = client.get("/api/marketplace/skills/definitely_not_registered_xyz/validate-env")

    assert response.status_code == 404


def test_set_runtime_env_api(monkeypatch):
    """POST /api/settings/env sets an env var in the running process."""
    from backend.auth import create_session
    from backend.main import app

    token = create_session()
    with _TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
        response = client.post(
            "/api/settings/env",
            json={"key": "TEST_RUNTIME_KEY_7", "value": "runtime-value-abc"}
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["persistent"] is False
    assert os.environ.get("TEST_RUNTIME_KEY_7") == "runtime-value-abc"


def test_set_runtime_env_api_blocked_keys():
    """POST /api/settings/env rejects dangerous system keys."""
    from backend.auth import create_session
    from backend.main import app

    token = create_session()
    with _TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
        response = client.post(
            "/api/settings/env",
            json={"key": "PATH", "value": "/injected"}
        )

    assert response.status_code == 400


def test_set_runtime_env_api_empty_key():
    """POST /api/settings/env rejects empty key name."""
    from backend.auth import create_session
    from backend.main import app

    token = create_session()
    with _TestClient(app, headers={"Authorization": f"Bearer {token}"}) as client:
        response = client.post(
            "/api/settings/env",
            json={"key": "", "value": "something"}
        )

    assert response.status_code == 400


