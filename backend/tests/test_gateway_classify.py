from backend.gateway.classify import (
    CLAUDE_HIGH_RISK_TOOLS,
    mcp_annotations_need_approval,
    needs_approval,
)
from backend.governance import HIGH_RISK_TOOLS


def test_high_risk_tools_are_gated():
    for name in ("execute_command", "execute_code", "clear_decision_logs"):
        assert name in HIGH_RISK_TOOLS
        assert needs_approval(name) is True


def test_claude_builtins_are_gated_even_when_not_mcp():
    assert "Bash" not in HIGH_RISK_TOOLS
    for name in CLAUDE_HIGH_RISK_TOOLS:
        assert needs_approval(name) is True
    assert needs_approval("Read") is False
    assert needs_approval("Grep") is False


def test_mcp_annotation_defaults_and_opt_out():
    assert mcp_annotations_need_approval(None) is True
    assert mcp_annotations_need_approval({}) is True
    assert mcp_annotations_need_approval({"readOnlyHint": True}) is False
    assert mcp_annotations_need_approval({"destructiveHint": False}) is False
    assert mcp_annotations_need_approval({"readOnlyHint": False}) is True


def test_known_mcp_uses_annotations_unknown_name_is_not_gated():
    assert needs_approval("search", {"readOnlyHint": True}, known_mcp=True) is False
    assert needs_approval("search", {}, known_mcp=True) is True
    assert needs_approval("search", {}, known_mcp=False) is False
