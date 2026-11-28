"""Headless run of the 7-minute demo stand. No LLM keys, no real side effects."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from backend.governance import ApprovalQueue, HIGH_RISK_TOOLS

_ROOT = Path(__file__).resolve().parents[2]


def _demo():
    spec = importlib.util.spec_from_file_location("hermes_demo_stand", _ROOT / "scripts" / "demo.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_demo_flow_headless(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    demo = _demo()
    assert "execute_command" in HIGH_RISK_TOOLS
    assert "execute_code" in HIGH_RISK_TOOLS
    # Pilot default is fail-safe false. The stand must not depend on it.
    monkeypatch.setenv("CODE_AGENTS_ENABLED", "false")

    result = demo.run_demo_flow(export_dir=tmp_path, log=lambda *_a, **_k: None)

    assert result.reject_retry_status == "REJECTED"
    assert ApprovalQueue.get_status(result.reject_request_id) == "REJECTED"
    assert result.command_calls == 0

    assert result.approve_status_after_resolve == "APPROVED"
    assert ApprovalQueue.get_status(result.approve_request_id) == "CONSUMED"
    assert result.sandbox_posts == 1

    assert result.replay_status == "PENDING_APPROVAL"
    assert result.replay_request_id != result.approve_request_id
    assert ApprovalQueue.get_status(result.replay_request_id) == "PENDING"

    assert result.kill_switch_status == "DISABLED"
    assert result.kill_switch_sandbox_posts == 1

    events = [event for _seq, event, _actor in result.events]
    assert events.count("REQUESTED") >= 3
    assert "REJECTED" in events
    assert "APPROVED" in events
    assert "CONSUMED" in events

    assert result.verify_ok is True
    assert result.verify_checked == len(result.events)
    assert len(result.head_hash) == 64
    assert result.offline_ok.startswith("ok checked=")
    assert result.head_hash in result.offline_ok
    assert "entry_hash mismatch" in result.offline_tamper
    assert result.export_path is not None and result.export_path.is_file()
    assert result.tamper_path is not None and result.tamper_path.is_file()
    assert len(result.bundle_hash_reject) == 64
    assert result.bundle_hash_reject != result.bundle_hash_approve


def test_demo_cli_headless(tmp_path: Path) -> None:
    db = tmp_path / "hermes-demo.db"
    export_dir = tmp_path / "export"
    export_dir.mkdir()
    env = os.environ.copy()
    env["DATABASE_URL"] = ""
    env["HERMES_DEMO_DB"] = str(db)
    env["HERMES_DEMO_EXPORT"] = str(export_dir)
    env["PYTHONPATH"] = str(_ROOT)
    env["CODE_AGENTS_ENABLED"] = "false"
    proc = subprocess.run(
        [sys.executable, str(_ROOT / "scripts" / "demo.py")],
        cwd=str(_ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "[demo] DEMO_OK" in proc.stdout
    assert "SCRIPTED AGENT" in proc.stdout
    assert "exports.partner.example/v1/customers" in proc.stdout
    assert "rm -rf" not in proc.stdout
    assert "status=REJECTED" in proc.stdout
    assert "status=CONSUMED" in proc.stdout
    assert "entry_hash mismatch" in proc.stdout
    assert "R1-2 gate_tool stopped execute_code" in proc.stdout
    assert "CODE_AGENTS_ENABLED=true (explicit, approval path)" in proc.stdout
    assert "CODE_AGENTS_ENABLED=true (explicit, consume path)" in proc.stdout
    assert "CODE_AGENTS_ENABLED=false (explicit, kill switch)" in proc.stdout
    assert "status=DISABLED" in proc.stdout


def test_makefile_has_demo_targets() -> None:
    text = (_ROOT / "Makefile").read_text(encoding="utf-8")
    assert "demo:" in text
    assert "demo-reset:" in text
    assert "evidence:" in text
    assert "evidence-rebuild:" in text
    assert "--force-rebuild" in text
    assert ".PHONY: demo demo-reset evidence evidence-rebuild evidence-repack" in text


def test_demo_offline_verify_goes_through_wrapper() -> None:
    demo = (_ROOT / "scripts" / "demo.py").read_text(encoding="utf-8")
    assert "demo_verify.py" in demo
    assert "verify_decision_log.py" not in demo
    wrapper = (_ROOT / "scripts" / "demo_verify.py").read_text(encoding="utf-8")
    assert "HERMES_DEMO_VERIFIER" in wrapper
    assert "verify_decision_log.py" in wrapper


def test_demo_media_files_exist() -> None:
    media = _ROOT / "docs" / "demo" / "media"
    names = (
        "make-demo.cast",
        "make-demo.gif",
        "make-demo.svg",
        "ui-pending-execute-code.png",
        "ui-approved-rejected.png",
        "kill-switch-disabled.png",
        "verify-ok-tamper-fail.png",
    )
    for name in names:
        path = media / name
        assert path.is_file(), name
        assert path.stat().st_size > 100, name
    gif = (media / "make-demo.gif").read_bytes()
    assert len(gif) < 3 * 1024 * 1024
    assert gif[:6] in (b"GIF87a", b"GIF89a")
    width = int.from_bytes(gif[6:8], "little")
    height = int.from_bytes(gif[8:10], "little")
    frames = gif.count(b"\x2c")
    assert width >= 600 and height >= 200, (width, height)
    assert frames >= 10, frames


def test_demo_media_has_no_vm_paths() -> None:
    media = _ROOT / "docs" / "demo" / "media"
    banned = ("/agent/repos", "/home/ubuntu", "cursor.com/agents")
    for path in media.iterdir():
        if path.suffix.lower() in {".png", ".gif"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in banned:
            assert needle not in text, f"{path.name} contains {needle}"


def _evidence():
    spec = importlib.util.spec_from_file_location(
        "hermes_demo_evidence", _ROOT / "scripts" / "demo_evidence.py"
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


SAMPLE_NAME = "hermes-evidence-sample.zip"


def _assert_evidence_layout(out: Path) -> None:
    import hashlib
    import json
    import zipfile

    readme = (out / "README.md").read_text(encoding="utf-8")
    summary = (out / "SUMMARY.md").read_text(encoding="utf-8")
    for doc in (readme, summary):
        assert "not legal advice" in doc.lower()
        assert "does not make you compliant" in doc.lower()
    limits = (out / "limits" / "known-limits.md").read_text(encoding="utf-8")
    assert limits.count("\n") >= 10
    for needle in (
        "RBAC",
        "signatures",
        "SOC 2",
        "gateway",
        "off by default",
        "scripted agent",
        "mocked",
    ):
        assert needle in readme, needle
        assert needle.lower() in limits.lower() or needle in limits or needle in readme
    assert "recorded and not enforced" in readme
    assert "off-host" in readme
    pin = (out / "pinned-head-hash.txt").read_text(encoding="utf-8").strip()
    assert len(pin) == 64 and all(ch in "0123456789abcdef" for ch in pin)
    ok = (out / "verifier-ok.txt").read_text(encoding="utf-8")
    fail = (out / "negative-control-expected-output.txt").read_text(encoding="utf-8")
    assert ok.startswith("ok checked=")
    assert "FAIL seq=1 entry_hash mismatch" in fail
    assert "exit 1" in fail
    assert "reason of seq 1" in fail
    cfg = json.loads((out / "config" / "config-snapshot.json").read_text(encoding="utf-8"))
    assert cfg["CODE_AGENTS_ENABLED"]["pilot_default"] is False
    read_from = cfg["CODE_AGENTS_ENABLED"]["read_from"]
    assert read_from[".env.example"]["value"] == "false"
    assert read_from["docker-compose.yml"]["value"] == "false"
    assert read_from["backend/subagents.py:code_agents_enabled"]["unset_fallback"] == "false"
    assert "approval_path" not in cfg["CODE_AGENTS_ENABLED"]
    assert "demo_pinned_for_approval_step" in cfg["CODE_AGENTS_ENABLED"]
    assert "execute_code" in cfg["high_risk_tools"]
    assert cfg["commit"]
    assert "mcp_rule" in cfg
    bundled = (out / "verifier" / "verify_decision_log.py").read_bytes()
    assert bundled == (_ROOT / "scripts" / "verify_decision_log.py").read_bytes()
    with zipfile.ZipFile(out / "decision-log.zip") as archive:
        log_rows = [
            json.loads(line)
            for line in archive.read("decisions.jsonl").decode().splitlines()
            if line.strip()
        ]
    calls = json.loads((out / "approvals" / "calls.json").read_text(encoding="utf-8"))
    assert len(calls) == len(log_rows) == 6
    events = {row["event"] for row in calls}
    assert events >= {"REQUESTED", "APPROVED", "REJECTED", "CONSUMED"}
    by_seq = {int(row["seq"]): row for row in log_rows}
    for row in calls:
        src = by_seq[int(row["seq"])]
        assert int(row["request_id"]) == int(src["request_id"])
        assert row["event"] == src["event"]
        assert row["actor_subject"] == src["actor_subject"]
        assert row["actor_roles"] == src["actor_roles"]
        assert row["auth_method"] == src["auth_method"]
        assert row["occurred_at"] == src["occurred_at"]
        assert row["synthetic"] is True
        assert row["role_status"] == "recorded, not verified"
        assert "UTC" in (out / "approvals" / "calls.md").read_text(encoding="utf-8")
    manifest = json.loads((out / "MANIFEST.json").read_text(encoding="utf-8"))
    sample = out / "hermes-evidence-sample.zip"
    with zipfile.ZipFile(sample) as archive:
        names = set(archive.namelist())
    assert "SPEC.md" not in names
    assert "hermes-evidence-sample.zip" not in names
    assert "verifier/verify_decision_log.py" in names
    for rel, meta in manifest["files"].items():
        path = out / rel
        assert path.is_file(), rel
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == meta["sha256"], rel
        assert path.stat().st_size == meta["size"]
        assert rel in names
    for name in names:
        if name != "MANIFEST.json":
            assert name in manifest["files"], name
    blob = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in out.rglob("*")
        if path.is_file()
        and path.suffix in {".md", ".json", ".csv", ".txt", ".py"}
        and path.name != "SPEC.md"
        and path.name != SAMPLE_NAME
        and path.relative_to(out).parts[0] != "src"
    )
    for banned in ("ed25519", "audit-log"):
        assert banned not in blob.lower(), banned
    assert "synthetic" in readme.lower()
    verifier = out / "verifier" / "verify_decision_log.py"
    proc_ok = subprocess.run(
        [sys.executable, str(verifier), str(out / "decision-log.zip"), "--pin", pin],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(out),
    )
    assert proc_ok.returncode == 0, proc_ok.stderr + proc_ok.stdout
    proc_fail = subprocess.run(
        [sys.executable, str(verifier), str(out / "decision-log.tampered.zip")],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(out),
    )
    assert proc_fail.returncode == 1
    assert "entry_hash mismatch" in (proc_fail.stderr or proc_fail.stdout)


def test_evidence_pack_from_demo_export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    demo = _demo()
    monkeypatch.setenv("CODE_AGENTS_ENABLED", "false")
    demo.run_demo_flow(export_dir=tmp_path, log=lambda *_a, **_k: None)
    out = tmp_path / "evidence"
    sample = _evidence().assemble(export_dir=tmp_path, out_dir=out)
    assert sample.is_file()
    _assert_evidence_layout(out)


PMM_G6 = {
    "README.md": "e6a72871aeb786ac5e045fb3545575d9469dbcf1dbb6dde8c084838105fb839d",
    "SUMMARY.md": "cadbbaf70a38ffe91ce2847d2cdbfba9671d5eae3ab9db3ac257d06940c65333",
    "SUMMARY.pdf": "93825d243ee8f1a35fdc9f9e6eb9b52036bea668b28284ed2b1d386f3932781e",
}


def test_committed_evidence_sample() -> None:
    folder = _ROOT / "docs" / "demo" / "evidence"
    assert (folder / "hermes-evidence-sample.zip").is_file()
    assert (folder / "SPEC.md").is_file()
    assert (folder / "SUMMARY.pdf").is_file()
    for name, digest in PMM_G6.items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest, name
    _assert_evidence_layout(folder)


def test_assemble_keeps_pmm_files_and_logs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    demo = _demo()
    monkeypatch.setenv("CODE_AGENTS_ENABLED", "false")
    demo.run_demo_flow(export_dir=tmp_path, log=lambda *_a, **_k: None)
    out = tmp_path / "evidence"
    _evidence().assemble(export_dir=tmp_path, out_dir=out)
    log_sha = hashlib.sha256((out / "decision-log.zip").read_bytes()).hexdigest()
    tamp_sha = hashlib.sha256((out / "decision-log.tampered.zip").read_bytes()).hexdigest()
    readme = (out / "README.md").read_bytes() + b"\n# PMM-KEEP\n"
    summary = (out / "SUMMARY.md").read_bytes()
    pdf = b"%PDF-1.4 PMM-KEEP\n"
    (out / "README.md").write_bytes(readme)
    (out / "SUMMARY.pdf").write_bytes(pdf)
    _evidence().assemble(export_dir=tmp_path, out_dir=out)
    assert hashlib.sha256((out / "decision-log.zip").read_bytes()).hexdigest() == log_sha
    assert hashlib.sha256((out / "decision-log.tampered.zip").read_bytes()).hexdigest() == tamp_sha
    assert (out / "README.md").read_bytes() == readme
    assert (out / "SUMMARY.md").read_bytes() == summary
    assert (out / "SUMMARY.pdf").read_bytes() == pdf


def test_repack_rebuilds_manifest_and_zip_only(tmp_path: Path) -> None:
    src = _ROOT / "docs" / "demo" / "evidence"
    dest = tmp_path / "evidence"
    shutil.copytree(src, dest)
    log_sha = hashlib.sha256((dest / "decision-log.zip").read_bytes()).hexdigest()
    tamp_sha = hashlib.sha256((dest / "decision-log.tampered.zip").read_bytes()).hexdigest()
    pmm = {name: (dest / name).read_bytes() for name in PMM_G6}
    sample = _evidence().repack(dest)
    assert hashlib.sha256((dest / "decision-log.zip").read_bytes()).hexdigest() == log_sha
    assert hashlib.sha256((dest / "decision-log.tampered.zip").read_bytes()).hexdigest() == tamp_sha
    for name, data in pmm.items():
        assert (dest / name).read_bytes() == data
    manifest = json.loads((dest / "MANIFEST.json").read_text(encoding="utf-8"))
    assert manifest["files"]["SUMMARY.pdf"]["sha256"] == PMM_G6["SUMMARY.pdf"]
    with zipfile.ZipFile(sample) as archive:
        names = set(archive.namelist())
    assert "SUMMARY.pdf" in names
    assert "SPEC.md" not in names
    assert "src/summary.css" not in names
    assert "hermes-evidence-sample.zip" not in names


def test_verify_committed_pack_ok() -> None:
    _evidence().verify_committed_pack(_ROOT / "docs" / "demo" / "evidence")


def test_verify_committed_pack_reports_drift(tmp_path: Path) -> None:
    dest = tmp_path / "evidence"
    shutil.copytree(_ROOT / "docs" / "demo" / "evidence", dest)
    (dest / "README.md").write_bytes((dest / "README.md").read_bytes() + b"\n# drift\n")
    with pytest.raises(SystemExit, match="drift") as caught:
        _evidence().verify_committed_pack(dest)
    assert "README.md" in str(caught.value)


def test_evidence_default_does_not_rewrite_committed_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "evidence"
    shutil.copytree(_ROOT / "docs" / "demo" / "evidence", dest)
    before = {
        path.relative_to(dest).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in dest.rglob("*")
        if path.is_file()
    }
    mod = _evidence()
    monkeypatch.setattr(mod, "OUT_DEFAULT", dest)
    assert mod.main([]) == 0
    after = {
        path.relative_to(dest).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in dest.rglob("*")
        if path.is_file()
    }
    assert before == after


def test_demo_guide_drops_false_security_claims() -> None:
    guide = (_ROOT / "docs" / "demo" / "DEMO.md").read_text(encoding="utf-8")
    assert "make demo" in guide
    assert "scripted" in guide.lower()
    assert "R1-2" in guide
    assert "CODE_AGENTS_ENABLED=false" in guide
    assert "CODE_AGENTS_ENABLED=true" in guide
    assert "./media/" in guide
    for banned in ("chain intact", "encrypted", "signed manifest", "rm -rf"):
        assert banned not in guide, banned
