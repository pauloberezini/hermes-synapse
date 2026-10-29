"""Unit test ensuring the standalone verifier runs on raw fixtures without importing backend."""

from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_VERIFIER = _ROOT / "scripts" / "verify_decision_log.py"


def test_verify_script_has_no_backend_imports() -> None:
    content = _VERIFIER.read_text(encoding="utf-8")
    assert "backend" not in content


def test_standalone_verification_on_synthetic_zip(tmp_path: Path) -> None:
    # Synthetic bundle
    bundle = {
        "schema_ver": 1,
        "agent_id": "test_agent",
        "action_name": "execute_command",
        "inputs": {"cmd": "ls"},
        "plan": None,
        "upstream": [],
        "flags": [],
    }
    b_canonical = json.dumps(bundle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    import hashlib
    b_hash = hashlib.sha256(b_canonical.encode("utf-8")).hexdigest()

    # Synthetic row
    body = {
        "tenant_id": "default",
        "request_id": 1,
        "event": "REQUESTED",
        "actor_subject": "agent:test",
        "actor_roles": "[]",
        "auth_method": "agent",
        "action_name": "execute_command",
        "payload_hash": hashlib.sha256(b'{"cmd":"ls"}').hexdigest(),
        "bundle_hash": b_hash,
        "reason": "",
        "occurred_at": "2026-10-25T12:00:00Z",
        "prev_hash": "0" * 64,
    }
    body_canonical = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    e_hash = hashlib.sha256(body_canonical.encode("utf-8")).hexdigest()

    row = dict(body)
    row["seq"] = 1
    row["entry_hash"] = e_hash
    row_canonical = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    manifest = {
        "tenant": "default",
        "from": "2026-10-25",
        "to": "2026-10-25",
        "count": 1,
        "first_seq": 1,
        "last_seq": 1,
        "head_hash": e_hash,
        "exported_at": "2026-10-25T12:01:00Z",
        "exported_by": "local-admin",
        "schema_ver": 1,
    }

    zip_path = tmp_path / "test.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr("decisions.jsonl", f"{row_canonical}\n")
        z.writestr("evidence/1.json", json.dumps(bundle))

    res = subprocess.run(
        [sys.executable, str(_VERIFIER), str(zip_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, res.stderr
    assert "ok checked=1" in res.stdout


def test_approvals_guide_drops_false_security_claims() -> None:
    """The demo guide must not describe a route or guarantees the code does not have."""
    guide = (_ROOT / "docs" / "guide" / "approvals.md").read_text(encoding="utf-8")
    assert "export.zip" in guide
    for banned in ("chain intact", "encrypted", "signed manifest"):
        assert banned not in guide, banned
