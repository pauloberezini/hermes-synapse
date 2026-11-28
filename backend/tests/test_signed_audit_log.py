"""Signed audit log: installation key, checkpoints, export, offline verifier."""

from __future__ import annotations

import base64
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from fastapi.testclient import TestClient

from backend.auth import create_session
from backend import decision_log as dl
from hermes_audit_verify import (
    checkpoint_payload,
    entry_hash,
    fingerprint_hex,
    public_key_b64,
    verify_bundle,
)

_ROOT = Path(__file__).resolve().parents[2]


def _client() -> TestClient:
    from backend.main import app

    token = create_session()
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def _append(i: int) -> str:
    return dl.append(
        "REQUESTED",
        request_id=i,
        actor="agent:a",
        action_name="execute_command",
        payload={"command": f"echo {i}"},
        bundle_hash=None,
    )


def _run_verifier(bundle_path: Path, fingerprint: str | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "-m", "hermes_audit_verify", str(bundle_path)]
    if fingerprint:
        cmd.extend(["--pubkey-fingerprint", fingerprint])
    env = os.environ.copy()
    env["PYTHONPATH"] = str(_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(cmd, capture_output=True, text=True, check=False, cwd=str(_ROOT), env=env)


def _synthetic_record(seq: int, prev: str) -> dict:
    body = {
        "tenant_id": "default",
        "request_id": seq,
        "event": "REQUESTED",
        "actor_subject": "agent:a",
        "actor_roles": "[]",
        "auth_method": "agent",
        "action_name": "execute_command",
        "payload_hash": "a" * 64,
        "bundle_hash": None,
        "reason": "",
        "occurred_at": f"2026-01-01T00:00:0{seq}Z",
        "prev_hash": prev,
    }
    digest = entry_hash(body)
    return {**body, "seq": seq, "entry_hash": digest}


def _synthetic_chain(n: int) -> list[dict]:
    rows = []
    prev = "0" * 64
    for seq in range(1, n + 1):
        row = _synthetic_record(seq, prev)
        rows.append(row)
        prev = row["entry_hash"]
    return rows


def _pair():
    private = Ed25519PrivateKey.generate()
    raw = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, raw, fingerprint_hex(raw), public_key_b64(raw)


def _signed_checkpoint(private, seq: int, head_hash: str, installation_id: str) -> dict:
    timestamp = "2026-01-01T00:00:00+00:00"
    signature = private.sign(checkpoint_payload(seq, head_hash, timestamp, installation_id))
    return {
        "seq": seq,
        "head_hash": head_hash,
        "timestamp": timestamp,
        "installation_id": installation_id,
        "signature": base64.b64encode(signature).decode("ascii"),
    }


def _bundle(private, raw, rows, checkpoints, installation_id="inst-1") -> dict:
    return {
        "version": 1,
        "installation_id": installation_id,
        "public_key": public_key_b64(raw),
        "pubkey_fingerprint": fingerprint_hex(raw),
        "tenant_id": "default",
        "exported_at": "2026-01-01T00:00:00+00:00",
        "records": rows,
        "checkpoints": checkpoints,
    }


def test_verify_script_has_no_backend_imports() -> None:
    content = (_ROOT / "hermes_audit_verify.py").read_text(encoding="utf-8")
    assert "from backend" not in content
    assert "import backend" not in content


def test_install_key_mode_0600_and_fingerprint(tmp_path: Path, monkeypatch) -> None:
    from backend.audit_signing import ensure_install_key, reset_for_tests

    path = tmp_path / "audit_ed25519.key"
    monkeypatch.setenv("HERMES_AUDIT_KEY_PATH", str(path))
    reset_for_tests()
    first = ensure_install_key()
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600
    assert len(first.fingerprint) == 64
    assert len(first.raw_public) == 32
    reset_for_tests()
    second = ensure_install_key()
    assert second.fingerprint == first.fingerprint
    assert second.installation_id == first.installation_id


def test_audit_key_endpoint_requires_auth_and_is_readonly() -> None:
    from backend.main import app

    bare = TestClient(app)
    assert bare.get("/api/governance/audit/key").status_code == 401
    client = _client()
    resp = client.get("/api/governance/audit/key")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["pubkey_fingerprint"]) == 64
    assert body["public_key"]
    assert body["installation_id"]
    assert client.post("/api/governance/audit/key").status_code == 405


def test_checkpoint_every_n_and_export_signs_head(monkeypatch) -> None:
    monkeypatch.setenv("HERMES_AUDIT_CHECKPOINT_EVERY", "2")
    for i in range(1, 6):
        _append(i)
    stored = dl.list_checkpoints("default")
    assert [c["seq"] for c in stored] == [2, 4]
    body, filename = dl.export_signed_bundle()
    assert filename.endswith(".json")
    bundle = json.loads(body)
    assert bundle["version"] == 1
    assert [c["seq"] for c in bundle["checkpoints"]] == [2, 4, 5]
    report = verify_bundle(bundle, expected_fingerprint=bundle["pubkey_fingerprint"])
    assert report.ok
    assert report.checked == 5
    assert report.unsigned_tail == 0


