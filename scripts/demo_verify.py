#!/usr/bin/env python3
"""Demo-stand offline verifier.

Does not own the hash chain. Forwards to the current checker so this stand can
switch later (HERMES_DEMO_VERIFIER) without editing gate_tool or decision_log.

Today: scripts/verify_decision_log.py
Same argv: <zip> [--pin <entry_hash>]
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT = _ROOT / "scripts" / "verify_decision_log.py"


def verifier_path() -> Path:
    """Checker this stand calls. Override with HERMES_DEMO_VERIFIER."""
    raw = os.environ.get("HERMES_DEMO_VERIFIER", "").strip()
    return Path(raw) if raw else _DEFAULT


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    return subprocess.call([sys.executable, str(verifier_path()), *args])


if __name__ == "__main__":
    raise SystemExit(main())
