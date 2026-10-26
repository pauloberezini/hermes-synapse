"""Integration tests for in-flight evidence context propagation through orchestrator and ReAct turns."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch
import pytest

from backend.evidence import evidence_ctx, EvidenceContext, PlanRef
from backend.governance import ApprovalQueue
from backend.orchestrator import run_orchestration
from backend.tools import execute_tool


@pytest.mark.asyncio
async def test_orchestrated_step_attaches_plan_ref(monkeypatch: pytest.MonkeyPatch) -> None:
    # Plan returns 2 steps: first 'research', second 'code'
    planner_output = json.dumps({
        "steps": [
            {"agent": "research", "instructions": "Search documentation"},
            {"agent": "code", "instructions": "Execute script"},
        ]
    })

    # Mock planner LLM call
    async def _mock_planner(*args, **kwargs):
        return planner_output

    monkeypatch.setattr("backend.orchestrator.call_llm", _mock_planner)

    # Mock research agent run
    async def _mock_research_run(self, instructions):
        return "docs found"

    monkeypatch.setattr("backend.orchestrator.ResearchAgent.run", _mock_research_run)

    # Step 2: Code agent calls execute_command which triggers gate_tool
    intercepted_bundle: dict = {}

    async def _mock_code_run(self, instructions):
        out_raw = execute_tool("execute_command", {"command": "echo run"}, chat_id="orch_test_1")
        out = json.loads(out_raw)
        detail = ApprovalQueue.get_detail(out["request_id"])
        nonlocal intercepted_bundle
        intercepted_bundle = detail["bundle"]
        return {"success": True, "attempts": 1, "stdout": "done", "stderr": ""}

    monkeypatch.setattr("backend.orchestrator.CodeAgent.run_and_correct", _mock_code_run)

    await run_orchestration("build feature", "fake_key", "fake_model", chat_id="orch_test_1")

    assert intercepted_bundle.get("plan") is not None
    plan = intercepted_bundle["plan"]
    assert plan["step_index"] == 1
    assert plan["step_count"] == 2
    assert plan["agent"] == "code"


@pytest.mark.asyncio
async def test_prior_step_result_in_upstream_with_truncation_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    planner_output = json.dumps({
        "steps": [
            {"agent": "research", "instructions": "Fetch massive doc"},
            {"agent": "code", "instructions": "Process doc"},
        ]
    })

    async def _mock_planner(*args, **kwargs):
        return planner_output

    monkeypatch.setattr("backend.orchestrator.call_llm", _mock_planner)

    # Step 1 returns > 3000 chars
    massive_output = "x" * 3500

    async def _mock_research_run(self, instructions):
        return massive_output

    monkeypatch.setattr("backend.orchestrator.ResearchAgent.run", _mock_research_run)

    intercepted_bundle: dict = {}

    async def _mock_code_run(self, instructions):
        out_raw = execute_tool("execute_command", {"command": "echo process"}, chat_id="orch_test_2")
        out = json.loads(out_raw)
        detail = ApprovalQueue.get_detail(out["request_id"])
        nonlocal intercepted_bundle
        intercepted_bundle = detail["bundle"]
        return {"success": True, "attempts": 1, "stdout": "done", "stderr": ""}

    monkeypatch.setattr("backend.orchestrator.CodeAgent.run_and_correct", _mock_code_run)

    await run_orchestration("process huge data", "fake_key", "fake_model", chat_id="orch_test_2")

    assert "step_output_truncated" in intercepted_bundle.get("flags", [])
    upstream = intercepted_bundle.get("upstream", [])
    truncated_items = [u for u in upstream if u.get("reason") == "step_context_3000"]
    assert len(truncated_items) >= 1
    assert truncated_items[0]["truncated"] is True


@pytest.mark.asyncio
async def test_contextvar_does_not_leak_between_concurrent_turns() -> None:
    results: dict[str, str] = {}

    async def _turn(turn_id: str, agent: str, step_idx: int) -> None:
        p = PlanRef(agent=agent, instructions=f"turn {turn_id}", step_index=step_idx, step_count=5)
        c = EvidenceContext(plan=p)
        token = evidence_ctx.set(c)
        try:
            await asyncio.sleep(0.02)
            out_raw = execute_tool("execute_command", {"command": f"echo {turn_id}"}, chat_id=f"concurrent_{turn_id}")
            out = json.loads(out_raw)
            detail = ApprovalQueue.get_detail(out["request_id"])
            results[turn_id] = detail["bundle"]["plan"]["agent"]
        finally:
            evidence_ctx.reset(token)

    await asyncio.gather(
        _turn("A", "agent_A", 1),
        _turn("B", "agent_B", 3),
    )

    assert results["A"] == "agent_A"
    assert results["B"] == "agent_B"
