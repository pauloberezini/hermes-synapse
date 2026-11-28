#!/usr/bin/env python3
"""Claude Code PreToolUse entrypoint. Fail-closed if Hermes cannot be imported."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _deny(reason: str) -> int:
    sys.stdout.write(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }) + "\n")
    return 0


try:
    from backend.gateway.hook import main
except Exception as exc:  # pragma: no cover - import path
    raise SystemExit(_deny(f"hook: cannot import Hermes backend (fail-closed): {exc}"))

if __name__ == "__main__":
    raise SystemExit(main())
