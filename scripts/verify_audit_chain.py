#!/usr/bin/env python3
"""Check the approval decision hash chain without starting the web app.

Usage: python3 scripts/verify_audit_chain.py [tenant_id]
Exit 0 when every link matches. Exit 1 on the first broken seq.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.decision_log import verify


def main(argv: list[str]) -> int:
    tenant = argv[1] if len(argv) > 1 else "default"
    result = verify(tenant)
    if result.ok:
        print(f"ok checked={result.checked} head={result.head_hash}")
        return 0
    print(f"FAIL seq={result.first_bad_seq} {result.error}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
