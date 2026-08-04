try:
    import pytest
except ImportError:
    pytest = None

import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

try:
    from backend.bcm.compliance_officer import ComplianceOfficer
    HAS_BCM = True
except ModuleNotFoundError:
    try:
        from bcm.compliance_officer import ComplianceOfficer
        HAS_BCM = True
    except ModuleNotFoundError:
        ComplianceOfficer = None
        HAS_BCM = False

if pytest and not HAS_BCM:
    pytestmark = pytest.mark.skipif(True, reason="BCM module is a private component ignored in git")


def test_compliance_hard_limits_approved():
    officer = ComplianceOfficer()
    
    # Valid buy trade with SL below entry and TP above entry
    passed, reason = officer.check_hard_limits(
        symbol="BTC",
        action="buy",
        volume=1,
        base_volume=1,
        sl=60000,
        tp=70000,
        entry_price=65000
    )
    assert passed is True
    assert "Hard limits passed" in reason


def test_compliance_hard_limits_unapproved_symbol():
    officer = ComplianceOfficer()
    
    passed, reason = officer.check_hard_limits(
        symbol="UNAPPROVED_TOKEN",
        action="buy",
        volume=1,
        base_volume=1,
        sl=10,
        tp=20,
        entry_price=15
    )
    assert passed is False
    assert "not on the approved list" in reason


def test_compliance_hard_limits_missing_sl_tp():
    officer = ComplianceOfficer()
    
    passed, reason = officer.check_hard_limits(
        symbol="BTC",
        action="buy",
        volume=1,
        base_volume=1,
        sl=None,
        tp=70000,
        entry_price=65000
    )
    assert passed is False
    assert "Stop Loss and Take Profit" in reason


def test_compliance_hard_limits_invalid_sl_direction():
    officer = ComplianceOfficer()
    
    # Buy order with SL above entry price (invalid)
    passed, reason = officer.check_hard_limits(
        symbol="BTC",
        action="buy",
        volume=1,
        base_volume=1,
        sl=68000,
        tp=70000,
        entry_price=65000
    )
    assert passed is False
    assert "Buy order SL must be below entry price" in reason


def test_compliance_audit_trade_wait_action():
    officer = ComplianceOfficer()
    
    passed, reason = officer.audit_trade(
        symbol="BTC",
        action="wait",
        volume=1,
        base_volume=1,
        sl=None,
        tp=None,
        entry_price=65000,
        md_decision="Wait for clearer signal",
        risk_report="Low risk"
    )
    assert passed is True
    assert "Action is WAIT" in reason


if __name__ == "__main__":
    print("🚀 Running Compliance Engine Unit Tests...")
    test_compliance_hard_limits_approved()
    print("  ✅ test_compliance_hard_limits_approved: PASSED")
    test_compliance_hard_limits_unapproved_symbol()
    print("  ✅ test_compliance_hard_limits_unapproved_symbol: PASSED")
    test_compliance_hard_limits_missing_sl_tp()
    print("  ✅ test_compliance_hard_limits_missing_sl_tp: PASSED")
    test_compliance_hard_limits_invalid_sl_direction()
    print("  ✅ test_compliance_hard_limits_invalid_sl_direction: PASSED")
    test_compliance_audit_trade_wait_action()
    print("  ✅ test_compliance_audit_trade_wait_action: PASSED")
    print("\n🎉 ALL COMPLIANCE ENGINE TESTS PASSED SUCCESSFULLY!")
