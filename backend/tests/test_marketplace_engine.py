"""
Comprehensive Unit Tests for Stage 19: Skills Marketplace Monetization & Billing Engine

Tests all 5 phases:
- Phase 1 & 2: Persistent registry, 1-click installation & config lifecycle
- Phase 3: Usage telemetry & metering accounting engine
- Phase 4: Remote registry sync & SHA256 checksum verification
- Phase 5: Pluggable BillingAdapter engine (NoOp) and REST API endpoints
"""

import hashlib
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.auth import create_session
from backend.marketplace.lifecycle import LifecycleManager, MarketplaceSkillManifest
from backend.marketplace.metering import MeteringEngine
from backend.marketplace.registry_sync import RegistrySyncManager
from backend.marketplace.billing_adapter import (
    NoOpBillingAdapter,
    get_billing_adapter,
)

client = TestClient(app)


def test_marketplace_lifecycle_and_persistence():
    """Test Phase 1 & 2: Skill manifest upsert, list, install, uninstall, and config."""
    manifest = MarketplaceSkillManifest(
        id="test_analytics_skill",
        name="test_analytics_skill",
        display_name="Test Analytics Skill",
        description="Analyzes telemetry data",
        author="unit_test",
        version="1.0.0",
        category="analytics",
        tools=["analyze_data", "plot_chart"],
        price_type="free",
        price_usd=0.0
    )
    
    # 1. Upsert
    saved = LifecycleManager.upsert_skill(manifest)
    assert saved["id"] == "test_analytics_skill"
    assert saved["display_name"] == "Test Analytics Skill"
    assert "analyze_data" in saved["tools"]

    # 2. List
    all_skills = LifecycleManager.list_skills()
    assert any(s["id"] == "test_analytics_skill" for s in all_skills)

    # 3. Install
    installed = LifecycleManager.install_skill("test_analytics_skill")
    assert installed["is_installed"] is True

    # 4. Save Config
    cfg_res = LifecycleManager.save_skill_config("test_analytics_skill", {"API_KEY": "secret_123"})
    assert cfg_res["status"] == "success"

    # 5. Uninstall
    uninstalled = LifecycleManager.uninstall_skill("test_analytics_skill")
    assert uninstalled["is_installed"] is False


def test_marketplace_metering_engine():
    """Test Phase 3: Usage telemetry recording, statistics, and quota checks."""
    skill_id = "test_metered_skill"
    
    # Record usage points
    MeteringEngine.record_usage(skill_id=skill_id, subagent_id="agent_alpha", execution_time_ms=120, tokens_used=50)
    MeteringEngine.record_usage(skill_id=skill_id, subagent_id="agent_beta", execution_time_ms=180, tokens_used=150)

    stats = MeteringEngine.get_skill_stats(skill_id)
    assert stats["skill_id"] == skill_id
    assert stats["total_calls"] >= 2
    assert stats["total_tokens"] >= 200

    assert MeteringEngine.check_quota(skill_id, daily_limit=1000) is True


def test_marketplace_registry_sync_checksum():
    """Test Phase 4: Package SHA256 verification and remote sync."""
    content = b"print('hello world')"
    expected_hash = hashlib.sha256(content).hexdigest()
    
    valid = RegistrySyncManager.verify_package_checksum(content, expected_hash)
    assert valid is True

    invalid = RegistrySyncManager.verify_package_checksum(content, "wrong_hash")
    assert invalid is False

    synced = RegistrySyncManager.sync_remote_manifest({
        "id": "remote_synced_skill",
        "name": "remote_synced_skill",
        "display_name": "Remote Synced Skill",
        "tools": ["remote_tool"]
    })
    assert synced["id"] == "remote_synced_skill"


