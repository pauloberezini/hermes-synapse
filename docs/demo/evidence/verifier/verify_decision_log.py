#!/usr/bin/env python3
"""Check a decision-log zip. Standard library only.

Usage: python3 scripts/verify_decision_log.py export.zip [--pin <entry_hash>]
Exit 0 when every link and evidence hash matches. Exit 1 on the first broken seq.
``--pin`` also requires that entry_hash to appear in the chain.
"""

from __future__ import annotations

import hashlib
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

# Same body as decision_log._HASH_FIELDS. seq and entry_hash stay outside the digest.
_HASH_FIELDS = (
    "tenant_id",
    "request_id",
    "event",
    "actor_subject",
    "actor_roles",
    "auth_method",
    "action_name",
    "payload_hash",
    "bundle_hash",
    "reason",
    "occurred_at",
    "prev_hash",
)


def canonical_json(obj: Any) -> str:
    """Stable JSON: sorted keys, no extra whitespace."""
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_hex(data: str) -> str:
    """SHA-256 hex digest of a UTF-8 string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def entry_hash(row: dict[str, Any]) -> str:
    """Recompute the decision digest from the exported columns."""
    body = {key: row[key] for key in _HASH_FIELDS}
    return sha256_hex(canonical_json(body))


def bundle_hash(bundle: dict[str, Any]) -> str:
    """Recompute the evidence digest. Excerpts and links are not hashed."""
    plan = bundle.get("plan")
    if plan is not None:
        plan = {
            "agent": plan["agent"],
            "instructions": plan["instructions"],
            "step_index": plan["step_index"],
            "step_count": plan["step_count"],
        }
    view = {
        "schema_ver": bundle["schema_ver"],
        "agent_id": bundle["agent_id"],
        "action_name": bundle["action_name"],
        "inputs": bundle.get("inputs") or {},
        "plan": plan,
        "upstream": [
            {
                "kind": item["kind"],
                "name": item["name"],
                "sha256": item["sha256"],
                "truncated": item["truncated"],
                "reason": item.get("reason"),
            }
            for item in bundle.get("upstream") or []
        ],
        "flags": sorted(set(bundle.get("flags") or [])),
    }
    return sha256_hex(canonical_json(view))


def main(argv: list[str]) -> int:
    """Verify a zip and print the first broken seq on failure.

    Args:
        argv: ``sys.argv``. Optional ``--pin <entry_hash>`` after the zip path.

    Returns:
        0 when the archive matches, 1 otherwise.
    """
    parsed = _parse(argv)
    if parsed is None:
        print(
            "usage: python3 verify_decision_log.py export.zip [--pin <entry_hash>]",
            file=sys.stderr,
        )
        return 1
    path, pin = parsed
    try:
        return _verify(path, pin)
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
        print(f"FAIL seq= {exc}", file=sys.stderr)
        return 1


def _parse(argv: list[str]) -> tuple[Path, str | None] | None:
    """Return the zip path and optional pin, or None when the usage is wrong."""
    args = argv[1:]
    pin: str | None = None
    if "--pin" in args:
        index = args.index("--pin")
        if index + 1 >= len(args) or args[index + 1].startswith("-"):
            return None
        pin = args[index + 1]
        del args[index : index + 2]
    if len(args) != 1:
        return None
    return Path(args[0]), pin


def _verify(path: Path, pin: str | None = None) -> int:
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        raw = archive.read("decisions.jsonl").decode()
        lines = [line for line in raw.splitlines() if line.strip()]
        rows = [json.loads(line) for line in lines]
        if manifest.get("count") != len(rows):
            seq = rows[0]["seq"] if rows else ""
            print(f"FAIL seq={seq} count mismatch", file=sys.stderr)
            return 1
        previous = ""
        for index, row in enumerate(rows):
            seq = row["seq"]
            if row["entry_hash"] != entry_hash(row):
                print(f"FAIL seq={seq} entry_hash mismatch", file=sys.stderr)
                return 1
            if index and row["prev_hash"] != previous:
                print(f"FAIL seq={seq} prev_hash mismatch", file=sys.stderr)
                return 1
            digest = row.get("bundle_hash")
            if digest:
                name = f"evidence/{row['request_id']}.json"
                if name not in archive.namelist():
                    print(f"FAIL seq={seq} evidence missing", file=sys.stderr)
                    return 1
                if bundle_hash(json.loads(archive.read(name))) != digest:
                    print(f"FAIL seq={seq} bundle_hash mismatch", file=sys.stderr)
                    return 1
            previous = row["entry_hash"]
        if rows:
            if manifest.get("head_hash") != rows[-1]["entry_hash"]:
                print(f"FAIL seq={rows[-1]['seq']} head_hash mismatch", file=sys.stderr)
                return 1
            if manifest.get("first_seq") != rows[0]["seq"] or manifest.get("last_seq") != rows[-1]["seq"]:
                print(f"FAIL seq={rows[0]['seq']} seq span mismatch", file=sys.stderr)
                return 1
        elif manifest.get("head_hash") not in ("", None):
            print("FAIL seq= head_hash mismatch", file=sys.stderr)
            return 1
        if pin is not None and not any(row.get("entry_hash") == pin for row in rows):
            print("FAIL seq= pinned entry missing", file=sys.stderr)
            return 1
    head = rows[-1]["entry_hash"] if rows else ""
    print(f"ok checked={len(rows)} head={head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
