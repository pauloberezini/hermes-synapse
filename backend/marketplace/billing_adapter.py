"""
Marketplace Pluggable Billing Adapter Engine (Phase 5 - Monetization & Billing)

Provides abstract billing interfaces and adapters:
- NoOpBillingAdapter: Open-source free mode (default, 0 vendor lock-in)
"""

import abc
import os
import logging
from typing import Any, Dict, Optional
try:
    import stripe
except ImportError:
    stripe = None
from backend.database import _execute, db_get_skill_owner, db_get_developer_stripe_account

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


class StripeBillingAdapter(BaseBillingAdapter):
    def __init__(self):
        if stripe is None:
            raise ImportError("Stripe is not installed. Run `pip install stripe` to use StripeBillingAdapter.")
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")

    async def check_entitlement(self, user_id: str, skill_id: str) -> bool:
        # If it's a free skill, always true
        rows = _execute("SELECT price_type FROM marketplace_skills WHERE id = ?", (skill_id,))
        if rows and rows[0][0] == 'free':
            return True
        # Check ledger
        purchase = _execute(
            "SELECT id FROM marketplace_ledger WHERE user_id = ? AND skill_id = ? AND transaction_type = 'purchase'",
            (user_id, skill_id)
        )
        return len(purchase) > 0

    async def record_usage_charge(self, user_id: str, skill_id: str, amount_usd: float) -> Dict[str, Any]:
        # Typically use Stripe metered billing, but for simple MVP just record
        _execute("""
            INSERT INTO marketplace_ledger (user_id, skill_id, amount_usd, transaction_type, provider, reference_id)
            VALUES (?, ?, ?, 'usage', 'stripe', 'pending')
        """, (user_id, skill_id, amount_usd))
        return {"status": "success", "provider": "stripe", "charged_usd": amount_usd}

    async def create_checkout_session(self, user_id: str, skill_id: str, redirect_url: str) -> Dict[str, Any]:
        # Get skill details
        rows = _execute("SELECT id, display_name, price_usd, author FROM marketplace_skills WHERE id = ?", (skill_id,))
        if not rows:
            raise ValueError("Skill not found")
        skill = {
            'id': rows[0][0],
            'display_name': rows[0][1],
            'price_usd': rows[0][2],
            'author': rows[0][3]
        }
        if skill['price_usd'] <= 0:
            return await NoOpBillingAdapter().create_checkout_session(user_id, skill_id, redirect_url)

        owner = skill['author']
        stripe_account_id = db_get_developer_stripe_account(owner)
        if not stripe_account_id:
            raise ValueError("Skill author has not configured Stripe payouts")

        # Create Stripe Checkout Session
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price_data': {
                    'currency': 'usd',
                    'unit_amount': int(skill['price_usd'] * 100),
                    'product_data': {
                        'name': skill['display_name'],
                        'description': f"Lifetime access to {skill['display_name']} skill on Hermes Marketplace",
                    },
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=redirect_url + "?checkout=success&skill_id=" + skill_id,
            cancel_url=redirect_url + "?checkout=canceled",
            payment_intent_data={
                'application_fee_amount': int(skill['price_usd'] * 100 * 0.1), # 10% platform fee
                'transfer_data': {
                    'destination': stripe_account_id,
                },
            },
            client_reference_id=f"{user_id}::{skill_id}",
        )
        return {
            "status": "success",
            "provider": "stripe",
            "checkout_url": session.url
        }


def get_billing_adapter() -> BaseBillingAdapter:
    """Factory function returning active BillingAdapter based on environment configuration."""
    if os.environ.get("STRIPE_SECRET_KEY") and stripe is not None:
        return StripeBillingAdapter()
    return NoOpBillingAdapter()
