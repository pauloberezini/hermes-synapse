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
