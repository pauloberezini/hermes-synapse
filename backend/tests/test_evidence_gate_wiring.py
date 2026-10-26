import json

from backend.evidence import EvidenceContext, PlanRef, evidence_ctx
from backend.governance import ApprovalQueue
from backend.tools import execute_tool


def test_pending_request_has_bundle_and_hash():
    out = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev1"))
    detail = ApprovalQueue.get_detail(out["request_id"])
    assert detail["bundle_hash"] and len(detail["bundle_hash"]) == 64
    assert detail["bundle"]["inputs"] == {"command": "echo hi"}


def test_retry_while_pending_reuses_snapshot():
    a = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev2"))
    tok = evidence_ctx.set(EvidenceContext(plan=PlanRef(agent="code", instructions="new", step_index=0, step_count=1)))
    try:
        b = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev2"))
    finally:
        evidence_ctx.reset(tok)
    assert a["request_id"] == b["request_id"]
    assert ApprovalQueue.get_detail(a["request_id"])["bundle"]["plan"] is None


def test_consumed_then_new_snapshot():
    a = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev3"))
    ApprovalQueue.resolve(a["request_id"], "APPROVED")
    execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev3")  # runs, consumes
    c = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev3"))
    assert c["request_id"] != a["request_id"]


def test_bundle_row_is_not_updatable_via_queue_api():
    a = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev4"))
    h = ApprovalQueue.get_detail(a["request_id"])["bundle_hash"]
    ApprovalQueue.resolve(a["request_id"], "APPROVED")
    assert ApprovalQueue.get_detail(a["request_id"])["bundle_hash"] == h