@pytest.mark.asyncio
async def test_billing_adapters():
    """Test Phase 5: BillingAdapters (NoOp)."""
    # 1. NoOp Adapter (Free default)
    noop = NoOpBillingAdapter()
    assert await noop.check_entitlement("user1", "skill1") is True
    charge_res = await noop.record_usage_charge("user1", "skill1", 0.0)
    assert charge_res["provider"] == "noop"
    
    checkout_res = await noop.create_checkout_session("user1", "skill1", "http://localhost")
    assert checkout_res["status"] == "success"

    # 2. Factory default
    default_adapter = get_billing_adapter()
    assert isinstance(default_adapter, NoOpBillingAdapter)


def test_marketplace_api_endpoints():
    """Test FastAPI REST endpoints for marketplace, install, telemetry, and checkout."""
    token = create_session()
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Get skills list
    r = client.get("/api/marketplace/skills", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "success"

    # 2. Register skill
    reg_r = client.post("/api/marketplace/register", json={
        "name": "api_test_skill",
        "display_name": "API Test Skill",
        "description": "Registered via test API",
        "tools": ["api_tool"],
        "price_type": "free",
        "price_usd": 0.0
    }, headers=headers)
    assert reg_r.status_code == 200

    # 3. Install skill via API
    inst_r = client.post("/api/marketplace/skills/api_test_skill/install", headers=headers)
    assert inst_r.status_code == 200

    # 4. Get telemetry via API
    tel_r = client.get("/api/marketplace/skills/api_test_skill/telemetry", headers=headers)
    assert tel_r.status_code == 200

    # 5. Billing checkout via API
    chk_r = client.post("/api/marketplace/skills/api_test_skill/checkout", headers=headers)
    assert chk_r.status_code == 200

    # 6. Billing provider info
    prov_r = client.get("/api/marketplace/billing/provider", headers=headers)
    assert prov_r.status_code == 200
    assert prov_r.json()["provider"] == "NoOpBillingAdapter"

    # 7. Developer earnings API
    earn_r = client.get("/api/marketplace/developer/DeFi_Quant_99/earnings", headers=headers)
    assert earn_r.status_code == 200
    assert "total_earnings_usd" in earn_r.json()["data"]

    # 8. Billing usage API
    usage_r = client.get("/api/marketplace/billing/usage", headers=headers)
    assert usage_r.status_code == 200
    assert "total_spent_usd" in usage_r.json()["data"]

@pytest.mark.asyncio
async def test_marketplace_payout_engine():
    """Test Phase 5: Payouts & Developer earnings logic (Cross test)."""
    from backend.marketplace.payouts import payout_engine
    from backend.database import _execute
    
    # 1. Upsert a mock skill for testing payouts
    _execute(
        "INSERT INTO marketplace_skills (id, name, display_name, author, price_usd) VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO NOTHING",
        ("test_paid_skill", "test_paid_skill", "Test Paid Skill", "test_dev_1", 10.0)
    )
    
    # 2. Insert mock ledger payments
    _execute(
        "INSERT INTO marketplace_ledger (user_id, skill_id, amount_usd, transaction_type, provider) VALUES (?, ?, ?, ?, ?)",
        ("test_user_1", "test_paid_skill", 10.0, "payment", "stripe")
    )
    _execute(
        "INSERT INTO marketplace_ledger (user_id, skill_id, amount_usd, transaction_type, provider) VALUES (?, ?, ?, ?, ?)",
        ("test_user_1", "test_paid_skill", 10.0, "payment", "stripe")
    )
    
    # 3. Test Developer Earnings (15% platform fee)
    earnings = await payout_engine.get_developer_earnings("test_dev_1")
    assert earnings["total_earnings_usd"] == 17.0  # 20.0 * 0.85
    assert len(earnings["skills_breakdown"]) >= 1
    assert earnings["skills_breakdown"][0]["gross_revenue"] == 20.0
    assert earnings["skills_breakdown"][0]["net_earnings"] == 17.0
    
    # 4. Test User Billing Usage
    usage = await payout_engine.get_billing_usage("test_user_1")
    assert usage["total_spent_usd"] == 20.0
    assert len(usage["skills_breakdown"]) >= 1
    assert usage["skills_breakdown"][0]["total_spent_usd"] == 20.0
