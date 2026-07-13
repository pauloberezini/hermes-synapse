"""
hermes_sdk.testing — Test utilities for Hermes skill authors.

Provides a MockHermesContext that lets you unit test your skills
without a running Hermes backend or real API keys.

Usage:
    from hermes_sdk.testing import MockHermesContext

    def test_my_skill():
        ctx = MockHermesContext(env={"MY_API_KEY": "test_key_123"})
        skill_instance = MySkill()
        skill_instance._mock_context = ctx

        result = skill_instance.my_tool_method(param="hello")
        assert "expected output" in result

The MockHermesContext patches os.environ for the duration of the test
so that self.get_env() works without real env vars.
"""

import os
from contextlib import contextmanager
from unittest.mock import patch
from typing import Any


class MockHermesContext:
    """
    Test context that simulates the Hermes runtime environment for skills.

    Args:
        env: Dict of environment variable overrides for this test session.
        tool_responses: Dict mapping tool_name → response string for
                        mocking calls to other tools (e.g. web_search).

    Example:
        ctx = MockHermesContext(
            env={"GITHUB_TOKEN": "ghp_test123"},
            tool_responses={"web_search": "Mock search result"},
        )
        with ctx.activate():
            instance = MyGitHubSkill()
            result = instance.get_issues(repo="owner/repo")
        assert "issues" in result.lower()
    """

    def __init__(
        self,
        env: dict[str, str] | None = None,
        tool_responses: dict[str, Any] | None = None,
    ):
        self.env = env or {}
        self.tool_responses = tool_responses or {}
        self._calls: list[dict] = []

    @contextmanager
    def activate(self):
        """
        Context manager that patches os.environ with the mock env vars.

        Usage:
            with ctx.activate():
                result = my_skill.my_tool()
        """
        with patch.dict(os.environ, self.env, clear=False):
            yield self

    def record_call(self, tool_name: str, params: dict) -> None:
        """Record a tool invocation for assertion in tests."""
        self._calls.append({"tool": tool_name, "params": params})

    def get_calls(self, tool_name: str | None = None) -> list[dict]:
        """Return recorded calls, optionally filtered by tool name."""
        if tool_name:
            return [c for c in self._calls if c["tool"] == tool_name]
        return self._calls

    def assert_called_with(self, tool_name: str, **params) -> None:
        """Assert that a tool was called with specific parameters."""
        matching = [
            c for c in self._calls
            if c["tool"] == tool_name and all(
                c["params"].get(k) == v for k, v in params.items()
            )
        ]
        if not matching:
            calls_summary = [
                f"  {c['tool']}({c['params']})" for c in self._calls
            ]
            raise AssertionError(
                f"Expected call to '{tool_name}' with {params} not found.\n"
                f"Actual calls:\n" + "\n".join(calls_summary or ["  (none)"])
            )

    def assert_not_called(self, tool_name: str) -> None:
        """Assert that a tool was never called."""
        matching = [c for c in self._calls if c["tool"] == tool_name]
        if matching:
            raise AssertionError(
                f"Expected '{tool_name}' to NOT be called, but it was called "
                f"{len(matching)} time(s)."
            )


def skill_test(env: dict[str, str] | None = None, tool_responses: dict[str, Any] | None = None):
    """
    Decorator factory for skill test functions.
    Automatically activates MockHermesContext and passes it to the test.

    Usage:
        @skill_test(env={"MY_API_KEY": "test_key"})
        def test_my_skill(ctx: MockHermesContext):
            instance = MySkill()
            result = instance.my_tool("input")
            assert "expected" in result

    Args:
        env: Environment variables to set during the test.
        tool_responses: Mock responses for Hermes tool calls.
    """
    def decorator(fn):
        def wrapper(*args, **kwargs):
            ctx = MockHermesContext(env=env, tool_responses=tool_responses)
            with ctx.activate():
                return fn(ctx, *args, **kwargs)
        wrapper.__name__ = fn.__name__
        wrapper.__doc__ = fn.__doc__
        return wrapper
    return decorator
