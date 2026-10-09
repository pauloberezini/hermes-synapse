"""Agents must call BudgetGuard before an LLM spend and ApprovalQueue before a high-risk tool."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.agent import JarvisAgent
from backend.governance import ApprovalQueue, BudgetExceededError
from backend.subagents import call_llm
from backend.tools import execute_tool


def _ok_response():
    resp = MagicMock()
    resp.status_code = 200
    resp.text = ""
    resp.headers = {}
    resp.json.return_value = {
        "choices": [{"message": {"role": "assistant", "content": "ok"}}]
    }
    return resp


def _agent():
    agent = JarvisAgent()
    agent.api_key = "test_key"
    agent.api_base = "https://openrouter.ai/api/v1"
    return agent


@pytest.mark.asyncio
async def test_respond_checks_budget_before_llm():
    def boom(session_id, estimated_cost_usd):
        raise BudgetExceededError(session_id, 2.0, 1.0)

    with patch("backend.governance.BudgetGuard.check", side_effect=boom) as chk, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        post.return_value = _ok_response()
        reply = await _agent().respond("hello", session_id="budget_main")

    chk.assert_called()
    assert chk.call_args.args[0] == "budget_main"
    post.assert_not_called()
    assert "spending cap" in reply


@pytest.mark.asyncio
async def test_subagent_checks_budget_before_llm():
    def boom(session_id, estimated_cost_usd):
        raise BudgetExceededError(session_id, 2.0, 1.0)

    with patch("backend.governance.BudgetGuard.check", side_effect=boom) as chk, \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post, \
         patch("backend.rag.search_memory", return_value=[]):
        post.return_value = _ok_response()
        reply = await _agent()._respond_as_subagent(
            "hi",
            {"id": "code_agent", "name": "Code", "system_prompt": "x", "model": "m", "skills": ""},
            chat_id="budget_sub",
        )

    chk.assert_called()
    assert chk.call_args.args[0] == "budget_sub"
    post.assert_not_called()
    assert "spending cap" in reply


@pytest.mark.asyncio
async def test_call_llm_checks_bound_session_before_post():
    seen = {}

    def boom(session_id, estimated_cost_usd):
        seen["sid"] = session_id
        raise BudgetExceededError(session_id, 1.0, 0.5)

    from backend.governance import budget_session

    with patch("backend.governance.BudgetGuard.check", side_effect=boom), \
         patch("httpx.AsyncClient.post", new_callable=AsyncMock) as post:
        post.return_value = _ok_response()
        token = budget_session.set("sess_42")
        try:
            with pytest.raises(BudgetExceededError):
                await call_llm([{"role": "user", "content": "hi"}], "k", "m")
        finally:
            budget_session.reset(token)

    assert seen["sid"] == "sess_42"
    post.assert_not_called()


def test_high_risk_tool_waits_for_human_then_runs_once():
    payload = {"command": "echo hi"}
    try:
        with patch("backend.tools.execute_command") as run:
            raw = execute_tool("execute_command", payload, chat_id="agent_1")
        run.assert_not_called()
        pending = json.loads(raw)
        assert pending["status"] == "PENDING_APPROVAL"
        assert ApprovalQueue.get_status(pending["request_id"]) == "PENDING"

        ApprovalQueue.resolve(pending["request_id"], "APPROVED")
        with patch("backend.tools.execute_command", return_value='{"stdout":"hi"}') as run:
            done = execute_tool("execute_command", payload, chat_id="agent_1")
        run.assert_called_once()
        assert "hi" in done

        with patch("backend.tools.execute_command") as run_again:
            again = execute_tool("execute_command", payload, chat_id="agent_1")
        run_again.assert_not_called()
        assert json.loads(again)["status"] == "PENDING_APPROVAL"
    finally:
        from backend.database import _execute
        _execute("DELETE FROM approval_requests WHERE agent_id = ?", ("agent_1",))


def test_safe_tool_skips_approval():
    before = ApprovalQueue.count_pending()
    raw = execute_tool("get_system_stats", {})
    assert ApprovalQueue.count_pending() == before
    assert "PENDING_APPROVAL" not in raw
