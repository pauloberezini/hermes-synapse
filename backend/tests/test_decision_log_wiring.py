"""Integration wiring tests for governance and immutable decision log."""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from backend import decision_log as dl
from backend.evidence import EvidenceContext, build_bundle
from backend.governance import ApprovalQueue
from backend.identity import Principal
from backend.tools import execute_tool

_ADMIN = Principal(subject="alice", roles=("admin",))


def test_gate_request_writes_REQUESTED_with_bundle_hash() -> None:
    out = json.loads(execute_tool("execute_command", {"command": "echo test"}, chat_id="dl_wire_1"))
    req_id = out["request_id"]
    entries = dl.history(req_id)
    assert len(entries) >= 1
    req_entry = entries[0]
    assert req_entry["event"] == "REQUESTED"
    assert req_entry["actor_subject"].startswith("agent:")
    assert req_entry["bundle_hash"] is not None
    assert len(req_entry["bundle_hash"]) == 64


def test_resolve_writes_APPROVED_with_principal_subject() -> None:
    req_id = ApprovalQueue.request_approval(
        agent_id="test_agent",
        action_name="execute_command",
        payload={"command": "echo 1"},
    )
    ok = ApprovalQueue.resolve(req_id, "APPROVED", "looks good", principal=_ADMIN)
    assert ok is True
    entries = dl.history(req_id)
    resolve_entry = entries[-1]
    assert resolve_entry["event"] == "APPROVED"
    assert resolve_entry["actor_subject"] == "alice"
    assert "admin" in json.loads(resolve_entry["actor_roles"])
    assert resolve_entry["reason"] == "looks good"


def test_consume_writes_CONSUMED() -> None:
    req_id = ApprovalQueue.request_approval(
        agent_id="test_agent",
        action_name="execute_command",
        payload={"command": "echo 1"},
    )
    ApprovalQueue.resolve(req_id, "APPROVED", principal=_ADMIN)
    ApprovalQueue.consume(req_id)

    entries = dl.history(req_id)
    assert len(entries) == 3
    consume_entry = entries[-1]
    assert consume_entry["event"] == "CONSUMED"
    assert consume_entry["actor_subject"] == "system"


def test_full_lifecycle_order_is_REQUESTED_APPROVED_CONSUMED() -> None:
    req_id = ApprovalQueue.request_approval(
        agent_id="test_agent",
        action_name="execute_command",
        payload={"command": "echo 1"},
    )
    ApprovalQueue.resolve(req_id, "APPROVED", principal=_ADMIN)
    ApprovalQueue.consume(req_id)

    events = [e["event"] for e in dl.history(req_id)]
    assert events == ["REQUESTED", "APPROVED", "CONSUMED"]


def test_resolve_twice_returns_false_and_logs_once() -> None:
    req_id = ApprovalQueue.request_approval(
        agent_id="test_agent",
        action_name="execute_command",
        payload={"command": "echo 1"},
    )
    first = ApprovalQueue.resolve(req_id, "APPROVED", principal=_ADMIN)
    second = ApprovalQueue.resolve(req_id, "APPROVED", principal=_ADMIN)
    assert first is True
    assert second is False

    events = [e["event"] for e in dl.history(req_id)]
    assert events.count("APPROVED") == 1


def test_status_and_log_atomic(monkeypatch: pytest.MonkeyPatch) -> None:
    req_id = ApprovalQueue.request_approval(
        agent_id="test_agent",
        action_name="execute_command",
        payload={"command": "echo 1"},
    )

    def _failing_append(*args, **kwargs):
        raise RuntimeError("simulated storage failure during append")

    monkeypatch.setattr(dl, "append", _failing_append)

    with pytest.raises(RuntimeError, match="simulated storage failure"):
        ApprovalQueue.resolve(req_id, "APPROVED", principal=_ADMIN)

    # Status must still be PENDING because transaction rolled back atomically
    assert ApprovalQueue.get_status(req_id) == ApprovalQueue.STATUS_PENDING


def test_only_governance_writes_decisions() -> None:
    """Grep test: INSERT INTO approval_decisions appears only in backend/decision_log.py."""
    backend_dir = Path(__file__).resolve().parents[1]
    matching_files = []
    for py_file in backend_dir.rglob("*.py"):
        if "tests" in py_file.parts:
            continue
        content = py_file.read_text(encoding="utf-8")
        if "INSERT INTO approval_decisions" in content:
            matching_files.append(py_file.name)

    assert matching_files == ["decision_log.py"]
