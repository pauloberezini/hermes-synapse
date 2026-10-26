"""
backend/governance.py — Hermes Synapse Governance Engine (Paperclip-inspired)

Provides:
  - BudgetGuard: Enforces per-session and global token/dollar spend caps.
  - ApprovalQueue: Stores and resolves human-in-the-loop approval requests.
"""

from __future__ import annotations

import contextvars
import json
import logging
from datetime import datetime, timezone
from typing import Optional

# Session whose spend caps apply to the current agent turn (orchestrator, subagent, call_llm).
budget_session: contextvars.ContextVar[str] = contextvars.ContextVar(
    "hermes_budget_session", default="default"
)
# Tools the agent currently running is allowed to delegate. None = caller unknown.
current_agent_tools: contextvars.ContextVar[Optional[frozenset[str]]] = contextvars.ContextVar(
    "current_agent_tools", default=None
)
# Fail-closed floor when a subagent is entered with no parent capability.
CORE_READONLY_TOOLS = frozenset({
    "get_current_time_israel",
    "get_weather",
    "web_search",
})
# ponytail: flat floor so a near-full cap blocks the next call; token price if this gets noisy
LLM_CALL_ESTIMATE_USD = 0.01

HIGH_RISK_TOOLS = frozenset({
    "execute_command",
    "create_obsidian_note",
    "delete_todoist_task",
    "create_subagent",
    "update_subagent",
    "delete_subagent",
    "change_agent_skills",
    "assign_role",
    "clear_history",
    "clear_decision_logs",
    "set_log_level",
    "export_or_purge_audit",
})

logger = logging.getLogger("hermes.governance")


# ── Budget Guard ──────────────────────────────────────────────────────────────────

class BudgetExceededError(Exception):
    """Raised when a session's spend cap is hit before executing an LLM call."""

    def __init__(self, session_id: str, spent: float, cap: float):
        self.session_id = session_id
        self.spent = spent
        self.cap = cap
        super().__init__(
            f"[BudgetGuard] Session '{session_id}' has exceeded its spending cap: "
            f"${spent:.4f} spent / ${cap:.4f} cap."
        )


