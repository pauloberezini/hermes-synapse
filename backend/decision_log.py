"""Append-only hash chain of approval decisions.

One chain per tenant. ``verify`` recomputes every link from the stored columns.
"""

from __future__ import annotations

import io
import json
import threading
import zipfile
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterator

from backend.canonical import canonical_json, sha256_hex
from backend.identity import Principal

GENESIS = "0" * 64

# Hashed body. seq and entry_hash are excluded so the digest can be checked.
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

_COLUMNS = ("seq", *_HASH_FIELDS, "entry_hash")

# ponytail: one process lock. Per-tenant locks if append throughput matters.
_chain_lock = threading.Lock()
_tx_conn: ContextVar[Any] = ContextVar("_tx_conn", default=None)


@dataclass(frozen=True)
class VerifyResult:
    """Outcome of walking one tenant chain."""

    ok: bool
    checked: int
    first_bad_seq: int | None = None
    error: str = ""
    head_hash: str = ""


def entry_hash(row: dict[str, Any]) -> str:
    """SHA-256 of the canonical decision body."""
    body = {key: row[key] for key in _HASH_FIELDS}
    return sha256_hex(canonical_json(body))


def append(
    event: str,
    *,
    request_id: int,
    actor: Principal | str,
    action_name: str,
    payload: dict[str, Any],
    bundle_hash: str | None,
    reason: str = "",
    tenant_id: str = "default",
    auth_method: str = "agent",
    actor_roles: list[str] | tuple[str, ...] | None = None,
) -> str:
    """Link a decision onto the tenant chain. Returns the new entry hash.

    Raises:
        sqlite3.IntegrityError: if a trigger rejects the write.
    """
    from backend.governance import PIIGuard

    clean_reason, _counts = PIIGuard.mask_pii(reason or "")
    if isinstance(actor, Principal):
        actor_subject = actor.subject
        roles = list(actor.roles)
        method = actor.auth_method
        if tenant_id == "default" and actor.tenant_id:
            tenant_id = actor.tenant_id
    else:
        actor_subject = str(actor)
        roles = list(actor_roles or [])
        if actor_subject.startswith("agent:"):
            method = "agent"
        elif actor_subject == "system":
            method = "system"
        else:
            method = auth_method

    row: dict[str, Any] = {
        "tenant_id": tenant_id,
        "request_id": int(request_id),
        "event": event,
        "actor_subject": actor_subject,
        "actor_roles": canonical_json(roles),
        "auth_method": method,
        "action_name": action_name,
        "payload_hash": sha256_hex(canonical_json(payload or {})),
        "bundle_hash": bundle_hash,
        "reason": clean_reason,
        "occurred_at": datetime.now(UTC).isoformat(),
        "prev_hash": GENESIS,
    }
    with _chain_lock:
        active_conn = _tx_conn.get()
        if active_conn is not None:
            from backend.database import _get_backend
            return _insert(active_conn, _get_backend(), row, immediate=False)
        return _insert_locked(row)


def history(request_id: int, tenant_id: str | None = None) -> list[dict[str, Any]]:
    """Return all decision log entries for a given request_id in seq order."""
    from backend.database import _execute

    placeholders = ", ".join(_COLUMNS)
    if tenant_id is not None:
        raws = _execute(
            f"SELECT {placeholders} FROM approval_decisions WHERE request_id = ? AND tenant_id = ? ORDER BY seq ASC",
            (int(request_id), tenant_id),
        )
    else:
        raws = _execute(
            f"SELECT {placeholders} FROM approval_decisions WHERE request_id = ? ORDER BY seq ASC",
            (int(request_id),),
        )
    return [_public_row(dict(zip(_COLUMNS, raw))) for raw in raws]


def export_jsonl(
    tenant_id: str = "default",
    since: str | None = None,
    until: str | None = None,
) -> Iterator[str]:
    """Yield decision log entries as canonical JSON lines."""
    for row in _rows(tenant_id, since, until):
        yield canonical_json(_public_row(row))


