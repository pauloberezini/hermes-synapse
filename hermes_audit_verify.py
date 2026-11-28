#!/usr/bin/env python3
"""Offline verifier for signed Hermes Synapse audit bundles.

Runnable without the server or a database:

    python -m hermes_audit_verify bundle.json
    python -m hermes_audit_verify bundle.json --pubkey-fingerprint <hex>

Exit 0 on a valid chain whose last checkpoint covers the tail.
Exit 1 on a verification failure.
Exit 2 on usage, I/O, or missing-dependency errors.

Needs ``cryptography`` (Ed25519). Hash-chain checks use the stdlib only.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BUNDLE_VERSION = 1
GENESIS = "0" * 64

# Same hashed body as the decision log. seq and entry_hash stay outside the digest.
HASH_FIELDS = (
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


def sha256_hex(data: str | bytes) -> str:
    """SHA-256 hex digest of bytes, or of a UTF-8 string."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def fingerprint_hex(raw_pubkey: bytes) -> str:
    """SHA-256 of the raw 32-byte Ed25519 public key, hex."""
    return sha256_hex(raw_pubkey)


def public_key_b64(raw_pubkey: bytes) -> str:
    """Standard base64 of the raw 32-byte Ed25519 public key."""
    return base64.b64encode(raw_pubkey).decode("ascii")


def decode_public_key_b64(value: str) -> bytes:
    """Decode a bundle public key. Rejects anything other than 32 raw bytes."""
    raw = base64.b64decode(value, validate=True)
    if len(raw) != 32:
        raise ValueError("public_key must be 32 raw Ed25519 bytes")
    return raw


def entry_hash(row: dict[str, Any]) -> str:
    """Recompute the decision digest from the exported columns."""
    body = {key: row[key] for key in HASH_FIELDS}
    return sha256_hex(canonical_json(body))


def checkpoint_payload(
    seq: int,
    head_hash: str,
    timestamp: str,
    installation_id: str,
) -> bytes:
    """Canonical bytes signed by the installation key."""
    body = {
        "head_hash": head_hash,
        "installation_id": installation_id,
        "seq": int(seq),
        "timestamp": timestamp,
    }
    return canonical_json(body).encode("utf-8")


@dataclass(frozen=True)
class VerifyReport:
    """Outcome of an offline signed-bundle check."""

    ok: bool
    checked: int = 0
    unsigned_tail: int = 0
    head_hash: str = ""
    fingerprint: str = ""
    error: str = ""
    first_bad_seq: int | None = None


def load_bundle(path: Path) -> dict[str, Any]:
    """Load a JSON object or JSONL typed-line bundle."""
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        raise ValueError("empty bundle")
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError:
        obj = None
    if isinstance(obj, dict) and "records" in obj:
        return obj
    return _load_jsonl(stripped)


def _load_jsonl(text: str) -> dict[str, Any]:
    header: dict[str, Any] = {}
    records: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        obj = json.loads(line)
        if not isinstance(obj, dict):
            raise ValueError("JSONL line is not an object")
        kind = obj.get("type")
        if kind == "checkpoint" or (kind is None and "signature" in obj and "head_hash" in obj):
            checkpoints.append(obj)
        elif kind == "record" or (kind is None and "entry_hash" in obj):
            records.append(obj)
        else:
            header.update(obj)
    if checkpoints and "checkpoints" not in header:
        header["checkpoints"] = checkpoints
    header["records"] = records
    return header


def verify_bundle(
    bundle: dict[str, Any],
    expected_fingerprint: str | None = None,
) -> VerifyReport:
    """Verify hash chain, checkpoint signatures, tail coverage, optional pin."""
    version = bundle.get("version")
    if version != BUNDLE_VERSION:
        return VerifyReport(False, error=f"unsupported version {version!r}")

    try:
        raw_pub = decode_public_key_b64(str(bundle.get("public_key") or ""))
    except (ValueError, TypeError) as exc:
        return VerifyReport(False, error=f"public_key: {exc}")

    fingerprint = fingerprint_hex(raw_pub)
    claimed = str(bundle.get("pubkey_fingerprint") or "")
    if claimed and claimed != fingerprint:
        return VerifyReport(False, fingerprint=fingerprint, error="pubkey_fingerprint mismatch")
    if expected_fingerprint and expected_fingerprint.lower() != fingerprint.lower():
        return VerifyReport(False, fingerprint=fingerprint, error="fingerprint mismatch")

    records = list(bundle.get("records") or [])
    checkpoints = list(bundle.get("checkpoints") or [])

    chain = _verify_chain(records)
    if not chain.ok:
        return VerifyReport(
            False,
            checked=chain.checked,
            head_hash=chain.head_hash,
            fingerprint=fingerprint,
            error=chain.error,
            first_bad_seq=chain.first_bad_seq,
        )

    by_seq = {int(row["seq"]): row for row in records}
    last_seq = int(records[-1]["seq"]) if records else 0
    last_checkpoint_seq = 0

    try:
        public_key = _ed25519_public(raw_pub)
    except Exception as exc:
        return VerifyReport(False, fingerprint=fingerprint, error=f"public_key: {exc}")

    for checkpoint in checkpoints:
        report = _verify_checkpoint(checkpoint, by_seq, public_key, fingerprint)
        if not report.ok:
            return report
        last_checkpoint_seq = max(last_checkpoint_seq, int(checkpoint["seq"]))

    unsigned_tail = 0
    if records:
        unsigned_tail = last_seq - last_checkpoint_seq
        if last_checkpoint_seq == 0:
            return VerifyReport(
                False,
                checked=len(records),
                unsigned_tail=len(records),
                head_hash=chain.head_hash,
                fingerprint=fingerprint,
                error="truncated tail unsigned=%s" % len(records),
            )
        if last_checkpoint_seq not in by_seq:
            return VerifyReport(
                False,
                checked=len(records),
                unsigned_tail=max(unsigned_tail, 0),
                head_hash=chain.head_hash,
                fingerprint=fingerprint,
                first_bad_seq=last_checkpoint_seq,
                error="truncated tail checkpoint seq=%s missing" % last_checkpoint_seq,
            )
        if unsigned_tail > 0:
            return VerifyReport(
                False,
                checked=len(records),
                unsigned_tail=unsigned_tail,
                head_hash=chain.head_hash,
                fingerprint=fingerprint,
                error="truncated tail unsigned=%s" % unsigned_tail,
            )
        if unsigned_tail < 0:
            return VerifyReport(
                False,
                checked=len(records),
                unsigned_tail=unsigned_tail,
                head_hash=chain.head_hash,
                fingerprint=fingerprint,
                first_bad_seq=last_checkpoint_seq,
                error="truncated tail checkpoint seq=%s past head" % last_checkpoint_seq,
            )

    return VerifyReport(
        True,
        checked=len(records),
        unsigned_tail=0,
        head_hash=chain.head_hash,
        fingerprint=fingerprint,
    )


