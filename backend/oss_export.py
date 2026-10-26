"""Publish-tree scan for private-plugin tokens.

Rules are read from ``scripts/export_oss.sh`` so the shell publisher and pytest
share one pattern. This module does not repeat that pattern.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

RULES_REL = "scripts/export_oss.sh"
_PRIVATE_LINE = re.compile(r"^PRIVATE_PATHS='([^']+)'", re.MULTILINE)
_LEAK_LINE = re.compile(r"grep -rIl -E '([^']+)'")


@dataclass(frozen=True)
class ExportRules:
    """Compiled path filter and body pattern from the export script."""

    private_paths: re.Pattern[str]
    leak: re.Pattern[str]


def load_rules(script: Path) -> ExportRules:
    """Compile the private-path and leak rules stored in the export script.

    Args:
        script: Path to ``scripts/export_oss.sh``.

    Returns:
        Compiled rules. The path pattern matches a repo-relative path. The
        leak pattern matches file text.

    Raises:
        ValueError: If either rule line is missing.
        FileNotFoundError: If ``script`` does not exist.
    """
    text = script.read_text(encoding="utf-8")
    private = _PRIVATE_LINE.search(text)
    leak = _LEAK_LINE.search(text)
    if private is None or leak is None:
        raise ValueError(f"export rules missing in {script}")
    return ExportRules(
        private_paths=re.compile(private.group(1)),
        leak=re.compile(leak.group(1)),
    )


def candidate_paths(root: Path) -> list[str]:
    """List tracked and untracked files, honoring gitignore.

    Args:
        root: Git checkout to list.

    Returns:
        Repo-relative paths, git order, empty lines removed.

    Raises:
        subprocess.CalledProcessError: If git cannot list the checkout.
    """
    completed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def scan(root: Path, rels: list[str], rules: ExportRules) -> list[str]:
    """Return public files whose text matches the leak pattern.

    Args:
        root: Directory the relative paths are under.
        rels: Repo-relative paths, in the order to report.
        rules: Compiled export rules.

    Returns:
        Matching paths. The rules file and private paths are omitted. A
        missing path or a file that contains a NUL byte is omitted.
    """
    hits: list[str] = []
    for rel in rels:
        if rel == RULES_REL or rules.private_paths.search(rel):
            continue
        path = root / rel
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data:
            continue
        if rules.leak.search(data.decode("utf-8", errors="replace")):
            hits.append(rel)
    return hits


def find_leaks(root: Path) -> list[str]:
    """Scan one checkout the way the publisher scans the export tree.

    Args:
        root: Checkout that contains ``scripts/export_oss.sh``.

    Returns:
        Public files that match the leak pattern.
    """
    return scan(root, candidate_paths(root), load_rules(root / RULES_REL))


def main(argv: list[str] | None = None) -> int:
    """Exit 1 when the tree would fail the OSS publish leak gate.

    Args:
        argv: CLI args. ``None`` reads ``sys.argv``. ``--root`` defaults to cwd.

    Returns:
        ``0`` when the public tree is clean, ``1`` when it is not.
    """
    parser = argparse.ArgumentParser(description="Scan a tree for OSS export leaks.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args(argv)
    root = args.root.resolve()
    hits = find_leaks(root)
    if not hits:
        return 0
    print("LEAK: private references found in export:", file=sys.stderr)
    for hit in hits:
        print(hit, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
