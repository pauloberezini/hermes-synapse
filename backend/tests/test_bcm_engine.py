import pytest

try:
    from backend.bcm.compliance_officer import ComplianceOfficer
    HAS_BCM = True
except ModuleNotFoundError:
    try:
        from bcm.compliance_officer import ComplianceOfficer
        HAS_BCM = True
    except ModuleNotFoundError:
        HAS_BCM = False

pytestmark = pytest.mark.skipif(not HAS_BCM, reason="BCM module is a private component ignored in git")


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
