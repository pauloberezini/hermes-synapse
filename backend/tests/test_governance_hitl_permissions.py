"""Permission and logging mutations wait for a human yes."""

import json

from backend.agent import JarvisAgent
from backend.database import _execute, get_chat_history, get_subagent, save_message
from backend.governance import ApprovalQueue, gate_tool
from backend.tools import execute_tool

_CREATE = {
    "subagent_id": "risky_hire",
    "name": "Risky",
    "system_prompt": "trade anything",
    "skills": "python_sandbox",
}


def test_create_subagent_waits_for_human_approval():
    raw = execute_tool("create_subagent", dict(_CREATE), chat_id="orch_boss")
    body = json.loads(raw)
    assert body["status"] == "PENDING_APPROVAL"
    assert body["request_id"]
    rows = _execute(
        "SELECT action_name, status FROM approval_requests WHERE action_name = ?",
        ("create_subagent",),
    )
    assert rows
    assert rows[0][1] == "PENDING"
    assert get_subagent("risky_hire") is None


def test_clear_history_requires_approval():
    save_message("gate_hist", "user", "keep me")
    result = JarvisAgent(api_key="k").clear_history("gate_hist")
    body = json.loads(result)
    assert body["status"] == "PENDING_APPROVAL"
    assert get_chat_history("gate_hist")

    blocked = gate_tool("gate_hist", "clear_decision_logs", {"session_id": "gate_hist"})
    log_body = json.loads(blocked)
    assert log_body["status"] == "PENDING_APPROVAL"
    names = {
        row[0]
        for row in _execute(
            "SELECT action_name FROM approval_requests WHERE action_name IN (?, ?)",
            ("clear_history", "clear_decision_logs"),
        )
    }
    assert names == {"clear_history", "clear_decision_logs"}


def test_rejected_subagent_creation_does_not_persist():
    first = json.loads(
        execute_tool("create_subagent", dict(_CREATE), chat_id="orch_boss")
    )
    assert first["status"] == "PENDING_APPROVAL"
    assert ApprovalQueue.resolve(first["request_id"], "REJECTED", "no")
    second = json.loads(
        execute_tool("create_subagent", dict(_CREATE), chat_id="orch_boss")
    )
    assert second["status"] == "REJECTED"
    assert get_subagent("risky_hire") is None
