import json
import threading
import time

from backend import decision_log as dl
from backend.gateway.decide import ON_TIMEOUT_PENDING_RETRY, decide
from backend.governance import ApprovalQueue
from backend.mcp_client import forget_mcp_server_tools


def teardown_function():
    forget_mcp_server_tools("gateway")


def _events_for(request_id: int) -> list[str]:
    return [row["event"] for row in dl.history(int(request_id))]


def test_settings_default_is_pending_retry(monkeypatch):
    from backend.gateway.decide import settings_from_env

    monkeypatch.delenv("HERMES_GATEWAY_WAIT", raising=False)
    cfg = settings_from_env()
    assert cfg["wait"] is False


def test_safe_tool_allows_without_queue_row():
    before = ApprovalQueue.count_pending()
    d = decide("s1", "Read", {"path": "README.md"}, wait=False)
    assert d.effect == "allow"
    assert ApprovalQueue.count_pending() == before


def test_high_risk_pending_retry_writes_requested_and_stays_pending():
    d = decide(
        "s_retry",
        "execute_command",
        {"command": "echo hi"},
        wait=False,
    )
    assert d.effect == "pending"
    assert d.status == "PENDING_APPROVAL"
    assert ApprovalQueue.get_status(d.request_id) == "PENDING"
    assert _events_for(d.request_id) == ["REQUESTED"]


def test_wait_approve_consumes_and_logs_chain():
    payload = {"command": "echo wait-ok"}
    request_holder: dict = {}

    def _approve():
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            pending = [
                r for r in ApprovalQueue.get_pending()
                if r["agent_id"] == "s_wait" and r["action_name"] == "execute_command"
            ]
            if pending:
                request_holder["id"] = pending[0]["id"]
                ApprovalQueue.resolve(pending[0]["id"], "APPROVED", resolver_note="spike")
                return
            time.sleep(0.05)

    t = threading.Thread(target=_approve)
    t.start()
    d = decide("s_wait", "execute_command", payload, wait=True, timeout_s=2.0)
    t.join(timeout=3)
    assert d.effect == "allow"
    assert d.status == "CONSUMED"
    rid = d.request_id or request_holder.get("id")
    assert ApprovalQueue.get_status(rid) == "CONSUMED"
    assert _events_for(rid) == ["REQUESTED", "APPROVED", "CONSUMED"]


def test_wait_reject_denies_and_does_not_consume():
    def _reject():
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            pending = [r for r in ApprovalQueue.get_pending() if r["agent_id"] == "s_rej"]
            if pending:
                ApprovalQueue.resolve(pending[0]["id"], "REJECTED", resolver_note="no")
                return
            time.sleep(0.05)

    t = threading.Thread(target=_reject)
    t.start()
    d = decide("s_rej", "execute_command", {"command": "rm -rf /"}, wait=True, timeout_s=2.0)
    t.join(timeout=3)
    assert d.effect == "deny"
    assert d.status == "REJECTED"
    assert _events_for(d.request_id) == ["REQUESTED", "REJECTED"]


def test_timeout_fail_closed_leaves_pending_row():
    start = time.monotonic()
    d = decide(
        "s_to",
        "execute_command",
        {"command": "sleep 9"},
        wait=True,
        timeout_s=0.25,
        on_timeout="fail_closed",
    )
    elapsed = time.monotonic() - start
    assert d.effect == "deny"
    assert d.status == "TIMEOUT"
    assert ApprovalQueue.get_status(d.request_id) == "PENDING"
    assert 0.2 <= elapsed < 1.5
    assert _events_for(d.request_id) == ["REQUESTED", "TIMEOUT"]


def test_timeout_pending_retry_returns_pending_quickly_enough():
    start = time.monotonic()
    d = decide(
        "s_pr",
        "execute_command",
        {"command": "sleep 9"},
        wait=True,
        timeout_s=0.2,
        on_timeout=ON_TIMEOUT_PENDING_RETRY,
    )
    elapsed = time.monotonic() - start
    assert d.effect == "pending"
    assert json.loads(json.dumps(d.body))["status"] == "PENDING_APPROVAL"
    assert elapsed < 1.5
    later = decide("s_pr", "execute_command", {"command": "sleep 9"}, wait=False)
    assert later.request_id == d.request_id
    assert "TIMEOUT" in _events_for(d.request_id)


def test_pending_retry_then_approve_consumes_once():
    payload = {"command": "echo once"}
    first = decide("s_once", "execute_command", payload, wait=False)
    assert first.effect == "pending"
    ApprovalQueue.resolve(first.request_id, "APPROVED")
    second = decide("s_once", "execute_command", payload, wait=False)
    assert second.effect == "allow"
    assert ApprovalQueue.get_status(first.request_id) == "CONSUMED"
    third = decide("s_once", "execute_command", payload, wait=False)
    assert third.effect == "pending"
    assert third.request_id != first.request_id
    assert _events_for(first.request_id) == ["REQUESTED", "APPROVED", "CONSUMED"]


def test_different_payload_is_a_new_request():
    a = decide("s_hash", "execute_command", {"command": "echo a"}, wait=False)
    b = decide("s_hash", "execute_command", {"command": "echo b"}, wait=False)
    assert a.request_id != b.request_id


def test_disconnect_cancels_wait_without_consume():
    cancel = threading.Event()

    def _flip():
        time.sleep(0.15)
        cancel.set()

    t = threading.Thread(target=_flip)
    t.start()
    d = decide(
        "s_disc",
        "execute_command",
        {"command": "echo disc"},
        wait=True,
        timeout_s=5.0,
        cancel=cancel,
    )
    t.join(timeout=3)
    assert d.status == "CANCELLED"
    assert ApprovalQueue.get_status(d.request_id) == "PENDING"
    assert _events_for(d.request_id) == ["REQUESTED", "TIMEOUT"]


def test_timeout_chain_verifies_offline(tmp_path):
    from backend.decision_log import export_zip, verify

    d = decide(
        "s_ver",
        "execute_command",
        {"command": "echo verify"},
        wait=True,
        timeout_s=0.2,
        on_timeout="fail_closed",
    )
    assert d.status == "TIMEOUT"
    result = verify()
    assert result.ok, result.error
    blob, _name = export_zip()
    zip_path = tmp_path / "decisions.zip"
    zip_path.write_bytes(blob)
    import subprocess
    import sys
    from pathlib import Path

    verifier = Path(__file__).resolve().parents[2] / "scripts" / "verify_decision_log.py"
    proc = subprocess.run(
        [sys.executable, str(verifier), str(zip_path), "--pin", result.head_hash],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "ok" in proc.stdout


def test_wait_for_decision_returns_pending_on_timeout():
    rid = ApprovalQueue.request_approval("s_poll", "execute_command", {"command": "x"})
    start = time.monotonic()
    status = ApprovalQueue.wait_for_decision(rid, timeout_s=0.2, poll_s=0.05)
    elapsed = time.monotonic() - start
    assert status == "PENDING"
    assert 0.15 <= elapsed < 1.2


def test_rejected_is_sticky_in_session():
    first = decide("s_sticky", "execute_command", {"command": "echo x"}, wait=False)
    ApprovalQueue.resolve(first.request_id, "REJECTED")
    again = decide("s_sticky", "execute_command", {"command": "echo x"}, wait=False)
    assert again.effect == "deny"
    assert again.status == "REJECTED"
    assert again.request_id == first.request_id
