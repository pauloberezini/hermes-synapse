"""
Marketplace Pluggable Billing Adapter Engine (Phase 5 - Monetization & Billing)

Provides abstract billing interfaces and adapters:
- NoOpBillingAdapter: Open-source free mode (default, 0 vendor lock-in)
"""

import abc
import os
import logging
from typing import Any, Dict, Optional
from backend.database import _execute

logger = logging.getLogger(__name__)


class BaseBillingAdapter(abc.ABC):
    """Abstract base class for marketplace billing providers."""

    @abc.abstractmethod
    async def check_entitlement(self, user_id: str, skill_id: str) -> bool:
        """Check if user is entitled to execute a paid skill."""
        pass

    @abc.abstractmethod
    async def record_usage_charge(self, user_id: str, skill_id: str, amount_usd: float) -> Dict[str, Any]:
        """Record usage charge transaction in billing ledger."""
        pass

    @abc.abstractmethod
    async def create_checkout_session(self, user_id: str, skill_id: str, redirect_url: str) -> Dict[str, Any]:
        """Generate checkout URL or payment request for skill access."""
        pass


class NoOpBillingAdapter(BaseBillingAdapter):
    """Default Open-Source Billing Adapter (100% free mode, zero vendor lock-in)."""

    async def check_entitlement(self, user_id: str, skill_id: str) -> bool:
        return True

    async def record_usage_charge(self, user_id: str, skill_id: str, amount_usd: float) -> Dict[str, Any]:
        _execute("""
            INSERT INTO marketplace_ledger (user_id, skill_id, amount_usd, transaction_type, provider, reference_id)
            VALUES (?, ?, ?, 'free_grant', 'noop', 'free_tier')
        """, (user_id, skill_id, amount_usd))
        return {"status": "success", "provider": "noop", "charged_usd": 0.0}

    async def create_checkout_session(self, user_id: str, skill_id: str, redirect_url: str) -> Dict[str, Any]:
        return {
            "status": "success",
            "provider": "noop",
            "checkout_url": redirect_url,
            "message": "Skill is free. No payment required."
        }


def get_billing_adapter() -> BaseBillingAdapter:
    """Factory function returning active BillingAdapter based on environment configuration."""
    return NoOpBillingAdapter()
