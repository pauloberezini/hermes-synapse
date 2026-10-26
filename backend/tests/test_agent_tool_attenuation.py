"""Child tools are the intersection of the child's skills and the parent's tools."""

import json
from unittest.mock import MagicMock, patch

import pytest

from backend.agent import agent_instance
from backend.database import save_subagent
from backend.governance import current_agent_tools
from backend.tools import call_subagent


def _ok_post(payload: dict):
    async def _mock_post(url, json=None, headers=None):
        payload["body"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        return resp

    return _mock_post


def _tool_names(payload: dict) -> set[str]:
    tools = (payload.get("body") or {}).get("tools") or []
    return {t.get("function", {}).get("name") for t in tools}


@pytest.mark.asyncio
async def test_child_cannot_receive_tools_outside_parent_set():
    """Parent has web_search only. A python_sandbox child must not get execute_command."""
    payload: dict = {}
    with patch("httpx.AsyncClient.post", side_effect=_ok_post(payload)), patch(
        "backend.rag.search_memory", return_value=[]
    ):
        await agent_instance._respond_as_subagent(
            "hi",
            {
                "id": "sandbox_child",
                "name": "Sandbox",
                "system_prompt": "run code",
                "model": "test-model",
                "skills": "python_sandbox",
                "agent_type": "agent",
            },
            caller_tools=frozenset({"web_search"}),
            session_id="attenuate_parent_web",
            include_history=False,
        )
    assert "execute_command" not in _tool_names(payload)


def test_call_subagent_propagates_caller_restrictions():
    """A low-privilege caller cannot reach a high-privilege subagent's tools."""
    save_subagent(
        "sheller",
        "Sheller",
        "run commands",
        "test-model",
        agent_type="agent",
        skills="python_sandbox",
    )
    payload: dict = {}
    token = current_agent_tools.set(frozenset({"web_search"}))
    try:
        with patch("httpx.AsyncClient.post", side_effect=_ok_post(payload)), patch(
            "backend.rag.search_memory", return_value=[]
        ):
            raw = call_subagent("sheller", "list the files")
    finally:
        current_agent_tools.reset(token)
    body = json.loads(raw)
    assert "error" not in body
    assert "execute_command" not in _tool_names(payload)
    assert _tool_names(payload) <= {"web_search"}


@pytest.mark.asyncio
async def test_management_tools_not_injected_if_parent_lacks_them():
    """An orchestrator child does not gain create_subagent the parent never had."""
    payload: dict = {}
    with patch("httpx.AsyncClient.post", side_effect=_ok_post(payload)), patch(
        "backend.rag.search_memory", return_value=[]
    ):
        await agent_instance._respond_as_subagent(
            "hire someone",
            {
                "id": "desk",
                "name": "Desk",
                "system_prompt": "coordinate",
                "model": "test-model",
                "skills": "web_search",
                "agent_type": "orchestrator",
            },
            caller_tools=frozenset({"web_search"}),
            session_id="attenuate_no_manage",
            include_history=False,
        )
    names = _tool_names(payload)
    assert "create_subagent" not in names
    assert "execute_command" not in names


@pytest.mark.asyncio
async def test_empty_skills_child_defaults_to_parent_intersection():
    """Empty skills must not fall open to the global tool superset."""
    payload: dict = {}
    with patch("httpx.AsyncClient.post", side_effect=_ok_post(payload)), patch(
        "backend.rag.search_memory", return_value=[]
    ):
        await agent_instance._respond_as_subagent(
            "hi",
            {
                "id": "blank",
                "name": "Blank",
                "system_prompt": "x",
                "model": "test-model",
                "skills": "",
                "agent_type": "agent",
            },
            caller_tools=frozenset({"web_search"}),
            session_id="attenuate_empty_skills",
            include_history=False,
        )
    names = _tool_names(payload)
    assert names <= {"web_search"}
    assert "execute_command" not in names
    assert "create_subagent" not in names
    assert "get_weather" not in names
