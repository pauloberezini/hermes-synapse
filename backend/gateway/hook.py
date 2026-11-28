"""Claude Code PreToolUse hook: map built-in tools onto ApprovalQueue.

Exit 0 with JSON. Deny on timeout, parse error, or backend unreachable
(fail-closed). Pair with ``onFailure: "block"`` in settings.json so a
killed/missing script cannot fail open.

Cursor's equivalent is ``preToolUse`` / ``beforeShellExecution`` /
``beforeMCPExecution`` in ``hooks.json`` (see scripts/gateway/example.cursor.hooks.json).
That path was not executed in this VM.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from backend.gateway.decide import decide, settings_from_env


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
            "permissionDecisionReason": reason,
        }
    }


def cursor_output(effect: str, reason: str) -> dict[str, Any]:
    return {
        "permission": "allow" if effect == "allow" else "deny",
        "user_message": reason,
        "agent_message": reason,
    }


def handle_event(event: dict, *, fmt: str | None = None) -> dict[str, Any]:
    cfg = settings_from_env()
    fmt = (fmt or os.environ.get("HERMES_HOOK_FORMAT", "claude")).strip() or "claude"
    out = cursor_output if fmt == "cursor" else claude_output
    name = tool_name(event)
    if not name:
        return out("deny", "hook: missing tool_name (fail-closed)")

    try:
        decision = decide(
            session_id(event, cfg["session_id"]),
            name,
            tool_input(event),
            known_mcp=False,
            wait=cfg["wait"],
            timeout_s=cfg["timeout_s"],
            on_timeout=cfg["on_timeout"],
            display_name=os.environ.get("HERMES_GATEWAY_AGENT_NAME", "claude-code"),
        )
    except Exception as exc:
        return out("deny", f"hook: backend unreachable (fail-closed): {exc}")

    if decision.effect == "allow":
        return out("allow", "hermes gateway allow")
    if decision.effect == "pending":
        return out(
            "deny",
            f"PENDING_APPROVAL request_id={decision.request_id}. "
            "Approve in Hermes Governance Approvals, then retry this tool "
            "with identical arguments.",
        )
    return out(
        "deny",
        decision.error
        or f"hermes deny status={decision.status} request_id={decision.request_id}",
    )


def main() -> int:
    try:
        event = json.loads(sys.stdin.read() or "{}")
        if not isinstance(event, dict):
            raise ValueError("hook input must be a JSON object")
    except Exception as exc:
        sys.stdout.write(
            json.dumps(claude_output("deny", f"hook: invalid JSON (fail-closed): {exc}"))
            + "\n"
        )
        return 0
    try:
        result = handle_event(event)
    except Exception as exc:
        result = claude_output("deny", f"hook: unhandled error (fail-closed): {exc}")
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