def verify(tenant_id: str = "default") -> VerifyResult:
    """Recompute the chain, then each stored evidence bundle hash.

    A decision row with a ``bundle_hash`` and no evidence row fails the walk
    (``evidence missing``). A row with no ``bundle_hash`` is not an evidence
    claim and stays valid. When the evidence row is present, its hash must
    match. The first broken seq fails the walk.

    Args:
        tenant_id: Chain to walk.

    Returns:
        The walk outcome. ``error`` is ``evidence missing`` when the row was
        deleted, or ``bundle_hash mismatch`` when evidence was edited.
    """
    from backend.database import _execute

    placeholders = ", ".join(_COLUMNS)
    rows = _execute(
        f"SELECT {placeholders} FROM approval_decisions WHERE tenant_id = ? ORDER BY seq",
        (tenant_id,),
    )
    parsed: list[dict[str, Any]] = []
    prev = GENESIS
    for raw in rows:
        row = dict(zip(_COLUMNS, raw))
        seq = int(row["seq"])
        if row["prev_hash"] != prev:
            return VerifyResult(False, 0, seq, "prev_hash mismatch", "")
        digest = entry_hash(row)
        if row["entry_hash"] != digest:
            return VerifyResult(False, 0, seq, "entry_hash mismatch", "")
        parsed.append(row)
        prev = digest
    evidence_bad = _evidence_mismatch(parsed)
    if evidence_bad is not None:
        return evidence_bad
    return VerifyResult(True, len(parsed), None, "", prev if parsed else "")


def _evidence_mismatch(rows: list[dict[str, Any]]) -> VerifyResult | None:
    """Return a failure when a claimed bundle is missing or no longer matches.

    Only rows that store a ``bundle_hash`` are claims. A missing evidence row
    for that claim is ``evidence missing``. An edited bundle is
    ``bundle_hash mismatch``.
    """
    from backend.evidence import EvidenceBundle, bundle_hash

    wanted = [int(row["request_id"]) for row in rows if row.get("bundle_hash")]
    stored = _load_evidence(wanted)
    seen: set[int] = set()
    for row in rows:
        digest = row.get("bundle_hash")
        if not digest:
            continue
        request_id = int(row["request_id"])
        if request_id in seen:
            continue
        seen.add(request_id)
        blob = stored.get(request_id)
        seq = int(row["seq"])
        if blob is None:
            return VerifyResult(False, 0, seq, "evidence missing", "")
        try:
            bundle = EvidenceBundle.model_validate(json.loads(blob))
        except (TypeError, ValueError):
            return VerifyResult(False, 0, seq, "bundle_hash mismatch", "")
        if bundle_hash(bundle) != digest:
            return VerifyResult(False, 0, seq, "bundle_hash mismatch", "")
    return None


_VERIFY_MD = """# Verify this archive

Python 3.11+ standard library only. No Hermes install and no network.

The checker is not in this zip. It lives in the repository at
`scripts/verify_decision_log.py`.

    python3 scripts/verify_decision_log.py hermes-decisions-<tenant>-<from>-<to>.zip
    python3 scripts/verify_decision_log.py hermes-decisions-<tenant>-<from>-<to>.zip --pin <entry_hash>

`--pin` requires that entry_hash to appear in the chain. Record the head hash
when you export. A later check with that pin fails if the tail was dropped,
even when manifest.json was rewritten to match the shorter file.

Exit 0 prints `ok checked=N head=H`.
Exit 1 prints `FAIL seq=N <reason>` to stderr. A missing pin prints `pinned entry missing`.
"""


def export_zip(
    tenant_id: str = "default",
    *,
    since: str | None = None,
    until: str | None = None,
    exported_by: str = "local-admin",
) -> tuple[bytes, str]:
    """Pack one tenant chain into the audit zip.

    Args:
        tenant_id: Chain to export.
        since: Inclusive start date, ``YYYY-MM-DD``. Omit to start at the first row.
        until: Inclusive end date, ``YYYY-MM-DD``. Omit to stop at the last row.
        exported_by: Operator recorded in ``manifest.json``.

    Returns:
        Zip bytes and the ``hermes-decisions-<tenant>-<from>-<to>.zip`` filename.
    """
    since = since or None
    until = until or None
    rows = [_public_row(row) for row in _rows(tenant_id, since, until)]
    span_from = since if since is not None else (str(rows[0]["occurred_at"])[:10] if rows else "all")
    span_to = until if until is not None else (str(rows[-1]["occurred_at"])[:10] if rows else "all")
    evidence = _load_evidence([int(row["request_id"]) for row in rows])
    manifest = {
        "tenant": tenant_id,
        "from": span_from,
        "to": span_to,
        "count": len(rows),
        "first_seq": rows[0]["seq"] if rows else None,
        "last_seq": rows[-1]["seq"] if rows else None,
        "head_hash": rows[-1]["entry_hash"] if rows else "",
        "exported_at": datetime.now(UTC).isoformat(),
        "exported_by": exported_by,
        "schema_ver": 1,
    }
    lines = [canonical_json(row) for row in rows]
    body = ("".join(f"{line}\n" for line in lines)).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("decisions.jsonl", body)
        for request_id in dict.fromkeys(int(row["request_id"]) for row in rows):
            blob = evidence.get(request_id)
            if blob is not None:
                archive.writestr(f"evidence/{request_id}.json", blob)
        archive.writestr("manifest.json", canonical_json(manifest).encode())
        archive.writestr("VERIFY.md", _VERIFY_MD)
    filename = f"hermes-decisions-{_slug(tenant_id)}-{_slug(span_from)}-{_slug(span_to)}.zip"
    return buf.getvalue(), filename


