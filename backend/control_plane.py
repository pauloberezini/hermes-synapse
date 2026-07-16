"""Durable policy gate and audit trail for agent tool execution."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from backend.database import DB_PATH

logger = logging.getLogger("hermes.control_plane")

RISK_ORDER = {"R0": 0, "R1": 1, "R2": 2, "R3": 3, "R4": 4}
OPEN_STATUSES = ("queued", "running", "awaiting_approval", "approved", "blocked")

TOOL_RISKS = {
    "get_system_stats": "R0",
    "get_current_time_israel": "R0",
    "get_weather": "R0",
    "get_calendar_events": "R0",
    "get_todoist_tasks": "R0",
    "get_market_prices": "R0",
    "get_github_summary": "R1",
    "get_rss_digest": "R1",
    "web_search": "R1",
    "list_subagents": "R0",
    "get_subagent_memory": "R0",
    "search_obsidian": "R0",
    "read_obsidian_note": "R0",
    "set_timer": "R2",
    "set_alarm": "R2",
    "cancel_timer_or_alarm": "R2",
    "set_recurring_reminder": "R2",
    "add_price_alert": "R2",
    "call_subagent": "R2",
    "add_calendar_event": "R3",
    "add_todoist_task": "R3",
    "create_subagent": "R3",
    "save_subagent_memory": "R3",
    "create_obsidian_note": "R3",
    "sync_obsidian_vault": "R3",
    "delete_todoist_task": "R4",
    "execute_command": "R4",
}

_SECRET_KEY = re.compile(r"(password|passwd|secret|token|api[_-]?key|authorization|cookie|private[_-]?key)", re.I)
_SECRET_VALUE = re.compile(r"(?i)(bearer\s+)[a-z0-9._~+\-/=]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _SECRET_KEY.search(str(key)) else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    if isinstance(value, str):
        return _SECRET_VALUE.sub(r"\1[REDACTED]", value)
    return value


def _safe_json(value: Any) -> str:
    return json.dumps(_redact(value), ensure_ascii=False, sort_keys=True)


def classify_tool_risk(tool_name: str) -> str:
    if tool_name.startswith(("ctrader_", "bcm_")):
        return "R4"
    return TOOL_RISKS.get(tool_name, "R4")


def _autonomy_for_risk(risk_class: str) -> str:
    return {"R0": "L2", "R1": "L2", "R2": "L2", "R3": "L3", "R4": "L3"}[risk_class]


def _task_from_row(row: sqlite3.Row) -> Dict[str, Any]:
    task = dict(row)
    for field, fallback in (("tool_arguments", {}), ("acceptance", [])):
        try:
            task[field] = json.loads(task.get(field) or "")
        except Exception:
            task[field] = fallback
    task["approval_required"] = task["approvals_required"] > task["approval_count"]
    return task


def _event(
    conn: sqlite3.Connection,
    task_id: Optional[str],
    event_type: str,
    actor: str,
    message: str,
    risk_class: str,
    *,
    output_hash: str = "",
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    conn.execute(
        """INSERT INTO workflow_events
           (task_id, event_type, actor, message, risk_class, confidence, output_hash, metadata, created_at)
           VALUES (?, ?, ?, ?, ?, 'CONFIRMED', ?, ?, ?)""",
        (task_id, event_type, actor, message, risk_class, output_hash, _safe_json(metadata or {}), _now()),
    )


def get_control_state() -> Dict[str, Any]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM control_plane_state WHERE id = 1").fetchone()
    if not row:
        return {"kill_switch": False, "reason": "", "updated_by": "system", "updated_at": ""}
    data = dict(row)
    data["kill_switch"] = bool(data["kill_switch"])
    return data


def set_kill_switch(enabled: bool, reason: str = "", actor: str = "owner") -> Dict[str, Any]:
    now = _now()
    with _connect() as conn:
        conn.execute(
            "UPDATE control_plane_state SET kill_switch = ?, reason = ?, updated_by = ?, updated_at = ? WHERE id = 1",
            (int(enabled), reason[:500], actor, now),
        )
        if enabled:
            conn.execute(
                f"UPDATE workflow_tasks SET status = 'killed', error = ?, updated_at = ?, completed_at = ? "
                f"WHERE status IN ({','.join('?' for _ in OPEN_STATUSES)})",
                (reason[:500] or "Emergency stop", now, now, *OPEN_STATUSES),
            )
        _event(conn, None, "kill_switch_on" if enabled else "kill_switch_off", actor,
               reason[:500] or ("Control Plane stopped" if enabled else "Control Plane resumed"), "R4")
    return get_control_state()


def create_tool_task(tool_name: str, arguments: Dict[str, Any], chat_id: str) -> Dict[str, Any]:
    risk_class = classify_tool_risk(tool_name)
    approvals_required = 1 if risk_class == "R3" else 2 if risk_class == "R4" else 0
    status = "awaiting_approval" if approvals_required else "queued"
    safe_arguments = _redact(arguments)
    canonical = json.dumps([chat_id, tool_name, safe_arguments], ensure_ascii=False, sort_keys=True)
    idempotency_key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    now = _now()

    with _connect() as conn:
        existing = conn.execute(
            f"SELECT * FROM workflow_tasks WHERE idempotency_key = ? "
            f"AND status IN ({','.join('?' for _ in OPEN_STATUSES)}) ORDER BY created_at DESC LIMIT 1",
            (idempotency_key, *OPEN_STATUSES),
        ).fetchone()
        if existing:
            return _task_from_row(existing)

        task_id = f"T-{uuid.uuid4().hex[:12]}"
        rollback = {
            "R0": "No state change expected.",
            "R1": "No local state change expected; stop further requests.",
            "R2": "Cancel the created timer, reminder, alert, or delegated run.",
            "R3": "Use the resource-specific delete/revert action after owner review.",
            "R4": "Manual recovery required; verify backup and restoration procedure before approval.",
        }[risk_class]
        conn.execute(
            """INSERT INTO workflow_tasks
               (id, origin, requester, goal, tool_name, tool_arguments, assignee, risk_class,
                autonomy_level, status, approvals_required, acceptance, rollback,
                idempotency_key, created_at, updated_at)
               VALUES (?, 'agent', ?, ?, ?, ?, 'jarvis', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task_id, chat_id, f"Execute {tool_name}", tool_name, _safe_json(arguments), risk_class,
                _autonomy_for_risk(risk_class), status, approvals_required,
                json.dumps(["Tool returns a valid result", "No policy or budget violation"], ensure_ascii=False),
                rollback, idempotency_key, now, now,
            ),
        )
        _event(conn, task_id, "task_created", "control-plane", f"Tool request classified as {risk_class}", risk_class,
               metadata={"tool": tool_name, "approval_count": approvals_required})
        row = conn.execute("SELECT * FROM workflow_tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_from_row(row)


def get_task(task_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM workflow_tasks WHERE id = ?", (task_id,)).fetchone()
    return _task_from_row(row) if row else None


def list_tasks(limit: int = 100, status: Optional[str] = None) -> list[Dict[str, Any]]:
    limit = max(1, min(int(limit), 250))
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM workflow_tasks WHERE status = ? ORDER BY created_at DESC LIMIT ?", (status, limit)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM workflow_tasks ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [_task_from_row(row) for row in rows]


def list_events(limit: int = 100) -> list[Dict[str, Any]]:
    limit = max(1, min(int(limit), 250))
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM workflow_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    events = [dict(row) for row in rows]
    for event in events:
        try:
            event["metadata"] = json.loads(event.get("metadata") or "{}")
        except Exception:
            event["metadata"] = {}
        event["evidence_id"] = f"EV-{event['id']:06d}"
    return events


def start_task(task_id: str) -> Dict[str, Any]:
    state = get_control_state()
    if state["kill_switch"]:
        raise RuntimeError(f"Control Plane is stopped: {state['reason'] or 'owner request'}")
    now = _now()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM workflow_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        task = _task_from_row(row)
        if task["approval_count"] < task["approvals_required"]:
            raise PermissionError("Task is awaiting approval")
        if task["commands_used"] >= task["budget_commands"]:
            conn.execute("UPDATE workflow_tasks SET status = 'blocked', error = ?, updated_at = ? WHERE id = ?",
                         ("Command budget exhausted", now, task_id))
            _event(conn, task_id, "budget_block", "control-plane", "Command budget exhausted", task["risk_class"])
            raise RuntimeError("Command budget exhausted")
        conn.execute(
            "UPDATE workflow_tasks SET status = 'running', commands_used = commands_used + 1, updated_at = ? WHERE id = ?",
            (now, task_id),
        )
        _event(conn, task_id, "task_started", "control-plane", "Execution started", task["risk_class"])
    return get_task(task_id) or task


def finish_task(task_id: str, result: str, error: str = "") -> Dict[str, Any]:
    try:
        safe_result = _safe_json(json.loads(str(result)))[:4000]
    except Exception:
        safe_result = _SECRET_VALUE.sub(r"\1[REDACTED]", str(result))[:4000]
    digest = hashlib.sha256(safe_result.encode("utf-8")).hexdigest()
    status = "failed" if error else "done"
    now = _now()
    with _connect() as conn:
        row = conn.execute("SELECT risk_class FROM workflow_tasks WHERE id = ?", (task_id,)).fetchone()
        risk_class = row[0] if row else "R4"
        conn.execute(
            "UPDATE workflow_tasks SET status = ?, result = ?, error = ?, updated_at = ?, completed_at = ? WHERE id = ?",
            (status, safe_result, error[:1000], now, now, task_id),
        )
        _event(conn, task_id, "task_failed" if error else "task_completed", "control-plane",
               error[:500] or "Execution completed", risk_class, output_hash=digest)
    return get_task(task_id) or {}


def approve_task(task_id: str, actor: str = "owner") -> Dict[str, Any]:
    now = _now()
    with _connect() as conn:
        row = conn.execute("SELECT * FROM workflow_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        task = _task_from_row(row)
        if task["status"] != "awaiting_approval":
            raise ValueError(f"Task cannot be approved from status {task['status']}")
        next_count = min(task["approval_count"] + 1, task["approvals_required"])
        next_status = "approved" if next_count >= task["approvals_required"] else "awaiting_approval"
        conn.execute(
            "UPDATE workflow_tasks SET approval_count = ?, status = ?, updated_at = ? WHERE id = ?",
            (next_count, next_status, now, task_id),
        )
        _event(conn, task_id, "approval_granted", actor,
               f"Approval {next_count}/{task['approvals_required']} granted", task["risk_class"])
    return get_task(task_id) or {}


def reject_task(task_id: str, reason: str = "Rejected by owner", actor: str = "owner") -> Dict[str, Any]:
    now = _now()
    with _connect() as conn:
        row = conn.execute("SELECT risk_class, status FROM workflow_tasks WHERE id = ?", (task_id,)).fetchone()
        if not row:
            raise KeyError(task_id)
        if row["status"] not in ("awaiting_approval", "approved", "queued"):
            raise ValueError(f"Task cannot be rejected from status {row['status']}")
        conn.execute(
            "UPDATE workflow_tasks SET status = 'rejected', error = ?, updated_at = ?, completed_at = ? WHERE id = ?",
            (reason[:1000], now, now, task_id),
        )
        _event(conn, task_id, "approval_rejected", actor, reason[:500], row["risk_class"])
    return get_task(task_id) or {}


def execute_governed_tool(
    tool_name: str,
    arguments: Dict[str, Any],
    chat_id: str = "default",
    *,
    approved_task_id: Optional[str] = None,
) -> str:
    """Run a tool through durable risk, approval, budget and evidence gates."""
    if approved_task_id:
        task = get_task(approved_task_id)
        if not task:
            return json.dumps({"error": "Approved task not found", "task_id": approved_task_id}, ensure_ascii=False)
        if task["tool_name"] != tool_name:
            return json.dumps({"error": "Approved task/tool mismatch", "task_id": approved_task_id}, ensure_ascii=False)
    else:
        state = get_control_state()
        if state["kill_switch"]:
            return json.dumps({"status": "killed", "error": "Control Plane stopped", "reason": state["reason"]}, ensure_ascii=False)
        task = create_tool_task(tool_name, arguments, chat_id)

    if task["approval_count"] < task["approvals_required"]:
        return json.dumps({
            "status": "awaiting_approval",
            "approval_required": True,
            "task_id": task["id"],
            "risk_class": task["risk_class"],
            "confirmations": f"{task['approval_count']}/{task['approvals_required']}",
            "message": "Action queued in Control Plane and was not executed.",
        }, ensure_ascii=False)

    try:
        from backend.tools import execute_tool
        start_task(task["id"])
        result = execute_tool(tool_name, arguments, chat_id=chat_id)
        parsed_error = ""
        try:
            parsed = json.loads(result)
            parsed_error = str(parsed.get("error") or "") if isinstance(parsed, dict) else ""
        except Exception:
            pass
        finish_task(task["id"], result, parsed_error)
        return result
    except Exception as exc:
        logger.exception("Governed tool execution failed for task %s", task["id"])
        finish_task(task["id"], "", str(exc))
        return json.dumps({"error": str(exc), "task_id": task["id"]}, ensure_ascii=False)


def get_summary(limit: int = 100) -> Dict[str, Any]:
    tasks = list_tasks(limit=limit)
    counts: Dict[str, int] = {}
    for task in tasks:
        counts[task["status"]] = counts.get(task["status"], 0) + 1
    return {
        "state": get_control_state(),
        "counts": counts,
        "pending_approvals": [task for task in tasks if task["status"] == "awaiting_approval"],
        "tasks": tasks,
        "events": list_events(limit=50),
        "policy": {"risk_levels": list(RISK_ORDER), "unknown_tools": "R4", "r4_double_confirmation": True},
    }
