"""Unit tests for the immutable decision log and verification."""

from __future__ import annotations

import json
import threading
import pytest

from backend import decision_log as dl
from backend.identity import Principal

ADMIN = Principal(subject="alice", roles=("admin",))


def _append(i: int, event: str = "REQUESTED") -> str:
    return dl.append(
        event,
        request_id=i,
        actor="agent:a",
        action_name="execute_command",
        payload={"command": f"echo {i}"},
        bundle_hash=None,
    )


def test_first_entry_links_to_genesis() -> None:
    _append(1)
    rows = list(dl.history(1))
    assert rows[0]["prev_hash"] == dl.GENESIS


def test_chain_links() -> None:
    h1 = _append(1)
    _append(2)
    assert dl.history(2)[0]["prev_hash"] == h1


def test_verify_ok_on_clean_chain() -> None:
    for i in range(5):
        _append(i)
    r = dl.verify()
    assert r.ok and r.checked == 5


def test_update_blocked_by_storage() -> None:
    _append(1)
    with pytest.raises(Exception, match="append-only"):
        from backend.database import _execute

        _execute("UPDATE approval_decisions SET reason='x'")


def test_delete_blocked_by_storage() -> None:
    _append(1)
    with pytest.raises(Exception, match="append-only"):
        from backend.database import _execute

        _execute("DELETE FROM approval_decisions")


def test_verify_detects_tamper(tamper_decision_row) -> None:  # fixture drops trigger, edits row 3, restores trigger
    for i in range(5):
        _append(i)
    tamper_decision_row(seq=3, reason="forged")
    r = dl.verify()
    assert not r.ok and r.first_bad_seq == 3


def test_concurrent_appends_keep_linear_chain() -> None:
    ts = [threading.Thread(target=_append, args=(i,)) for i in range(20)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert dl.verify().ok


def test_evidence_update_is_rejected_and_delete_is_allowed() -> None:
    from backend.evidence import build_bundle
    from backend.governance import ApprovalQueue

    bundle = build_bundle("agent", "execute_command", {"command": "echo hi"}, None)
    request_id = ApprovalQueue.request_approval(
        "agent",
        "execute_command",
        {"command": "echo hi"},
        bundle=bundle,
    )
    with pytest.raises(Exception, match="append-only"):
        from backend.database import _execute

        _execute(
            "UPDATE approval_evidence SET bundle_hash = ? WHERE request_id = ?",
            ("x", request_id),
        )
    from backend.database import _execute

    _execute("DELETE FROM approval_evidence WHERE request_id = ?", (request_id,))
    left = _execute("SELECT request_id FROM approval_evidence WHERE request_id = ?", (request_id,))
    assert left == []


def test_verify_detects_edited_evidence() -> None:
    from backend.database import _execute
    from backend.evidence import build_bundle
    from backend.governance import ApprovalQueue

    bundle = build_bundle("agent", "execute_command", {"command": "echo hi"}, None)
    request_id = ApprovalQueue.request_approval(
        "agent",
        "execute_command",
        {"command": "echo hi"},
        bundle=bundle,
    )
    assert dl.verify().ok
    stored = _execute("SELECT bundle_json FROM approval_evidence WHERE request_id = ?", (request_id,))
    edited = json.loads(stored[0][0])
    edited["inputs"] = {"command": "tampered"}
    _execute("DROP TRIGGER IF EXISTS approval_evidence_no_update")
    _execute(
        "UPDATE approval_evidence SET bundle_json = ? WHERE request_id = ?",
        (json.dumps(edited), request_id),
    )
    result = dl.verify()
    assert result.ok is False
    assert result.error == "bundle_hash mismatch"


def test_reason_is_pii_redacted() -> None:
    dl.append(
        "REJECTED",
        request_id=1,
        actor=ADMIN,
        action_name="x",
        payload={},
        bundle_hash=None,
        reason="call me +1 415 555 0100",
    )
    assert "555" not in dl.history(1)[0]["reason"]
