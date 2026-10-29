"""GET /api/governance/decisions/export returns a verifiable zip archive."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from backend.auth import create_session
from backend.evidence import build_bundle
from backend.governance import ApprovalQueue
from backend.main import app

_ROOT = Path(__file__).resolve().parents[2]
_VERIFIER = _ROOT / "scripts" / "verify_decision_log.py"


def _client() -> TestClient:
    token = create_session()
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def _seed(command: str) -> int:
    bundle = build_bundle("agent", "execute_command", {"command": command}, None)
    return ApprovalQueue.request_approval(
        "agent",
        "execute_command",
        {"command": command},
        bundle=bundle,
    )


def _zip(content: bytes) -> zipfile.ZipFile:
    return zipfile.ZipFile(io.BytesIO(content))


def _run_verifier(path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_VERIFIER), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_export_zip_alias_matches_export(tmp_path: Path) -> None:
    _seed("echo alias")
    client = _client()
    plain = client.get("/api/governance/decisions/export")
    alias = client.get("/api/governance/decisions/export.zip")
    assert plain.status_code == 200
    assert alias.status_code == 200
    assert plain.headers["content-type"].startswith("application/zip")
    assert alias.headers["content-type"].startswith("application/zip")

    def decisions(content: bytes) -> bytes:
        return _zip(content).read("decisions.jsonl")

    assert decisions(plain.content) == decisions(alias.content)
    path = tmp_path / "alias.zip"
    path.write_bytes(alias.content)
    verified = _run_verifier(path)
    assert verified.returncode == 0, verified.stderr


def test_pin_detects_dropped_tail(tmp_path: Path) -> None:
    for command in ("echo 1", "echo 2", "echo 3"):
        _seed(command)
    response = _client().get("/api/governance/decisions/export.zip")
    archive = _zip(response.content)
    lines = [line for line in archive.read("decisions.jsonl").decode().splitlines() if line.strip()]
    assert len(lines) >= 3
    kept_lines = lines[:-2]
    dropped = json.loads(lines[-1])
    kept_first = json.loads(kept_lines[0])
    kept_last = json.loads(kept_lines[-1])
    manifest = json.loads(archive.read("manifest.json"))
    manifest["count"] = len(kept_lines)
    manifest["first_seq"] = kept_first["seq"]
    manifest["last_seq"] = kept_last["seq"]
    manifest["head_hash"] = kept_last["entry_hash"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for name in archive.namelist():
            if name == "decisions.jsonl":
                out.writestr(name, ("\n".join(kept_lines) + "\n").encode())
            elif name == "manifest.json":
                out.writestr(name, json.dumps(manifest).encode())
            else:
                out.writestr(name, archive.read(name))
    path = tmp_path / "truncated.zip"
    path.write_bytes(buf.getvalue())

    open_check = _run_verifier(path)
    assert open_check.returncode == 0, open_check.stderr
    pinned = subprocess.run(
        [sys.executable, str(_VERIFIER), str(path), "--pin", dropped["entry_hash"]],
        capture_output=True,
        text=True,
        check=False,
    )
    assert pinned.returncode == 1
    assert "pinned entry missing" in pinned.stderr


def test_export_zip_contains_manifest_and_verifies(tmp_path: Path) -> None:
    first = _seed("echo 1")
    second = _seed("echo 2")
    response = _client().get("/api/governance/decisions/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/zip")

    archive = _zip(response.content)
    names = set(archive.namelist())
    assert {"decisions.jsonl", "manifest.json", "VERIFY.md"} <= names
    assert f"evidence/{first}.json" in names
    assert f"evidence/{second}.json" in names

    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["count"] == 2
    assert manifest["schema_ver"] == 1
    assert manifest["tenant"] == "default"
    assert manifest["first_seq"] < manifest["last_seq"]
    assert manifest["head_hash"]
    assert "verify_decision_log.py" in archive.read("VERIFY.md").decode()

    lines = archive.read("decisions.jsonl").decode().splitlines()
    assert [json.loads(line)["request_id"] for line in lines] == [first, second]

    export_path = tmp_path / "export.zip"
    export_path.write_bytes(response.content)
    verified = _run_verifier(export_path)
    assert verified.returncode == 0, verified.stderr


def test_export_respects_date_range() -> None:
    _seed("echo a")
    _seed("echo b")
    client = _client()

    empty = client.get(
        "/api/governance/decisions/export",
        params={"from": "2099-01-01", "to": "2099-12-31"},
    )
    assert empty.status_code == 200
    assert "hermes-decisions-default-2099-01-01-2099-12-31.zip" in empty.headers["content-disposition"]
    empty_zip = _zip(empty.content)
    empty_manifest = json.loads(empty_zip.read("manifest.json"))
    assert empty_manifest["count"] == 0
    assert empty_manifest["from"] == "2099-01-01"
    assert empty_manifest["to"] == "2099-12-31"
    assert empty_zip.read("decisions.jsonl").strip() == b""

    full = client.get(
        "/api/governance/decisions/export",
        params={"from": "2000-01-01", "to": "2099-12-31"},
    )
    full_manifest = json.loads(_zip(full.content).read("manifest.json"))
    assert full_manifest["count"] == 2
    assert full_manifest["from"] == "2000-01-01"
    assert full_manifest["to"] == "2099-12-31"


def test_verifier_reports_first_broken_seq(tmp_path: Path) -> None:
    _seed("echo tamper")
    response = _client().get("/api/governance/decisions/export")
    archive = _zip(response.content)
    line = archive.read("decisions.jsonl").decode().splitlines()[0]
    row = json.loads(line)
    row["reason"] = "forged"
    forged = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for name in archive.namelist():
            payload = forged.encode() if name == "decisions.jsonl" else archive.read(name)
            out.writestr(name, payload)
    path = tmp_path / "forged.zip"
    path.write_bytes(buf.getvalue())

    verified = _run_verifier(path)
    assert verified.returncode == 1
    assert f"seq={row['seq']}" in verified.stderr


def test_verifier_reports_missing_evidence(tmp_path: Path) -> None:
    _seed("echo evidence")
    response = _client().get("/api/governance/decisions/export")
    archive = _zip(response.content)
    row = json.loads(archive.read("decisions.jsonl").decode().splitlines()[0])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as out:
        for name in archive.namelist():
            if name.startswith("evidence/"):
                continue
            out.writestr(name, archive.read(name))
    path = tmp_path / "no-evidence.zip"
    path.write_bytes(buf.getvalue())
    verified = _run_verifier(path)
    assert verified.returncode == 1
    assert f"seq={row['seq']}" in verified.stderr


def test_verifier_script_does_not_import_backend() -> None:
    source = _VERIFIER.read_text(encoding="utf-8")
    assert "import backend" not in source
    assert "from backend" not in source
