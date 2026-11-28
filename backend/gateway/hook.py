"""Claude Code PreToolUse hook mapping. The process that Claude/Cursor
spawns is ``scripts/gateway/claude_pre_tool_use.py`` (HTTP only, no DB).

This module runs inside the backend and is reached via
``POST /api/gateway/pre-tool``.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from backend.gateway.decide import (
    ON_TIMEOUT_PENDING_RETRY,
    decide,
    pending_retry_error,
    settings_from_env,
)
from backend.gateway.token import redact_token

# Leave headroom under the host hook timeout (example settings use 50s).
HOOK_WAIT_HEADROOM_S = 5.0
DEFAULT_HOST_HOOK_TIMEOUT_S = 50.0


def tool_name(event: dict) -> str:
    name = str(event.get("tool_name") or event.get("tool") or "")
    if name:
        return name
    # Cursor beforeShellExecution: {command, cwd} with no tool_name.
    if event.get("command"):
        return "Shell" if (event.get("cwd") and not event.get("tool_input")) else "Bash"
    return ""


def tool_input(event: dict) -> dict:
    raw = event.get("tool_input") or event.get("input") or event.get("arguments")
    if isinstance(raw, dict):
        return raw
    if event.get("command"):
        payload = {"command": event["command"]}
        if event.get("cwd"):
            payload["cwd"] = event["cwd"]
        return payload
    if raw:
        return {"_raw": raw}
    return {}


def session_id(event: dict, fallback: str) -> str:
    return str(event.get("session_id") or event.get("conversation_id") or fallback)


def claude_output(effect: str, reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow" if effect == "allow" else "deny",
            "permissionDecisionReason": redact_token(reason),
        }
    }


def cursor_output(effect: str, reason: str) -> dict[str, Any]:
    reason = redact_token(reason)
    return {
        "permission": "allow" if effect == "allow" else "deny",
        "user_message": reason,
        "agent_message": reason,
    }


def _hook_timeout_s(cfg: dict[str, Any]) -> float:
    try:
        host_timeout = float(os.environ.get("HERMES_HOOK_HOST_TIMEOUT_S", str(DEFAULT_HOST_HOOK_TIMEOUT_S)))
    except ValueError:
        host_timeout = DEFAULT_HOST_HOOK_TIMEOUT_S
    cap = max(0.1, host_timeout - HOOK_WAIT_HEADROOM_S)
    if not cfg["wait"]:
        return cfg["timeout_s"]
    return min(float(cfg["timeout_s"]), cap)


def _hook_on_timeout() -> str:
    raw = os.environ.get("HERMES_GATEWAY_ON_TIMEOUT")
    if raw is None or not str(raw).strip():
        return ON_TIMEOUT_PENDING_RETRY
    return str(raw).strip()


def _log_hook(action_name: str, request_id: int | None, reason: str, extra: dict[str, Any]) -> None:
    from backend.decision_log import append as dl_append
    from backend.governance import ApprovalQueue

    bundle_hash = None
    rid = int(request_id or 0)
    if rid:
        detail = ApprovalQueue.get_detail(rid)
        if detail:
            bundle_hash = detail.get("bundle_hash")
    dl_append(
        "HOOK",
        request_id=rid,
        actor="system",
        action_name=action_name or "unknown",
        payload={"source": "hook", **extra},
        bundle_hash=bundle_hash,
        reason=redact_token(reason)[:500],
        auth_method="system",
    )


def handle_event(event: dict, *, fmt: str | None = None) -> dict[str, Any]:
    cfg = settings_from_env()
    fmt = (fmt or os.environ.get("HERMES_HOOK_FORMAT", "claude")).strip() or "claude"
    out = cursor_output if fmt == "cursor" else claude_output
    name = tool_name(event)
    if not name:
        reason = "hook: missing tool_name (fail-closed)"
        _log_hook("unknown", None, reason, {"effect": "deny", "status": "FAIL_CLOSED"})
        return out("deny", reason)

    try:
        decision = decide(
            session_id(event, cfg["session_id"]),
            name,
            tool_input(event),
            known_mcp=False,
            wait=cfg["wait"],
            timeout_s=_hook_timeout_s(cfg),
            on_timeout=_hook_on_timeout(),
            display_name=os.environ.get("HERMES_GATEWAY_AGENT_NAME", "claude-code"),
        )
    except Exception as exc:
        reason = f"hook: backend unreachable (fail-closed): {type(exc).__name__}"
        _log_hook(name, None, reason, {"effect": "deny", "status": "FAIL_CLOSED"})
        return out("deny", reason)

    if decision.effect == "allow":
        reason = "hermes gateway allow"
        _log_hook(name, decision.request_id, reason, {"effect": "allow", "status": decision.status or "ALLOW"})
        return out("allow", reason)
    if decision.effect == "pending":
        reason = decision.error or pending_retry_error(name, decision.request_id)
        _log_hook(name, decision.request_id, reason, {"effect": "pending", "status": decision.status or "PENDING_APPROVAL"})
        return out("deny", reason)
    reason = decision.error or f"hermes deny status={decision.status} request_id={decision.request_id}"
    _log_hook(name, decision.request_id, reason, {"effect": "deny", "status": decision.status or "DENY"})
    return out("deny", reason)


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        if not isinstance(event, dict):
            raise ValueError("hook input must be a JSON object")
    except Exception as exc:
        reason = f"hook: invalid JSON (fail-closed): {type(exc).__name__}"
        try:
            _log_hook("unknown", None, reason, {"effect": "deny", "status": "FAIL_CLOSED"})
        except Exception:
            pass
        sys.stdout.write(json.dumps(claude_output("deny", reason)) + "\n")
        return 0
    try:
        result = handle_event(event)
    except Exception as exc:
        reason = f"hook: unhandled error (fail-closed): {type(exc).__name__}"
        try:
            _log_hook("unknown", None, reason, {"effect": "deny", "status": "FAIL_CLOSED"})
        except Exception:
            pass
        result = claude_output("deny", reason)
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
