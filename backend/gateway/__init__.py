"""Hermes gateway: stdio MCP proxy + coding-agent hook around ApprovalQueue."""

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