def test_valid_bundle_passes_cli(tmp_path: Path) -> None:
    private, raw, fp, _pub = _pair()
    rows = _synthetic_chain(3)
    checkpoints = [_signed_checkpoint(private, 3, rows[-1]["entry_hash"], "inst-1")]
    bundle = _bundle(private, raw, rows, checkpoints)
    path = tmp_path / "ok.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    ran = _run_verifier(path, fp)
    assert ran.returncode == 0, ran.stderr
    assert "ok checked=3" in ran.stdout
    assert "unsigned_tail=0" in ran.stdout


def test_tampered_record_fails(tmp_path: Path) -> None:
    private, raw, fp, _pub = _pair()
    rows = _synthetic_chain(3)
    rows[1]["reason"] = "forged"
    checkpoints = [_signed_checkpoint(private, 3, rows[-1]["entry_hash"], "inst-1")]
    path = tmp_path / "tamper.json"
    path.write_text(json.dumps(_bundle(private, raw, rows, checkpoints)), encoding="utf-8")
    ran = _run_verifier(path, fp)
    assert ran.returncode == 1
    assert "entry_hash mismatch" in ran.stderr


def test_truncated_tail_detected(tmp_path: Path) -> None:
    private, raw, fp, _pub = _pair()
    rows = _synthetic_chain(5)
    checkpoints = [_signed_checkpoint(private, 5, rows[-1]["entry_hash"], "inst-1")]
    truncated = _bundle(private, raw, rows[:-2], checkpoints)
    path = tmp_path / "trunc.json"
    path.write_text(json.dumps(truncated), encoding="utf-8")
    ran = _run_verifier(path, fp)
    assert ran.returncode == 1
    assert "tail" in ran.stderr


def test_reordered_records_fail(tmp_path: Path) -> None:
    private, raw, fp, _pub = _pair()
    rows = _synthetic_chain(3)
    rows[0], rows[1] = rows[1], rows[0]
    checkpoints = [_signed_checkpoint(private, 3, rows[2]["entry_hash"], "inst-1")]
    path = tmp_path / "reorder.json"
    path.write_text(json.dumps(_bundle(private, raw, rows, checkpoints)), encoding="utf-8")
    ran = _run_verifier(path, fp)
    assert ran.returncode == 1
    assert "prev_hash mismatch" in ran.stderr


def test_foreign_key_fails(tmp_path: Path) -> None:
    private, raw, fp, _pub = _pair()
    other, other_raw, _other_fp, _other_pub = _pair()
    rows = _synthetic_chain(2)
    checkpoints = [_signed_checkpoint(private, 2, rows[-1]["entry_hash"], "inst-1")]
    bundle = _bundle(private, other_raw, rows, checkpoints)
    path = tmp_path / "foreign.json"
    path.write_text(json.dumps(bundle), encoding="utf-8")
    ran = _run_verifier(path, fingerprint_hex(other_raw))
    assert ran.returncode == 1
    assert "signature" in ran.stderr


def test_fingerprint_mismatch_fails(tmp_path: Path) -> None:
    private, raw, fp, _pub = _pair()
    rows = _synthetic_chain(2)
    checkpoints = [_signed_checkpoint(private, 2, rows[-1]["entry_hash"], "inst-1")]
    path = tmp_path / "fp.json"
    path.write_text(json.dumps(_bundle(private, raw, rows, checkpoints)), encoding="utf-8")
    ran = _run_verifier(path, "ab" * 32)
    assert ran.returncode == 1
    assert "fingerprint mismatch" in ran.stderr


def test_jsonl_bundle_roundtrip(tmp_path: Path) -> None:
    private, raw, fp, _pub = _pair()
    rows = _synthetic_chain(2)
    checkpoints = [_signed_checkpoint(private, 2, rows[-1]["entry_hash"], "inst-1")]
    header = {
        "type": "header",
        "version": 1,
        "installation_id": "inst-1",
        "public_key": public_key_b64(raw),
        "pubkey_fingerprint": fp,
        "tenant_id": "default",
    }
    lines = [json.dumps(header)]
    for row in rows:
        lines.append(json.dumps({"type": "record", **row}))
    for checkpoint in checkpoints:
        lines.append(json.dumps({"type": "checkpoint", **checkpoint}))
    path = tmp_path / "bundle.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ran = _run_verifier(path, fp)
    assert ran.returncode == 0, ran.stderr


def test_signed_export_api_verifies() -> None:
    _append(1)
    _append(2)
    client = _client()
    resp = client.get("/api/governance/decisions/export.signed.json")
    assert resp.status_code == 200
    bundle = resp.json()
    assert bundle["version"] == 1
    report = verify_bundle(bundle, expected_fingerprint=bundle["pubkey_fingerprint"])
    assert report.ok
    assert report.checked == 2
