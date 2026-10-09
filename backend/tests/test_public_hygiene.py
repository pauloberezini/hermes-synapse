"""Public-surface leftovers: Sir in replies, Serper docs, desk names in core, root junk."""
import json
import re
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
SIR = re.compile(r"\bSir\b|\bSIR\b")
REPLY_FILES = (
    "backend/agent.py",
    "backend/bot.py",
    "backend/main.py",
    "backend/orchestrator.py",
    "backend/scheduler.py",
    "backend/tools.py",
    "backend/database.py",
)
ROOT_JUNK = (
    "AUDUSD_TRADE_AUDIT_2026_09_14.md",
    "agent_network.dot",
    "agent_network.png",
    "test_docker.py",
    "test_script.py",
    "scratch_test.py",
    "jarvis.db",
)


def test_docs_describe_searxng_not_serper():
    readme_path = ROOT / "README.md"
    if not readme_path.exists():
        pytest.skip("README.md not accessible in container workspace")
    readme = readme_path.read_text()
    example = (ROOT / ".env.example").read_text()
    assert "serper" not in readme.lower()
    assert "serper" not in example.lower()
    assert "SearXNG" in readme
    assert "SEARXNG_URL" in example


def test_replies_do_not_address_the_user_as_sir():
    from backend.agent import DEFAULT_SYSTEM_PROMPT

    assert not SIR.search(DEFAULT_SYSTEM_PROMPT)
    assert "serper" not in DEFAULT_SYSTEM_PROMPT.lower()
    assert "BCM" not in DEFAULT_SYSTEM_PROMPT
    hits = []
    for rel in REPLY_FILES:
        for i, line in enumerate((ROOT / rel).read_text().splitlines(), 1):
            if SIR.search(line):
                hits.append(f"{rel}:{i}:{line.strip()}")
    assert hits == []


def test_core_does_not_name_the_trading_desk():
    _broker = "Pepper" + "stone"
    desk = re.compile(rf"\bBCM\b|bcm_|ctrader_|BRENT|Remizov|hedge fund|{_broker}", re.I)
    hits = []
    for rel in (
        "backend/agent.py",
        "backend/orchestrator.py",
        "backend/main.py",
        "backend/scheduler.py",
        "backend/rag.py",
    ):
        for i, line in enumerate((ROOT / rel).read_text().splitlines(), 1):
            if desk.search(line):
                hits.append(f"{rel}:{i}:{line.strip()}")
    assert hits == []


def test_ui_copy_does_not_address_sir():
    hits = []
    for path in (ROOT / "frontend/src").rglob("*.tsx"):
        if ".test." in path.name:
            continue
        rel = path.relative_to(ROOT)
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if SIR.search(line):
                hits.append(f"{rel}:{i}:{line.strip()}")
    assert hits == []


def test_repo_root_has_no_scratch_files():
    git_files = ROOT / ".git"
    if not git_files.is_dir():
        pytest.skip("Git metadata not accessible in container workspace")
    tracked = set()
    import subprocess
    out = subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True)
    tracked = {line for line in out.splitlines() if "/" not in line}
    assert set(ROOT_JUNK).isdisjoint(tracked)
    assert not list(ROOT.glob("patch_*.py"))
    for name in ROOT_JUNK:
        assert not (ROOT / name).exists(), name


def test_changelog_matches_package_version():
    package_json = ROOT / "frontend/package.json"
    if not package_json.exists():
        pytest.skip("frontend/package.json not accessible in container workspace")
    pkg_data = json.loads(package_json.read_text())
    pkg_version = pkg_data.get("version")
    assert pkg_version, "frontend/package.json missing version field"

    changelog_path = ROOT / "CHANGELOG.md"
    if not changelog_path.exists():
        pytest.skip("CHANGELOG.md not accessible in container workspace")
    changelog = changelog_path.read_text()

    # Find release headers like "## 🚀 [v1.4.1] - 2026-10-09"
    versions = re.findall(r"^##\s*(?:[^\n\r]*?)\[?v?(\d+\.\d+\.\d+)\]?", changelog, re.MULTILINE)
    assert versions, "No version headers found in CHANGELOG.md"

    latest_changelog_version = versions[0]
    assert latest_changelog_version == pkg_version, (
        f"Latest CHANGELOG.md version ({latest_changelog_version}) does not match "
        f"frontend/package.json version ({pkg_version})"
    )
    assert pkg_version in versions, f"Version {pkg_version} not found in CHANGELOG.md headers"

