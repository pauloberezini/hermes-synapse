"""Wait-or-retry wrapper around ``gate_tool`` + ``ApprovalQueue``."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Optional

from backend.gateway.classify import needs_approval
from backend.governance import HIGH_RISK_TOOLS, ApprovalQueue, gate_tool

ON_TIMEOUT_FAIL_CLOSED = "fail_closed"
ON_TIMEOUT_PENDING_RETRY = "pending_retry"
GATEWAY_MCP_SERVER = "gateway"


@dataclass(frozen=True)
class GateDecision:
    """Outcome of one gated call. ``effect`` is allow, deny, or pending."""

    effect: str
    request_id: int | None = None
    status: str | None = None
    error: str = ""
    body: dict[str, Any] | None = None


def _register_for_gate(name: str, annotations: dict | None) -> None:
    """Make ``gate_tool`` treat names that are not in HIGH_RISK_TOOLS as MCP-gated."""
    if name in HIGH_RISK_TOOLS:
        return
    from backend.mcp_client import mcp_tool_to_server, note_mcp_tool

    if name in mcp_tool_to_server:
        return
    note_mcp_tool(GATEWAY_MCP_SERVER, {"name": name, "annotations": annotations or {}})


def _parse_gate(raw: Optional[str]) -> dict | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"status": "ERROR", "error": raw}
    return parsed if isinstance(parsed, dict) else {"status": "ERROR", "error": raw}


def decide(
    agent_id: str,
    action_name: str,
    payload: dict,
    *,
    annotations: dict | None = None,
    known_mcp: bool = False,
    wait: bool = True,
    timeout_s: float = 50.0,
    on_timeout: str = ON_TIMEOUT_FAIL_CLOSED,
    display_name: str = "gateway",
) -> GateDecision:
    """Create/match an approval, optionally wait, then allow / deny / pending.

    ``gate_tool`` stays retry-based. This wrapper adds the blocking wait the
    MCP proxy needs, and a ``pending_retry`` timeout mode that returns
    PENDING_APPROVAL instead of hanging past the client's request timeout.
    """
    if not needs_approval(action_name, annotations, known_mcp=known_mcp):
        return GateDecision(effect="allow")

    _register_for_gate(action_name, annotations)

    from backend.agent import approval_context

    hint = json.dumps(payload or {}, ensure_ascii=False)[:500]
    with approval_context(display_name, hint, "gateway"):
        blocked = gate_tool(agent_id or "gateway", action_name, payload or {})

    body = _parse_gate(blocked)
    if body is None:
        return GateDecision(effect="allow")

    status = body.get("status")
    request_id = body.get("request_id")
    error = str(body.get("error") or "")

    if status == ApprovalQueue.STATUS_REJECTED:
        return GateDecision(effect="deny", request_id=request_id, status=status, error=error, body=body)
    if status == "INVALID_ARGUMENTS":
        return GateDecision(effect="deny", request_id=request_id, status=status, error=error, body=body)
    if status != "PENDING_APPROVAL":
        return GateDecision(
            effect="deny",
            request_id=request_id,
            status=status or "ERROR",
            error=error or json.dumps(body, ensure_ascii=False),
            body=body,
        )

    if not wait:
        return GateDecision(effect="pending", request_id=request_id, status=status, error=error, body=body)

    waited = ApprovalQueue.wait_for_decision(int(request_id or 0), timeout_s=timeout_s)
    if waited == ApprovalQueue.STATUS_APPROVED:
        blocked2 = gate_tool(agent_id or "gateway", action_name, payload or {})
        if blocked2 is None:
            return GateDecision(effect="allow", request_id=request_id, status="CONSUMED", body=body)
        body2 = _parse_gate(blocked2) or {}
        return GateDecision(
            effect="deny",
            request_id=body2.get("request_id", request_id),
            status=body2.get("status"),
            error=str(body2.get("error") or "approved request could not be consumed"),
            body=body2,
        )
    if waited == ApprovalQueue.STATUS_REJECTED:
        return GateDecision(
            effect="deny",
            request_id=request_id,
            status=waited,
            error=error or f"Human rejected {action_name}.",
            body=body,
        )

    if on_timeout == ON_TIMEOUT_PENDING_RETRY:
        return GateDecision(
            effect="pending",
            request_id=request_id,
            status="PENDING_APPROVAL",
            error=error or (
                f"Awaiting human approval for {action_name}. "
                "Retry with identical arguments after approval."
            ),
            body=body,
        )
    return GateDecision(
        effect="deny",
        request_id=request_id,
        status="TIMEOUT",
        error=(
            f"Timed out waiting for human approval of {action_name} "
            f"(request_id={request_id}). Fail-closed; request stays PENDING."
        ),
        body=body,
    )


def settings_from_env() -> dict[str, Any]:
    """Read wait/timeout/session from the process environment."""
    wait_raw = os.environ.get("HERMES_GATEWAY_WAIT", "1").strip().lower()
    wait = wait_raw not in ("0", "false", "no")
    try:
        timeout_s = float(os.environ.get("HERMES_GATEWAY_WAIT_TIMEOUT_S", "50"))
    except ValueError:
        timeout_s = 50.0
    on_timeout = (os.environ.get("HERMES_GATEWAY_ON_TIMEOUT", ON_TIMEOUT_FAIL_CLOSED).strip()
                  or ON_TIMEOUT_FAIL_CLOSED)
    session_id = os.environ.get("HERMES_GATEWAY_SESSION_ID", "gateway").strip() or "gateway"
    display_name = os.environ.get("HERMES_GATEWAY_AGENT_NAME", "gateway").strip() or "gateway"
    return {
        "wait": wait,
        "timeout_s": timeout_s,
        "on_timeout": on_timeout,
        "session_id": session_id,
        "display_name": display_name,
    }
