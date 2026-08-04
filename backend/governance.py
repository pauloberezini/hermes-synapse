"""
backend/governance.py — Hermes Synapse Governance Engine (Paperclip-inspired)

Provides:
  - BudgetGuard: Enforces per-session and global token/dollar spend caps.
  - ApprovalQueue: Stores and resolves human-in-the-loop approval requests.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional

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
    ) -> int:
        """
        Create a new approval request row. Returns the request ID.
        Agents should persist this ID and poll with ``is_approved(request_id)``.
        """
        from backend.database import _lastrowid
        now = datetime.now(timezone.utc).isoformat()
        sql = """
            INSERT INTO approval_requests (agent_id, action_name, payload, description, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """
        params = (
            agent_id,
            action_name,
            json.dumps(payload, ensure_ascii=False),
            description,
            ApprovalQueue.STATUS_PENDING,
            now,
        )
        request_id = _lastrowid(sql, params)
        logger.info(
            f"[ApprovalQueue] New request #{request_id}: agent={agent_id} "
            f"action={action_name}"
        )
        return request_id or 0

    @staticmethod
    def resolve(request_id: int, decision: str, resolver_note: str = "") -> bool:
        """
        Resolve an approval request.  decision must be 'APPROVED' or 'REJECTED'.
        Returns True on success.
        """
        if decision not in (ApprovalQueue.STATUS_APPROVED, ApprovalQueue.STATUS_REJECTED):
            raise ValueError(f"Invalid decision '{decision}'. Must be APPROVED or REJECTED.")
        from backend.database import _rowcount
        now = datetime.now(timezone.utc).isoformat()
        sql = "UPDATE approval_requests SET status = ?, resolver_note = ?, resolved_at = ? WHERE id = ?"
        params = (decision, resolver_note, now, request_id)
        changed = _rowcount(sql, params) > 0
        if changed:
            logger.info(f"[ApprovalQueue] Request #{request_id} → {decision}")
        return changed

    @staticmethod
    def get_pending() -> list[dict]:
        """Return all PENDING approval requests, newest first."""
        from backend.database import _get_backend
        backend = _get_backend()
        with backend.connect() as conn:
            cursor = conn.cursor()
            sql = backend.translate_placeholder(
                "SELECT id, agent_id, action_name, payload, description, status, created_at "
                "FROM approval_requests WHERE status = ? ORDER BY id DESC"
            )
            cursor.execute(sql, (ApprovalQueue.STATUS_PENDING,))
            cols = ["id", "agent_id", "action_name", "payload", "description", "status", "created_at"]
            rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]

    @staticmethod
    def get_all(limit: int = 50) -> list[dict]:
        """Return all approval requests (any status), newest first."""
        from backend.database import _get_backend
        backend = _get_backend()
        with backend.connect() as conn:
            cursor = conn.cursor()
            sql = backend.translate_placeholder(
                "SELECT id, agent_id, action_name, payload, description, status, created_at, resolved_at, resolver_note "
                "FROM approval_requests ORDER BY id DESC LIMIT ?"
            )
            cursor.execute(sql, (limit,))
            cols = ["id", "agent_id", "action_name", "payload", "description", "status",
                    "created_at", "resolved_at", "resolver_note"]
            rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]

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
