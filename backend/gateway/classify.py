"""Classify a tool call as high-risk.

Reuses ``HIGH_RISK_TOOLS`` / plugin extras, the MCP annotation rule from
``mcp_tool_needs_approval``, plus coding-agent builtins that never appear
on the MCP socket (Bash/Edit/Write, Cursor Shell/Write/Delete).
"""

from __future__ import annotations

from backend.governance import HIGH_RISK_TOOLS, _high_risk_names

# Claude Code built-ins. They do not go through an MCP proxy.
CLAUDE_HIGH_RISK_TOOLS = frozenset({
    "Bash",
    "Edit",
    "Write",
    "NotebookEdit",
    "MultiEdit",
})

# Cursor agent names from https://cursor.com/docs/hooks (not exercised in this VM).
CURSOR_HIGH_RISK_TOOLS = frozenset({
    "Shell",
    "Write",
    "Delete",
})


def mcp_annotations_need_approval(annotations: dict | None) -> bool:
    """Same rule as ``mcp_tool_needs_approval``, without the global registry.

    Omitted annotations follow MCP defaults: readOnlyHint false, destructiveHint true.
    Opt out with readOnlyHint true or destructiveHint false.
    """
    ann = annotations or {}
    if ann.get("readOnlyHint") is True:
        return False
    return ann.get("destructiveHint", True) is not False


def needs_approval(
    name: str,
    annotations: dict | None = None,
    *,
    known_mcp: bool = False,
) -> bool:
    """True when the gateway/hook must create or match an ApprovalQueue row."""
    if not name:
        return False
    if name in _high_risk_names() or name in HIGH_RISK_TOOLS:
        return True
    if name in CLAUDE_HIGH_RISK_TOOLS or name in CURSOR_HIGH_RISK_TOOLS:
        return True
    if known_mcp:
        return mcp_annotations_need_approval(annotations)
    return False
