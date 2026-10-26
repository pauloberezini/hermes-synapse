"""OSS export leak gate. Sample tokens are concatenated so this file stays clean."""

from __future__ import annotations

from pathlib import Path

import shutil
import pytest
from backend.oss_export import find_leaks, load_rules, scan

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "scripts" / "export_oss.sh"


def _token(kind: str) -> str:
    """Build one leak spelling without writing it as a single literal."""
    parts = {
        "import": ("backend", ".bcm"),
        "from": ("from", " bcm"),
        "env": ("BCM_", "MODEL"),
        "broker_env": ("CTRADER_", "TOKEN"),
        "broker": ("Pepper", "stone"),
    }
    left, right = parts[kind]
    return left + right


@pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available in environment")
def test_checkout_has_no_public_leak() -> None:
    assert find_leaks(ROOT) == []


@pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available in environment")
def test_main_accepts_clean_checkout() -> None:
    from backend.oss_export import main

    assert main(["--root", str(ROOT)]) == 0


@pytest.mark.parametrize(
    "kind",
    ["import", "from", "env", "broker_env", "broker"],
)
def test_each_leak_token_is_reported(tmp_path: Path, kind: str) -> None:
    rel = "docs/specs/note.md"
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text("see " + _token(kind), encoding="utf-8")
    assert scan(tmp_path, [rel], load_rules(RULES)) == [rel]


def test_private_spec_prefix_is_ignored(tmp_path: Path) -> None:
    rules = load_rules(RULES)
    private = "docs/specs/bcm-note.md"
    public = "docs/specs/note.md"
    for rel in (private, public):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(_token("import"), encoding="utf-8")
    assert scan(tmp_path, [private, public], rules) == [public]


def test_slash_path_is_not_a_leak(tmp_path: Path) -> None:
    rel = "docs/specs/note.md"
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text("edit backend/bcm/plugin.py\n", encoding="utf-8")
    assert scan(tmp_path, [rel], load_rules(RULES)) == []


def test_rules_file_is_skipped(tmp_path: Path) -> None:
    rel = "scripts/export_oss.sh"
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    path.write_text(_token("import"), encoding="utf-8")
    assert scan(tmp_path, [rel], load_rules(RULES)) == []


def test_nul_file_is_skipped(tmp_path: Path) -> None:
    rel = "docs/specs/note.md"
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    path.write_bytes(b"ok\0" + _token("import").encode())
    assert scan(tmp_path, [rel], load_rules(RULES)) == []


def test_missing_rule_lines_raise(tmp_path: Path) -> None:
    script = tmp_path / "export_oss.sh"
    script.write_text("echo hi\n", encoding="utf-8")
    with pytest.raises(ValueError, match="export rules missing"):
        load_rules(script)


def test_main_prints_hits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from backend.oss_export import main

    monkeypatch.setattr(
        "backend.oss_export.find_leaks", lambda root: ["docs/specs/note.md"]
    )
    assert main(["--root", str(tmp_path)]) == 1
    err = capsys.readouterr().err
    assert err.startswith("LEAK: private references found in export:")
    assert "docs/specs/note.md" in err
