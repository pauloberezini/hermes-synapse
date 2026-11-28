"""Headless run of the 7-minute demo stand. No LLM keys, no real side effects."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
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
    assert ".PHONY: demo demo-reset" in text


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
