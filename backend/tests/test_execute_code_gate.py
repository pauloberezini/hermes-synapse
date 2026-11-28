"""R1-2: execute_code goes through gate_tool (HITL, payload bind, decision log, kill switch)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend import decision_log as dl
from backend.database import save_subagent
from backend.governance import ApprovalQueue, current_agent_tools
from backend.orchestrator import run_orchestration
from backend.subagents import CodeAgent, execute_code


def _ok_sandbox(stdout: str = "ok\n"):
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {
        "success": True,
        "stdout": stdout,
        "stderr": "",
        "display_data": [],
    }
    return resp


def _posted_code(mock_post) -> str:
    args, kwargs = mock_post.call_args
    payload = kwargs.get("json") or (args[1] if len(args) > 1 else {})
    return payload.get("code")


def test_execute_code_without_approval_is_blocked():
    with patch("backend.subagents.requests.post") as mock_post:
        res = execute_code("print(1)")
    mock_post.assert_not_called()
    assert res["success"] is False
    assert res["status"] == "PENDING_APPROVAL"
    assert res["request_id"]
    assert ApprovalQueue.get_status(res["request_id"]) == "PENDING"


def test_execute_code_runs_once_after_approval():
    code = "print('approved')"
    with patch("backend.subagents.requests.post", return_value=_ok_sandbox("approved\n")) as mock_post:
        pending = execute_code(code)
        ApprovalQueue.resolve(pending["request_id"], "APPROVED")
        done = execute_code(code)

        mock_post.assert_called_once()
        assert _posted_code(mock_post) == code
        assert done["success"] is True
        assert done["stdout"].strip() == "approved"
        assert ApprovalQueue.get_status(pending["request_id"]) == "CONSUMED"

        mock_post.reset_mock()
        replay = execute_code(code)
        mock_post.assert_not_called()
        assert replay["status"] == "PENDING_APPROVAL"
        assert replay["request_id"] != pending["request_id"]


def test_approval_cannot_be_reused_with_different_payload():
    with patch("backend.subagents.requests.post", return_value=_ok_sandbox()) as mock_post:
        pending = execute_code("print(1)")
        ApprovalQueue.resolve(pending["request_id"], "APPROVED")

        other = execute_code("print(2)")
        mock_post.assert_not_called()
        assert other["status"] == "PENDING_APPROVAL"
        assert other["request_id"] != pending["request_id"]

        done = execute_code("print(1)")
        mock_post.assert_called_once()
        assert _posted_code(mock_post) == "print(1)"
        assert done["success"] is True


def test_execute_code_writes_decision_log():
    with patch("backend.subagents.requests.post", return_value=_ok_sandbox()):
        pending = execute_code("print('log')")
        req_id = pending["request_id"]
        assert [e["event"] for e in dl.history(req_id)] == ["REQUESTED"]

        ApprovalQueue.resolve(req_id, "APPROVED")
        execute_code("print('log')")

    events = [e["event"] for e in dl.history(req_id)]
    assert events == ["REQUESTED", "APPROVED", "CONSUMED"]


def test_kill_switch_blocks_execute_code(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODE_AGENTS_ENABLED", "false")
    before = ApprovalQueue.count_pending()
    with patch("backend.subagents.requests.post") as mock_post:
        res = execute_code("print(1)")
    mock_post.assert_not_called()
    assert res["status"] == "DISABLED"
    assert res["success"] is False
    assert ApprovalQueue.count_pending() == before


def test_kill_switch_unrecognised_value_fails_closed(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODE_AGENTS_ENABLED", "maybe")
    with patch("backend.subagents.requests.post") as mock_post:
        res = execute_code("print(1)")
    mock_post.assert_not_called()
    assert res["status"] == "DISABLED"


@pytest.mark.asyncio
async def test_kill_switch_skips_llm_in_code_agent(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODE_AGENTS_ENABLED", "false")
    with patch("backend.subagents.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.subagents.requests.post") as mock_post:
        res = await CodeAgent(api_key="k", model="m").run_and_correct("print(1)")
    mock_llm.assert_not_called()
    mock_post.assert_not_called()
    assert res["status"] == "DISABLED"
    assert res["attempts"] == 0


def test_rejected_execute_code_stays_blocked():
    with patch("backend.subagents.requests.post") as mock_post:
        pending = execute_code("print(1)")
        ApprovalQueue.resolve(pending["request_id"], "REJECTED")
        again = execute_code("print(1)")
    mock_post.assert_not_called()
    assert again["status"] == "REJECTED"


def test_missing_tools_forbid_execute_code_without_approval():
    token = current_agent_tools.set(frozenset({"web_search"}))
    try:
        before = ApprovalQueue.count_pending()
        with patch("backend.subagents.requests.post") as mock_post:
            res = execute_code("print(1)")
        mock_post.assert_not_called()
        assert res["status"] == "FORBIDDEN"
        assert ApprovalQueue.count_pending() == before
    finally:
        current_agent_tools.reset(token)


@pytest.mark.asyncio
async def test_pending_does_not_self_correct():
    agent = CodeAgent(api_key="k", model="m")
    with patch("backend.subagents.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.subagents.requests.post") as mock_post:
        mock_llm.return_value = "```python\nprint(1)\n```"
        res = await agent.run_and_correct("print 1")
    mock_post.assert_not_called()
    assert mock_llm.call_count == 1
    assert res["status"] == "PENDING_APPROVAL"
    assert res["attempts"] == 1
    assert res["success"] is False


@pytest.mark.asyncio
async def test_parent_without_python_sandbox_skips_code_step():
    save_subagent(
        "cap_orch",
        "Capped",
        "p",
        "test-model",
        agent_type="orchestrator",
        skills="web_search",
    )
    save_subagent(
        "code",
        "Code Engineer",
        "p",
        "test-model",
        agent_type="agent",
        parent_id="cap_orch",
        skills="python_sandbox",
    )
    plan = json.dumps({"steps": [{"agent": "code", "instructions": "print(1)"}]})

    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.orchestrator.CodeAgent.run_and_correct", new_callable=AsyncMock) as mock_code, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.side_effect = [plan, "done"]
        result = await run_orchestration(
            "run code",
            "k",
            "test-model",
            chat_id="cap_orch",
            parent_skills="web_search",
        )

    mock_code.assert_not_called()
    assert any(r.get("agent") == "code" and "python_sandbox" in str(r.get("error")) for r in result.get("results", []))
    traces = result["traces"]
    assert any(t.get("agent") == "Code Agent" and t.get("action") == "Skip" for t in traces)
