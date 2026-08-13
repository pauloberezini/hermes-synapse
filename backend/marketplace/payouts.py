import os
import logging
from typing import Dict, Any, List
from backend.database import _execute

logger = logging.getLogger(__name__)

class PayoutEngine:
    def __init__(self, platform_fee_percent: float = 0.15):
        self.platform_fee_percent = platform_fee_percent

    async def get_developer_earnings(self, developer_id: str) -> Dict[str, Any]:
        """
        Calculate total earnings for a developer across all their skills.
        """
        # Find all skills authored by this developer
        skills = _execute(
            "SELECT id FROM marketplace_skills WHERE author = ?", 
            (developer_id,)
        )
        
        if not skills:
            return {"developer_id": developer_id, "total_earnings_usd": 0.0, "skills_breakdown": []}
            
        # Handle dict or tuple row from _execute
        skill_ids = [s["id"] if isinstance(s, dict) else s[0] for s in skills]
        placeholders = ",".join(["?"] * len(skill_ids))
        
        # Query ledger for these skills (transaction_type = 'payment')
        ledger_entries = _execute(
            f"SELECT skill_id, SUM(amount_usd) as gross_revenue FROM marketplace_ledger WHERE skill_id IN ({placeholders}) AND transaction_type = 'payment' GROUP BY skill_id",
            (*skill_ids,)
        )
        
        total_earnings = 0.0
        breakdown = []
        for entry in ledger_entries:
            skill_id = entry["skill_id"] if isinstance(entry, dict) else entry[0]
            gross = entry["gross_revenue"] if isinstance(entry, dict) else entry[1]
            gross = gross or 0.0
            net = gross * (1.0 - self.platform_fee_percent)
            total_earnings += net
            breakdown.append({
                "skill_id": skill_id,
                "gross_revenue": gross,
                "net_earnings": round(net, 2)
            })
            
        return {
            "developer_id": developer_id,
            "total_earnings_usd": round(total_earnings, 2),
            "platform_fee_percent": self.platform_fee_percent,
            "skills_breakdown": breakdown
        }

    async def get_billing_usage(self, user_id: str) -> Dict[str, Any]:
        """
        Calculate total amount spent by a user.
        """
        # Query ledger for these skills (transaction_type = 'payment')
        ledger_entries = _execute(
            "SELECT skill_id, SUM(amount_usd) as total_spent FROM marketplace_ledger WHERE user_id = ? AND transaction_type = 'payment' GROUP BY skill_id",
            (user_id,)
        )
        
        total_spent = 0.0
        breakdown = []
        for entry in ledger_entries:
            skill_id = entry["skill_id"] if isinstance(entry, dict) else entry[0]
            spent = entry["total_spent"] if isinstance(entry, dict) else entry[1]
            spent = spent or 0.0
            total_spent += spent
            breakdown.append({
                "skill_id": skill_id,
                "total_spent_usd": round(spent, 2)
            })
            
        return {
            "user_id": user_id,
            "total_spent_usd": round(total_spent, 2),
            "skills_breakdown": breakdown
        }

payout_engine = PayoutEngine()
