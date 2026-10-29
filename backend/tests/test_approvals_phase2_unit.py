"""Unit tests for approvals demo hardening phase 2.

No HTTP app and no agent loop. The verifier is loaded from the script file.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from backend.governance import ApprovalQueue

_ROOT = Path(__file__).resolve().parents[2]
_VERIFIER = _ROOT / "scripts" / "verify_decision_log.py"


def _verifier():
    spec = importlib.util.spec_from_file_location("verify_decision_log_phase2", _VERIFIER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _linked_row(mod, *, seq: int, request_id: int, prev: str, command: str) -> tuple[dict, dict, str]:
    bundle = {
        "schema_ver": 1,
        "agent_id": "sess",
        "action_name": "execute_command",
        "inputs": {"command": command},
        "plan": None,
        "upstream": [],
        "flags": [],
    }
    body = {
        "tenant_id": "default",
        "request_id": request_id,
        "event": "REQUESTED",
        "actor_subject": "agent:test",
        "actor_roles": "[]",
        "auth_method": "agent",
        "action_name": "execute_command",
        "payload_hash": "ab",
        "bundle_hash": mod.bundle_hash(bundle),
        "reason": "",
        "occurred_at": "2026-10-29T12:00:00+00:00",
        "prev_hash": prev,
    }
    digest = mod.entry_hash(body)
    row = dict(body)
    row["seq"] = seq
    row["entry_hash"] = digest
    return row, bundle, digest


def _zip(path: Path, rows: list[dict], bundles: dict[int, dict], manifest: dict) -> None:
    import zipfile

    with zipfile.ZipFile(path, "w") as archive:
        lines = [json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for row in rows]
        archive.writestr("decisions.jsonl", "".join(f"{line}\n" for line in lines))
        archive.writestr("manifest.json", json.dumps(manifest))
        for request_id, bundle in bundles.items():
            archive.writestr(f"evidence/{request_id}.json", json.dumps(bundle))
        archive.writestr("VERIFY.md", "see scripts/verify_decision_log.py\n")


def test_verifier_usage_error_exits_1() -> None:
    mod = _verifier()
    assert mod.main(["verify_decision_log.py"]) == 1
    assert mod.main(["verify_decision_log.py", "export.zip", "--pin"]) == 1


def test_pin_fails_when_the_tail_row_was_dropped(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    mod = _verifier()
    first, bundle_a, first_hash = _linked_row(mod, seq=1, request_id=1, prev="0" * 64, command="echo 1")
    second, bundle_b, second_hash = _linked_row(mod, seq=2, request_id=2, prev=first_hash, command="echo 2")
    full = tmp_path / "full.zip"
    _zip(
        full,
        [first, second],
        {1: bundle_a, 2: bundle_b},
        {
            "count": 2,
            "first_seq": 1,
            "last_seq": 2,
            "head_hash": second_hash,
        },
    )
    assert mod.main(["verify_decision_log.py", str(full)]) == 0

    truncated = tmp_path / "truncated.zip"
    _zip(
        truncated,
        [first],
        {1: bundle_a},
        {"count": 1, "first_seq": 1, "last_seq": 1, "head_hash": first_hash},
    )
    assert mod.main(["verify_decision_log.py", str(truncated)]) == 0
    assert mod.main(["verify_decision_log.py", str(truncated), "--pin", second_hash]) == 1
    assert "pinned entry missing" in capsys.readouterr().err
    assert mod.main(["verify_decision_log.py", str(truncated), "--pin", first_hash]) == 0


def test_agent_name_is_blank_without_links() -> None:
    assert ApprovalQueue._agent_name(None) == ""
    assert ApprovalQueue._agent_name("{}") == ""
    assert ApprovalQueue._agent_name("not-json") == ""
    assert ApprovalQueue._agent_name('{"links":{"agent":"Sys Ops"}}') == "Sys Ops"


def test_approval_context_resets_after_error() -> None:
    from backend.agent import agent_name_ctx, approval_context
    from backend.evidence import evidence_ctx

    with pytest.raises(RuntimeError):
        with approval_context("Jarvis", "run uname", "jarvis"):
            assert agent_name_ctx.get() == "Jarvis"
            assert evidence_ctx.get() is not None
            raise RuntimeError("boom")
    assert agent_name_ctx.get() == ""
    assert evidence_ctx.get() is None


def test_evidence_update_is_rejected_delete_is_not() -> None:
    from backend.database import _execute
    from backend.evidence import build_bundle

    bundle = build_bundle("agent", "execute_command", {"command": "echo hi"}, None)
    request_id = ApprovalQueue.request_approval(
        "agent",
        "execute_command",
        {"command": "echo hi"},
        bundle=bundle,
    )
    with pytest.raises(Exception, match="append-only"):
        _execute(
            "UPDATE approval_evidence SET bundle_hash = ? WHERE request_id = ?",
            ("x", request_id),
        )
    _execute("DELETE FROM approval_evidence WHERE request_id = ?", (request_id,))
    assert _execute(
        "SELECT request_id FROM approval_evidence WHERE request_id = ?",
        (request_id,),
    ) == []