def _public_row(row: dict[str, Any]) -> dict[str, Any]:
    out = {key: row[key] for key in _COLUMNS}
    out["seq"] = int(out["seq"])
    out["request_id"] = int(out["request_id"])
    return out


def _rows(tenant_id: str, since: str | None, until: str | None) -> list[dict[str, Any]]:
    # ponytail: scan the tenant chain in process; SQL range when a tenant log gets long
    from backend.database import _execute

    placeholders = ", ".join(_COLUMNS)
    raws = _execute(
        f"SELECT {placeholders} FROM approval_decisions WHERE tenant_id = ? ORDER BY seq",
        (tenant_id,),
    )
    picked: list[dict[str, Any]] = []
    for raw in raws:
        row = dict(zip(_COLUMNS, raw))
        day = str(row["occurred_at"])[:10]
        if since is not None and day < since[:10]:
            continue
        if until is not None and day > until[:10]:
            continue
        picked.append(row)
    return picked


def _load_evidence(request_ids: list[int]) -> dict[int, str]:
    if not request_ids:
        return {}
    from backend.database import _execute

    unique = tuple(dict.fromkeys(request_ids))
    marks = ", ".join("?" for _ in unique)
    raws = _execute(
        f"SELECT request_id, bundle_json FROM approval_evidence WHERE request_id IN ({marks})",
        unique,
    )
    return {int(request_id): str(bundle_json) for request_id, bundle_json in raws}


def _slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)
    return cleaned or "all"


def _insert_locked(row: dict[str, Any]) -> str:
    from backend.database import PostgresBackend, _get_backend, _get_conn

    backend = _get_backend()
    if isinstance(backend, PostgresBackend):
        with backend.connect() as conn:
            return _insert(conn, backend, row, immediate=False)
    conn = _get_conn()
    conn.isolation_level = None
    try:
        return _insert(conn, backend, row, immediate=True)
    finally:
        conn.close()


def _insert(conn: Any, backend: Any, row: dict[str, Any], *, immediate: bool) -> str:
    cur = conn.cursor()
    manage_tx = immediate or (not getattr(conn, "in_transaction", False))
    if manage_tx:
        cur.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
    try:
        select_sql = backend.translate_placeholder(
            "SELECT entry_hash FROM approval_decisions WHERE tenant_id = ? ORDER BY seq DESC LIMIT 1"
        )
        cur.execute(select_sql, (row["tenant_id"],))
        previous = cur.fetchone()
        row["prev_hash"] = previous[0] if previous else GENESIS
        digest = entry_hash(row)
        insert_sql = backend.translate_placeholder(
            "INSERT INTO approval_decisions "
            "(tenant_id, request_id, event, actor_subject, actor_roles, auth_method, "
            "action_name, payload_hash, bundle_hash, reason, occurred_at, prev_hash, entry_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
        cur.execute(
            insert_sql,
            (
                row["tenant_id"],
                row["request_id"],
                row["event"],
                row["actor_subject"],
                row["actor_roles"],
                row["auth_method"],
                row["action_name"],
                row["payload_hash"],
                row["bundle_hash"],
                row["reason"],
                row["occurred_at"],
                row["prev_hash"],
                digest,
            ),
        )
        if manage_tx:
            cur.execute("COMMIT")
    except Exception:
        if manage_tx:
            try:
                cur.execute("ROLLBACK")
            except Exception:
                pass
        raise
    return digest