class BudgetGuard:
    """
    Lightweight budget enforcer that reads spend totals from the DB
    and raises BudgetExceededError before a new LLM call if the cap is hit.

    Caps are stored in ``app_settings`` as JSON strings:
      - Key ``budget_global_daily_usd``  → global daily cap across all sessions.
      - Key ``budget_global_monthly_usd``→ global monthly cap across all sessions.

    Per-session caps are stored in the ``session_metadata`` table columns:
      - ``daily_budget_usd``   (REAL, NULL = unlimited)
      - ``monthly_budget_usd`` (REAL, NULL = unlimited)
    """

    # ── Public API ────────────────────────────────────────────────────────────

    @staticmethod
    def check(session_id: str, estimated_cost_usd: float) -> None:
        """
        Call before invoking the LLM.  Raises BudgetExceededError if any cap
        (session-level or global) would be exceeded by ``estimated_cost_usd``.
        """
        from backend import database as db

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        month = datetime.now(timezone.utc).strftime("%Y-%m")

        # ── Per-session caps ───────────────────────────────────────────────
        session_caps = BudgetGuard._get_session_caps(session_id)
        if session_caps:
            daily_cap = session_caps.get("daily_budget_usd")
            monthly_cap = session_caps.get("monthly_budget_usd")

            if daily_cap is not None:
                daily_spent = BudgetGuard._session_spend(session_id, prefix=today)
                if daily_spent + estimated_cost_usd > daily_cap:
                    raise BudgetExceededError(session_id, daily_spent, daily_cap)

            if monthly_cap is not None:
                monthly_spent = BudgetGuard._session_spend(session_id, prefix=month)
                if monthly_spent + estimated_cost_usd > monthly_cap:
                    raise BudgetExceededError(session_id, monthly_spent, monthly_cap)

        # ── Global caps ────────────────────────────────────────────────────
        global_daily_cap = BudgetGuard._get_global_cap("budget_global_daily_usd")
        if global_daily_cap is not None:
            global_daily_spent = BudgetGuard._global_spend(prefix=today)
            if global_daily_spent + estimated_cost_usd > global_daily_cap:
                raise BudgetExceededError("global", global_daily_spent, global_daily_cap)

        global_monthly_cap = BudgetGuard._get_global_cap("budget_global_monthly_usd")
        if global_monthly_cap is not None:
            global_monthly_spent = BudgetGuard._global_spend(prefix=month)
            if global_monthly_spent + estimated_cost_usd > global_monthly_cap:
                raise BudgetExceededError("global", global_monthly_spent, global_monthly_cap)

    @staticmethod
    def get_spend_summary(session_id: str) -> dict:
        """Returns current spend totals and caps for a session."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        caps = BudgetGuard._get_session_caps(session_id) or {}

        return {
            "session_id": session_id,
            "daily_spent_usd": round(BudgetGuard._session_spend(session_id, prefix=today), 6),
            "monthly_spent_usd": round(BudgetGuard._session_spend(session_id, prefix=month), 6),
            "total_spent_usd": round(BudgetGuard._session_spend(session_id), 6),
            "daily_budget_usd": caps.get("daily_budget_usd"),
            "monthly_budget_usd": caps.get("monthly_budget_usd"),
            "global_daily_spent_usd": round(BudgetGuard._global_spend(prefix=today), 6),
            "global_monthly_spent_usd": round(BudgetGuard._global_spend(prefix=month), 6),
            "global_daily_budget_usd": BudgetGuard._get_global_cap("budget_global_daily_usd"),
            "global_monthly_budget_usd": BudgetGuard._get_global_cap("budget_global_monthly_usd"),
        }

    # ── Internals ─────────────────────────────────────────────────────────────

    @staticmethod
    def _session_spend(session_id: str, prefix: Optional[str] = None) -> float:
        """Sum cost_usd from messages table for a session, optionally filtered by date prefix."""
        from backend.database import _get_backend
        backend = _get_backend()
        with backend.connect() as conn:
            cursor = conn.cursor()
            if prefix:
                sql = backend.translate_placeholder(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM messages "
                    "WHERE session_id = ? AND CAST(timestamp AS TEXT) LIKE ?"
                )
                cursor.execute(sql, (session_id, f"{prefix}%"))
            else:
                sql = backend.translate_placeholder(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM messages WHERE session_id = ?"
                )
                cursor.execute(sql, (session_id,))
            result = cursor.fetchone()
            return float(result[0]) if result else 0.0

    @staticmethod
    def _global_spend(prefix: Optional[str] = None) -> float:
        """Sum cost_usd across ALL sessions, optionally filtered by date prefix."""
        from backend.database import _get_backend
        backend = _get_backend()
        with backend.connect() as conn:
            cursor = conn.cursor()
            if prefix:
                sql = backend.translate_placeholder(
                    "SELECT COALESCE(SUM(cost_usd), 0) FROM messages WHERE CAST(timestamp AS TEXT) LIKE ?"
                )
                cursor.execute(sql, (f"{prefix}%",))
            else:
                cursor.execute("SELECT COALESCE(SUM(cost_usd), 0) FROM messages")
            result = cursor.fetchone()
            return float(result[0]) if result else 0.0

    @staticmethod
    def _get_session_caps(session_id: str) -> Optional[dict]:
        """Read per-session budget caps from session_metadata."""
        from backend.database import _get_backend
        try:
            backend = _get_backend()
            with backend.connect() as conn:
                cursor = conn.cursor()
                sql = backend.translate_placeholder(
                    "SELECT daily_budget_usd, monthly_budget_usd FROM session_metadata WHERE session_id = ?"
                )
                cursor.execute(sql, (session_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "daily_budget_usd": row[0] if row[0] is not None else None,
                        "monthly_budget_usd": row[1] if row[1] is not None else None,
                    }
        except Exception:
            pass
        return None

    @staticmethod
    def _get_global_cap(key: str) -> Optional[float]:
        """Read a global cap from app_settings KV store."""
        from backend.database import _get_backend
        try:
            backend = _get_backend()
            with backend.connect() as conn:
                cursor = conn.cursor()
                sql = backend.translate_placeholder(
                    "SELECT value FROM app_settings WHERE key = ?"
                )
                cursor.execute(sql, (key,))
                row = cursor.fetchone()
                if row:
                    val = float(row[0])
                    return val if val > 0 else None
        except Exception:
            pass
        return None


# ── Approval Queue ────────────────────────────────────────────────────────────────

class ApprovalQueue:
    """
    Human-in-the-loop approval queue.

    Agents call ``request_approval()`` before running a high-risk action.
    The operator uses the dashboard (or REST API) to approve or reject the request.
    The agent polls ``is_approved()`` or awaits ``wait_for_decision()``.
    """

    STATUS_PENDING = "PENDING"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"

    @staticmethod
    def request_approval(
        agent_id: str,
        action_name: str,
        payload: dict,
        description: str = "",
        bundle=None,
        session_id: str | None = None,
    ) -> int:
        """
        Create a new approval request row. Returns the request ID.
        When ``bundle`` is set, the evidence row is inserted in the same transaction.
        """
        from backend.database import PostgresBackend, _get_backend
        from backend.evidence import bundle_hash as _bundle_hash

        now = datetime.now(timezone.utc).isoformat()
        stored_hash = _bundle_hash(bundle) if bundle is not None else None
        bundle_json = None
        schema_ver = 1
        if bundle is not None:
            bundle_json = json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False)
            schema_ver = bundle.schema_ver
            if not description:
                description = bundle.description
        backend = _get_backend()
        insert_sql = backend.translate_placeholder(
            "INSERT INTO approval_requests "
            "(agent_id, action_name, payload, description, status, created_at, bundle_hash, session_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
        params = (
            agent_id,
            action_name,
            json.dumps(payload, ensure_ascii=False),
            description,
            ApprovalQueue.STATUS_PENDING,
            now,
            stored_hash,
            session_id,
        )
        with backend.connect() as conn:
            cur = conn.cursor()
            if isinstance(backend, PostgresBackend):
                cur.execute(insert_sql.rstrip(";") + " RETURNING id", params)
                request_id = cur.fetchone()[0]
            else:
                cur.execute(insert_sql, params)
                request_id = cur.lastrowid
            if bundle_json is not None and request_id:
                ev_sql = backend.translate_placeholder(
                    "INSERT INTO approval_evidence "
                    "(request_id, bundle_json, bundle_hash, schema_ver, created_at) "
                    "VALUES (?, ?, ?, ?, ?)"
                )
                cur.execute(ev_sql, (request_id, bundle_json, stored_hash, schema_ver, now))

            from backend.decision_log import _tx_conn, append as dl_append

            token = _tx_conn.set(conn)
            try:
                dl_append(
                    "REQUESTED",
                    request_id=request_id or 0,
                    actor=f"agent:{agent_id}",
                    action_name=action_name,
                    payload=payload,
                    bundle_hash=stored_hash,
                    auth_method="agent",
                )
            finally:
                _tx_conn.reset(token)

            conn.commit()

        logger.info(
            f"[ApprovalQueue] New request #{request_id}: agent={agent_id} "
            f"action={action_name}"
        )
        try:
            from backend.websocket_manager import broadcast_sync
            broadcast_sync({"type": "approval_update", "id": request_id or 0, "status": ApprovalQueue.STATUS_PENDING})
        except Exception:
            pass
        return request_id or 0

    @staticmethod
    def resolve(
        request_id: int,
        decision: str,
        resolver_note: str = "",
        *,
        principal: Optional[Any] = None,
    ) -> bool:
        """
        Resolve an approval request. decision must be 'APPROVED' or 'REJECTED'.
        Returns True on success.
        """
        if decision not in (ApprovalQueue.STATUS_APPROVED, ApprovalQueue.STATUS_REJECTED):
            raise ValueError(f"Invalid decision '{decision}'. Must be APPROVED or REJECTED.")

        if principal is None:
            logger.warning("[ApprovalQueue] resolve called without explicit principal; falling back to system admin")
            from backend.identity import Principal
            principal = Principal("system", ("admin",))

        from backend.database import _get_backend
        from backend.decision_log import _tx_conn, append as dl_append

        now = datetime.now(timezone.utc).isoformat()
        backend = _get_backend()
        with backend.connect() as conn:
            cur = conn.cursor()
            # Resolve-once rule: only PENDING rows can be resolved
            check_sql = backend.translate_placeholder(
                "SELECT status, action_name, payload, bundle_hash FROM approval_requests WHERE id = ?"
            )
            cur.execute(check_sql, (request_id,))
            row = cur.fetchone()
            if not row or row[0] != ApprovalQueue.STATUS_PENDING:
                return False

            action_name = row[1]
            raw_payload = row[2]
            bundle_hash = row[3]
            try:
                payload = json.loads(raw_payload) if isinstance(raw_payload, str) else dict(raw_payload or {})
            except Exception:
                payload = {}

            sql = backend.translate_placeholder(
                "UPDATE approval_requests SET status = ?, resolver_note = ?, resolved_at = ? WHERE id = ? AND status = ?"
            )
            cur.execute(sql, (decision, resolver_note, now, request_id, ApprovalQueue.STATUS_PENDING))
            if cur.rowcount <= 0:
                return False

            token = _tx_conn.set(conn)
            try:
                dl_append(
                    decision,
                    request_id=request_id,
                    actor=principal,
                    action_name=action_name,
                    payload=payload,
                    bundle_hash=bundle_hash,
                    reason=resolver_note,
                )
            finally:
                _tx_conn.reset(token)

            conn.commit()

        logger.info(f"[ApprovalQueue] Request #{request_id} → {decision}")
        try:
            from backend.websocket_manager import broadcast_sync
            broadcast_sync({"type": "approval_update", "id": request_id, "status": decision})
        except Exception:
            pass
        return True

    @staticmethod
    def get_pending() -> list[dict]:
        """Return all PENDING approval requests, newest first."""
        from backend.database import _get_backend
        backend = _get_backend()
        with backend.connect() as conn:
            cursor = conn.cursor()
            sql = backend.translate_placeholder(
                "SELECT r.id, r.agent_id, r.action_name, r.payload, r.description, r.status, r.created_at, "
                "r.bundle_hash, e.bundle_json "
                "FROM approval_requests r "
                "LEFT JOIN approval_evidence e ON e.request_id = r.id "
                "WHERE r.status = ? ORDER BY r.id DESC"
            )
            cursor.execute(sql, (ApprovalQueue.STATUS_PENDING,))
            cols = ["id", "agent_id", "action_name", "payload", "description", "status", "created_at", "bundle_hash", "bundle_json"]
            rows = cursor.fetchall()
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            raw_b = d.pop("bundle_json")
            flags = []
            if raw_b:
                try:
                    flags = (json.loads(raw_b).get("flags") or [])[:5]
                except Exception:
                    pass
            d["flags"] = flags
            d["bundle_hash"] = d["bundle_hash"] or ""
            result.append(d)
        return result

    @staticmethod
    def get_all(limit: int = 50) -> list[dict]:
        """Return all approval requests (any status), newest first."""
        from backend.database import _get_backend
        backend = _get_backend()
        with backend.connect() as conn:
            cursor = conn.cursor()
            sql = backend.translate_placeholder(
                "SELECT r.id, r.agent_id, r.action_name, r.payload, r.description, r.status, r.created_at, "
                "r.resolved_at, r.resolver_note, r.bundle_hash, e.bundle_json "
                "FROM approval_requests r "
                "LEFT JOIN approval_evidence e ON e.request_id = r.id "
                "ORDER BY r.id DESC LIMIT ?"
            )
            cursor.execute(sql, (limit,))
            cols = ["id", "agent_id", "action_name", "payload", "description", "status",
                    "created_at", "resolved_at", "resolver_note", "bundle_hash", "bundle_json"]
            rows = cursor.fetchall()
        result = []
        for row in rows:
            d = dict(zip(cols, row))
            raw_b = d.pop("bundle_json")
            flags = []
            if raw_b:
                try:
                    flags = (json.loads(raw_b).get("flags") or [])[:5]
                except Exception:
                    pass
            d["flags"] = flags
            d["bundle_hash"] = d["bundle_hash"] or ""
            result.append(d)
        return result

    @staticmethod
    def get_detail(request_id: int) -> Optional[dict]:
        """Request row plus the stored evidence bundle. None if the id is missing."""
        from backend.database import _get_backend
        backend = _get_backend()
        with backend.connect() as conn:
            cursor = conn.cursor()
            sql = backend.translate_placeholder(
                "SELECT r.id, r.agent_id, r.action_name, r.payload, r.description, r.status, "
                "r.created_at, r.resolved_at, r.resolver_note, r.bundle_hash, r.session_id, e.bundle_json "
                "FROM approval_requests r LEFT JOIN approval_evidence e ON e.request_id = r.id "
                "WHERE r.id = ?"
            )
            cursor.execute(sql, (request_id,))
            row = cursor.fetchone()
        if not row:
            return None
        cols = [
            "id", "agent_id", "action_name", "payload", "description", "status",
            "created_at", "resolved_at", "resolver_note", "bundle_hash", "session_id",
            "bundle_json",
        ]
        detail = dict(zip(cols, row))
        raw = detail.pop("bundle_json")
        detail["bundle"] = json.loads(raw) if raw else None
        return detail

    @staticmethod
    def get_status(request_id: int) -> Optional[str]:
        """Return the status string of a request, or None if not found."""
        from backend.database import _get_backend
        backend = _get_backend()
        with backend.connect() as conn:
            cursor = conn.cursor()
            sql = backend.translate_placeholder(
                "SELECT status FROM approval_requests WHERE id = ?"
            )
            cursor.execute(sql, (request_id,))
            row = cursor.fetchone()
        return row[0] if row else None

    @staticmethod
    def count_pending() -> int:
        """Return count of PENDING approval requests (for badge display)."""
        from backend.database import _get_backend
        backend = _get_backend()
        with backend.connect() as conn:
            cursor = conn.cursor()
            sql = backend.translate_placeholder(
                "SELECT COUNT(*) FROM approval_requests WHERE status = ?"
            )
            cursor.execute(sql, (ApprovalQueue.STATUS_PENDING,))
            row = cursor.fetchone()
        return row[0] if row else 0

    @staticmethod
    def find_latest(agent_id: str, action_name: str, payload: dict) -> Optional[dict]:
        """Newest non-consumed request with the same agent, action, and payload."""
        wanted = _payload_key(payload)
        from backend.database import _get_backend
        backend = _get_backend()
        with backend.connect() as conn:
            cursor = conn.cursor()
            sql = backend.translate_placeholder(
                "SELECT id, status, payload FROM approval_requests "
                "WHERE agent_id = ? AND action_name = ? ORDER BY id DESC LIMIT 20"
            )
            cursor.execute(sql, (agent_id, action_name))
            rows = cursor.fetchall()
        for row in rows:
            if row[1] == "CONSUMED":
                continue
            if _payload_key_stored(row[2]) == wanted:
                return {"id": row[0], "status": row[1]}
        return None

    @staticmethod
    def consume(request_id: int) -> None:
        """One approval authorizes one execution."""
        from backend.database import _get_backend
        from backend.decision_log import _tx_conn, append as dl_append

        now = datetime.now(timezone.utc).isoformat()
        backend = _get_backend()
        with backend.connect() as conn:
            cur = conn.cursor()
            check_sql = backend.translate_placeholder(
                "SELECT status, action_name, payload, bundle_hash FROM approval_requests WHERE id = ?"
            )
            cur.execute(check_sql, (request_id,))
            row = cur.fetchone()
            if not row or row[0] != ApprovalQueue.STATUS_APPROVED:
                return

            action_name = row[1]
            raw_payload = row[2]
            bundle_hash = row[3]
            try:
                payload = json.loads(raw_payload) if isinstance(raw_payload, str) else dict(raw_payload or {})
            except Exception:
                payload = {}

            sql = backend.translate_placeholder(
                "UPDATE approval_requests SET status = ?, resolved_at = ? WHERE id = ? AND status = ?"
            )
            cur.execute(sql, ("CONSUMED", now, request_id, ApprovalQueue.STATUS_APPROVED))
            if cur.rowcount <= 0:
                return

            token = _tx_conn.set(conn)
            try:
                dl_append(
                    "CONSUMED",
                    request_id=request_id,
                    actor="system",
                    action_name=action_name,
                    payload=payload,
                    bundle_hash=bundle_hash,
                    auth_method="system",
                )
            finally:
                _tx_conn.reset(token)

            conn.commit()
        try:
            from backend.websocket_manager import broadcast_sync
            broadcast_sync({"type": "approval_update", "id": request_id, "status": "CONSUMED"})
        except Exception:
            pass


def _payload_key(payload: dict) -> str:
    try:
        return json.dumps(payload or {}, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return json.dumps(str(payload), ensure_ascii=False)


def _payload_key_stored(raw: str) -> str:
    try:
        return json.dumps(json.loads(raw or "{}"), ensure_ascii=False, sort_keys=True)
    except Exception:
        return raw or ""


def _high_risk_names() -> frozenset[str]:
    """Core names plus whatever each plugin contributes via high_risk_tools()."""
    names = set(HIGH_RISK_TOOLS)
    from backend.plugins import collect
    for extra in collect("high_risk_tools"):
        if isinstance(extra, str):
            names.add(extra)
        else:
            names.update(str(n) for n in extra)
    return frozenset(names)


def _requires_approval(action_name: str) -> bool:
    if action_name in _high_risk_names():
        return True
    # MCP names arrive at runtime. Gate from the tool's own annotations.
    from backend.mcp_client import mcp_tool_needs_approval
    return mcp_tool_needs_approval(action_name)


def gate_tool(agent_id: str, action_name: str, payload: dict) -> Optional[str]:
    """Block a high-risk tool until a human approves that exact call.

    Returns None when the tool may run. Otherwise a JSON string for the agent.
    """
    if not _requires_approval(action_name):
        return None
    agent_id = agent_id or "default"
    payload = payload or {}
    match = ApprovalQueue.find_latest(agent_id, action_name, payload)
    if match and match["status"] == ApprovalQueue.STATUS_APPROVED:
        ApprovalQueue.consume(match["id"])
        return None
    if match and match["status"] == ApprovalQueue.STATUS_PENDING:
        request_id = match["id"]
    elif match and match["status"] == ApprovalQueue.STATUS_REJECTED:
        return json.dumps({
            "status": ApprovalQueue.STATUS_REJECTED,
            "request_id": match["id"],
            "error": f"Human rejected {action_name}.",
        }, ensure_ascii=False)
    else:
        from backend.evidence import build_bundle, cap_bundle, evidence_ctx, redact_bundle
        bundle = cap_bundle(redact_bundle(build_bundle(
            agent_id, action_name, payload, evidence_ctx.get(),
        )))
        bundle.links = {**bundle.links, "session_id": agent_id}
        request_id = ApprovalQueue.request_approval(
            agent_id=agent_id,
            action_name=action_name,
            payload=payload,
            description=bundle.description,
            bundle=bundle,
            session_id=agent_id,
        )
    return json.dumps({
        "status": "PENDING_APPROVAL",
        "request_id": request_id,
        "error": f"Awaiting human approval for {action_name}.",
    }, ensure_ascii=False)


# ── Local PII Guard ───────────────────────────────────────────────────────────────

import re
from typing import Tuple, List, Dict, Any


class PIIGuard:
    """
    Local Open-Source PII (Personally Identifiable Information) Redaction & Masking Guard.
    Redacts sensitive credentials, tokens, emails, phone numbers, and payment details locally
    without routing data to external commercial third-party cloud APIs.
    """

    PATTERNS = {
        "EMAIL": re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
        "PHONE": re.compile(r'(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
        "API_KEY_OPENAI": re.compile(r'\bsk-[a-zA-Z0-9_-]{20,}\b'),
        "API_KEY_GITHUB": re.compile(r'\bgh[pousr]_[a-zA-Z0-9]{36,}\b'),
        "API_KEY_GENERIC": re.compile(r'(?i)(?:api_key|access_token|secret_key|private_key)\s*[:=]\s*["\']?([a-zA-Z0-9_\-\.]{16,})["\']?'),
        "BEARER_TOKEN": re.compile(r'(?i)bearer\s+[a-zA-Z0-9_\-\.]{20,}'),
        "CREDIT_CARD": re.compile(r'\b(?:\d{4}[-\s]?){3}\d{4}\b'),
        "SSN_US": re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
    }

    @classmethod
    def mask_pii(cls, text: str) -> Tuple[str, Dict[str, int]]:
        """
        Masks all detected PII entities with standard tokens: [EMAIL_REDACTED], [KEY_REDACTED], etc.
        Returns:
            Tuple of (redacted_text, detection_counts_dict)
        """
        if not text or not isinstance(text, str):
            return text or "", {}

        redacted = text
        detections: Dict[str, int] = {}

        for pii_type, pattern in cls.PATTERNS.items():
            matches = pattern.findall(redacted)
            if matches:
                detections[pii_type] = len(matches)
                tag = f"[{pii_type}_REDACTED]"
                redacted = pattern.sub(tag, redacted)

        return redacted, detections

    @classmethod
    def contains_pii(cls, text: str) -> bool:
        """Returns True if any sensitive PII pattern matches."""
        if not text or not isinstance(text, str):
            return False
        return any(pattern.search(text) for pattern in cls.PATTERNS.values())


# ── OWASP Memory Poisoning & Prompt Injection Guard ────────────────────────────────

class MemoryGuard:
    """
    OWASP ASI06 / LLM01 Memory Poisoning & Indirect Prompt Injection Guard.
    Audits documents, web scrapes, and external context before indexing into
    the vector database (Qdrant / PostgresGraph) to prevent memory corruption.
    """

    INJECTION_PATTERNS = [
        re.compile(r'(?i)ignore\s+(all\s+)?(previous|prior)\s+(instructions|directives|commands)'),
        re.compile(r'(?i)you\s+are\s+now\s+in\s+(developer|dan|jailbreak|unrestricted)\s+mode'),
        re.compile(r'(?i)system\s+prompt\s+override'),
        re.compile(r'(?i)disregard\s+(the\s+)?above\s+and'),
        re.compile(r'(?i)<\s*system\s*>'),
        re.compile(r'(?i)\[\s*INST\s*\]'),
        re.compile(r'(?i)\[\s*SYS\s*\]'),
        re.compile(r'(?i)!\[.*?\]\((https?:\/\/[^\s\)]+[\?&](?:token|key|secret|cookie|pass|pwd)=)'), # Image exfiltration
    ]

    ZERO_WIDTH_CHARS = re.compile(r'[\u200B\u200C\u200D\u200E\u200F\uFEFF\u202A-\u202E]')

    @classmethod
    def audit_text(cls, text: str, source: str = "manual") -> Dict[str, Any]:
        """
        Audits input text for prompt injection markers, hidden unicode channels, and PII.
        """
        if not text or not isinstance(text, str):
            return {
                "is_safe": True,
                "threat_level": "CLEAN",
                "threats": [],
                "clean_text": text or "",
                "pii_detected": False
            }

        threats = []
        # 1. Strip invisible zero-width unicode injection channels
        clean_text = cls.ZERO_WIDTH_CHARS.sub("", text)
        if len(clean_text) < len(text):
            threats.append(f"Stripped {len(text) - len(clean_text)} invisible zero-width unicode characters.")

        # 2. Check for Prompt Injection / Jailbreak Patterns
        for pat in cls.INJECTION_PATTERNS:
            if pat.search(clean_text):
                threats.append(f"Prompt injection marker detected: '{pat.pattern}'")

        # 3. PII Redaction
        clean_text, pii_counts = PIIGuard.mask_pii(clean_text)
        if pii_counts:
            threats.append(f"Redacted sensitive PII entities: {list(pii_counts.keys())}")

        threat_level = "CLEAN"
        if any("Prompt injection" in t for t in threats):
            threat_level = "BLOCKED" if source in ["upload", "web_search", "untrusted"] else "HIGH"
        elif threats:
            threat_level = "LOW"

        return {
            "is_safe": (threat_level != "BLOCKED"),
            "threat_level": threat_level,
            "threats": threats,
            "clean_text": clean_text,
            "pii_detected": len(pii_counts) > 0
        }

    @classmethod
    def sanitize_for_indexing(cls, text: str, source: str = "manual") -> Tuple[bool, str, List[str]]:
        """
        Gatekeeper for vector memory indexing.
        Returns:
            Tuple of (allow_indexing: bool, clean_text: str, warnings: List[str])
        """
        audit = cls.audit_text(text, source=source)
        if not audit["is_safe"]:
            logger.warning(
                f"[MemoryGuard] BLOCKED poisoned document from source='{source}'. "
                f"Threats: {audit['threats']}"
            )
            return False, "", audit["threats"]
        return True, audit["clean_text"], audit["threats"]

