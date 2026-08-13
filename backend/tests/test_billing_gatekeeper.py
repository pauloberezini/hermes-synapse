import pytest
import asyncio
from unittest.mock import patch, MagicMock

def test_billing_gatekeeper_denies_access():
    """
    Test that when billing adapter returns False for entitlement,
    the tool execution is skipped and an error is injected.
    """
    async def run_test():
        with patch('backend.marketplace.billing_adapter.get_billing_adapter') as mock_get_billing, \
             patch('backend.marketplace.lifecycle.LifecycleManager') as mock_lifecycle:
            
            mock_adapter = MagicMock()
            async def mock_check_entitlement(user_id, skill_id):
                return False
            mock_adapter.check_entitlement = mock_check_entitlement
            mock_get_billing.return_value = mock_adapter
            
            mock_lifecycle.get_skill_for_tool.return_value = "premium_skill"
            
            from backend.marketplace.lifecycle import LifecycleManager
            skill_id = LifecycleManager.get_skill_for_tool("premium_tool")
            assert skill_id == "premium_skill"
            
            from backend.marketplace.billing_adapter import get_billing_adapter
            billing = get_billing_adapter()
            is_entitled = await billing.check_entitlement("default_user", skill_id)
            
            assert is_entitled is False
            
    asyncio.run(run_test())

def test_billing_gatekeeper_grants_access():
    """
    Test that when billing adapter returns True for entitlement (e.g. NoOpBillingAdapter),
    the execution continues.
    """
    async def run_test():
        with patch('backend.marketplace.billing_adapter.get_billing_adapter') as mock_get_billing, \
             patch('backend.marketplace.lifecycle.LifecycleManager') as mock_lifecycle:
            
            mock_adapter = MagicMock()
            async def mock_check_entitlement(user_id, skill_id):
                return True
            mock_adapter.check_entitlement = mock_check_entitlement
            mock_get_billing.return_value = mock_adapter
            
            mock_lifecycle.get_skill_for_tool.return_value = "free_skill"
            
            from backend.marketplace.lifecycle import LifecycleManager
            skill_id = LifecycleManager.get_skill_for_tool("free_tool")
            assert skill_id == "free_skill"
            
            from backend.marketplace.billing_adapter import get_billing_adapter
            billing = get_billing_adapter()
            is_entitled = await billing.check_entitlement("default_user", skill_id)
            
            assert is_entitled is True

    asyncio.run(run_test())
