"""Approvals demo hardening: masked reads, thread broadcast, retry hint."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone

from backend.database import _execute
from backend.governance import ApprovalQueue, gate_tool
from backend.websocket_manager import manager

_SECRET = "sk-or-v1-" + ("a" * 24)
_PAYLOAD = {"command": f"echo {_SECRET}"}


def test_read_paths_mask_secrets_find_latest_keeps_raw() -> None:
    """API reads hide the key; same-call matching still sees the raw column."""
    request_id = ApprovalQueue.request_approval(
        agent_id="mask_agent",
        action_name="execute_command",
        payload=_PAYLOAD,
        description="list files",
    )
    blob = json.dumps(
        {
            "pending": ApprovalQueue.get_pending(),
            "all": ApprovalQueue.get_all(),
            "detail": ApprovalQueue.get_detail(request_id),
        },
        ensure_ascii=False,
    )
    assert _SECRET not in blob
    assert "[API_KEY_OPENAI_REDACTED]" in blob
    stored = _execute("SELECT payload FROM approval_requests WHERE id = ?", (request_id,))
    assert _SECRET in stored[0][0]
    match = ApprovalQueue.find_latest("mask_agent", "execute_command", _PAYLOAD)
    assert match is not None and match["id"] == request_id


def test_unparsed_payload_is_masked_as_a_string() -> None:
    """A payload column that is not JSON is masked in place, not returned raw."""
    now = datetime.now(timezone.utc).isoformat()
    _execute(
        "INSERT INTO approval_requests "
        "(agent_id, action_name, payload, description, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ("plain_agent", "execute_command", f"echo {_SECRET}", "plain", "PENDING", now),
    )
    rows = [row for row in ApprovalQueue.get_all() if row["agent_id"] == "plain_agent"]
    assert rows
    assert _SECRET not in rows[0]["payload"]
    assert "[API_KEY_OPENAI_REDACTED]" in rows[0]["payload"]
    assert not rows[0]["payload"].startswith("{")


def test_gate_tool_pending_reply_says_to_retry_identical_args() -> None:
    """The model is told to call again with the same arguments after approval."""
    raw = gate_tool("retry_hint_agent", "execute_command", {"command": "uname -a"})
    assert raw is not None
    body = json.loads(raw)
    assert body["status"] == "PENDING_APPROVAL"
    assert "identical arguments" in body["error"]


async def test_request_approval_broadcasts_from_worker_thread() -> None:
    """approval_update reaches a client when request_approval runs off the server loop."""

    class _FakeSocket:
        def __init__(self) -> None:
            self.sent: list[str] = []

        async def accept(self) -> None:
            return None

        async def send_text(self, text: str) -> None:
            self.sent.append(text)

    socket = _FakeSocket()
    await manager.connect(socket)
    try:
        request_id = await asyncio.to_thread(
            ApprovalQueue.request_approval,
            "thread_agent",
            "execute_command",
            {"command": "uname -a"},
            "uname",
        )
        for _ in range(50):
            if socket.sent:
                break
            await asyncio.sleep(0.01)
        assert socket.sent, "worker-thread broadcast was dropped"
        message = json.loads(socket.sent[-1])
        assert message["type"] == "approval_update"
        assert message["id"] == request_id
        assert message["status"] == "PENDING"
    finally:
        manager.disconnect(socket)


def test_agent_name_is_display_only_and_session_stays_the_key() -> None:
    from backend.agent import approval_context

    session_id = "chat42_sysops"
    with approval_context("Sys Ops", "run uname", "sysops"):
        raw = gate_tool(session_id, "execute_command", {"command": "uname -a"})
    body = json.loads(raw or "")
    row = next(item for item in ApprovalQueue.get_pending() if item["id"] == body["request_id"])
    detail = ApprovalQueue.get_detail(body["request_id"])
    assert row["agent_name"] == "Sys Ops"
    assert row["agent_id"] == session_id
    assert detail is not None
    assert detail["agent_name"] == "Sys Ops"
    assert detail["agent_id"] == session_id
    assert detail["bundle"]["links"]["agent"] == "Sys Ops"
    assert detail["bundle"]["plan"]["instructions"] == "run uname"
    assert detail["bundle"]["plan"]["step_count"] == 1
    assert "direct_route" in detail["bundle"]["flags"]
    assert "plan_missing" not in detail["bundle"]["flags"]
    assert "direct_route" in row["flags"]


def test_direct_route_does_not_replace_a_planner_plan() -> None:
    from backend.agent import approval_context
    from backend.evidence import EvidenceContext, PlanRef, evidence_ctx

    planner = EvidenceContext(
        plan=PlanRef(agent="sysops", instructions="planner said so", step_index=1, step_count=3),
    )
    token = evidence_ctx.set(planner)
    try:
        with approval_context("Sys Ops", "user text", "sysops"):
            raw = gate_tool("orch_session", "execute_command", {"command": "id"})
    finally:
        evidence_ctx.reset(token)
    detail = ApprovalQueue.get_detail(json.loads(raw or "")["request_id"])
    assert detail is not None
    assert detail["bundle"]["plan"]["instructions"] == "planner said so"
    assert detail["bundle"]["plan"]["step_index"] == 1
    assert "direct_route" not in detail["bundle"]["flags"]
    assert detail["agent_name"] == "Sys Ops"


def test_approved_call_is_not_consumed_in_another_session() -> None:
    from backend.agent import approval_context

    payload = {"command": "uname -a"}
    with approval_context("Sys Ops", "run uname", "sysops"):
        first = json.loads(gate_tool("session_a", "execute_command", payload) or "")
    ApprovalQueue.resolve(first["request_id"], "APPROVED")
    with approval_context("Sys Ops", "run uname", "sysops"):
        second = json.loads(gate_tool("session_b", "execute_command", payload) or "")
    assert second["status"] == "PENDING_APPROVAL"
    assert second["request_id"] != first["request_id"]
    assert ApprovalQueue.get_status(first["request_id"]) == "APPROVED"