def _verify_chain(records: list[dict[str, Any]]) -> VerifyReport:
    previous = ""
    for index, row in enumerate(records):
        try:
            seq = int(row["seq"])
        except (KeyError, TypeError, ValueError):
            return VerifyReport(False, checked=index, error="record missing seq")
        try:
            digest = entry_hash(row)
        except KeyError as exc:
            return VerifyReport(False, checked=index, first_bad_seq=seq, error=f"entry_hash field {exc}")
        if row.get("entry_hash") != digest:
            return VerifyReport(False, checked=index, first_bad_seq=seq, error="entry_hash mismatch")
        if index and row.get("prev_hash") != previous:
            return VerifyReport(False, checked=index, first_bad_seq=seq, error="prev_hash mismatch")
        previous = row["entry_hash"]
    return VerifyReport(True, checked=len(records), head_hash=previous)


def _verify_checkpoint(
    checkpoint: dict[str, Any],
    by_seq: dict[int, dict[str, Any]],
    public_key: Any,
    fingerprint: str,
) -> VerifyReport:
    try:
        seq = int(checkpoint["seq"])
        head_hash = str(checkpoint["head_hash"])
        timestamp = str(checkpoint["timestamp"])
        installation_id = str(checkpoint["installation_id"])
        signature_b64 = str(checkpoint["signature"])
    except (KeyError, TypeError, ValueError) as exc:
        return VerifyReport(False, fingerprint=fingerprint, error=f"checkpoint fields: {exc}")

    row = by_seq.get(seq)
    if row is None:
        return VerifyReport(
            False,
            fingerprint=fingerprint,
            first_bad_seq=seq,
            error="truncated tail checkpoint seq=%s missing" % seq,
        )
    if row.get("entry_hash") != head_hash:
        return VerifyReport(
            False,
            fingerprint=fingerprint,
            first_bad_seq=seq,
            error="checkpoint head_hash mismatch",
        )

    try:
        signature = base64.b64decode(signature_b64, validate=True)
        public_key.verify(signature, checkpoint_payload(seq, head_hash, timestamp, installation_id))
    except Exception:
        return VerifyReport(
            False,
            fingerprint=fingerprint,
            first_bad_seq=seq,
            error="checkpoint signature invalid",
        )
    return VerifyReport(True, fingerprint=fingerprint)


def _ed25519_public(raw_pubkey: bytes) -> Any:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    return Ed25519PublicKey.from_public_bytes(raw_pubkey)


def main(argv: list[str] | None = None) -> int:
    """CLI entry. ``argv`` is ``sys.argv`` (including ``python -m`` argv[0])."""
    parser = argparse.ArgumentParser(
        prog="hermes_audit_verify",
        description="Verify a signed Hermes Synapse audit bundle offline.",
    )
    parser.add_argument("bundle", help="JSON or JSONL bundle path")
    parser.add_argument(
        "--pubkey-fingerprint",
        default=None,
        metavar="HEX",
        help="expected SHA-256 of the raw Ed25519 public key",
    )
    args = parser.parse_args(argv[1:] if argv is not None else None)
    path = Path(args.bundle)
    try:
        bundle = load_bundle(path)
        report = verify_bundle(bundle, expected_fingerprint=args.pubkey_fingerprint)
    except FileNotFoundError:
        print(f"FAIL cannot read {path}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2

    if report.ok:
        print(
            f"ok checked={report.checked} head={report.head_hash} "
            f"unsigned_tail={report.unsigned_tail} fingerprint={report.fingerprint}"
        )
        return 0
    seq = f" seq={report.first_bad_seq}" if report.first_bad_seq is not None else ""
    print(f"FAIL{seq} {report.error}", file=sys.stderr)
    if report.unsigned_tail:
        print(f"unsigned_tail={report.unsigned_tail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
