"""Approval decisions are an append-only hash chain."""

import pytest

from backend import database as db
from backend import decision_log as dl


def _append(i: int) -> str:
    return dl.append(
        "REQUESTED",
        request_id=i,
        actor="agent:a",
        action_name="execute_command",
        payload={"command": f"echo {i}"},
        bundle_hash=None,
    )


def test_decision_log_is_append_only():
    _append(1)
    with pytest.raises(Exception, match="append-only"):
        db._execute("UPDATE approval_decisions SET reason = ?", ("x",))
    with pytest.raises(Exception, match="append-only"):
        db._execute("DELETE FROM approval_decisions")


def test_hash_chain_verification():
    for i in range(4):
        _append(i)
    clean = dl.verify("default")
    assert clean.ok
    assert clean.checked == 4

    rows = db._execute("SELECT seq FROM approval_decisions ORDER BY seq")
    target = rows[1][0]
    db._execute("DROP TRIGGER IF EXISTS approval_decisions_no_update")
    db._execute(
        "UPDATE approval_decisions SET reason = ? WHERE seq = ?",
        ("forged", target),
    )
    broken = dl.verify("default")
    assert not broken.ok
    assert broken.first_bad_seq == target
