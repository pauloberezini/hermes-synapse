"""Spike: Hermes as a gateway in front of external coding agents.

Not the full Phase 4 HTTP gateway. This package is a 1-day prototype:
stdio MCP proxy + Claude Code PreToolUse hook, both routing through
``gate_tool`` / ``ApprovalQueue`` / the hash-chained decision log.
"""

from backend.gateway.classify import (
    CLAUDE_HIGH_RISK_TOOLS,
    CURSOR_HIGH_RISK_TOOLS,
    mcp_annotations_need_approval,
    needs_approval,
)
from backend.gateway.decide import GateDecision, decide, settings_from_env

__all__ = [
    "CLAUDE_HIGH_RISK_TOOLS",
    "CURSOR_HIGH_RISK_TOOLS",
    "GateDecision",
    "decide",
    "mcp_annotations_need_approval",
    "needs_approval",
    "settings_from_env",
]
