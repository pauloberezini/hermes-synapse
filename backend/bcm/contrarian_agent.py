"""
backend/bcm/contrarian_agent.py — Contrarian Logic Agent (Devil's Advocate)

Role: Evaluates the proposed trade hypothesis from the ConfluenceEngine and
attempts to invalidate it using strict contrarian logic (e.g., detecting trap
patterns, divergence anomalies, or extreme volatility without structure).

Features strict "no fallback" logic: any failure or ambiguity results in a VETO.
"""

import logging
from typing import Dict, Any

logger = logging.getLogger("hermes.bcm.contrarian")

class ContrarianAgent:
    """
    Acts as the 'Devil's Advocate' to cross-validate trade signals.
    """

    def __init__(self):
        # Strict thresholds for contrarian veto
        self.max_allowed_divergence = 0.8
        self.trap_momentum_threshold = 0.6
        self.chop_wyckoff_threshold = 0.2

    def evaluate_hypothesis(
        self,
        component_scores: Dict[str, float],
        proposed_decision: str,
        raw_confluence: float
    ) -> Dict[str, Any]:
        """
        Evaluates the hypothesis. Returns a dict containing 'veto' boolean
        and 'reasons' list.
        """
        # NO FALLBACK: If proposed_decision is HOLD_SKIP, we immediately agree
        # (no need to veto a non-trade).
        if proposed_decision == "HOLD_SKIP":
            return {
                "veto": False,
                "reasons": ["No trade proposed. Agree with HOLD."]
            }

        veto_reasons = []

        try:
            wyckoff = component_scores.get("wyckoff_structure", 0.0)
            momentum = component_scores.get("momentum", 0.0)
            vwap = component_scores.get("vwap_position", 0.0)
            odf = component_scores.get("odf_volatility", 0.0)

            # 1. Divergence Trap Detection
            # If momentum is very high but wyckoff structure is poor/choppy
            if abs(momentum) > self.trap_momentum_threshold and abs(wyckoff) < self.chop_wyckoff_threshold:
                veto_reasons.append("Contrarian Veto: Momentum trap detected. High momentum without supporting market structure.")

            # 2. Extreme Volatility vs Trend
            # If orderflow volatility is extreme but VWAP isn't trending
            if abs(odf) > 0.8 and abs(vwap) < 0.3:
                veto_reasons.append("Contrarian Veto: Volatility anomaly. High ODF spike in sideways VWAP band.")

            # 3. Contrarian Alignment Check
            # If proposed decision is STRONG_BUY, but wyckoff is negative
            if "BUY" in proposed_decision and wyckoff < -0.1:
                veto_reasons.append("Contrarian Veto: Buying against bearish Wyckoff structure.")

            if "SELL" in proposed_decision and wyckoff > 0.1:
                veto_reasons.append("Contrarian Veto: Selling against bullish Wyckoff structure.")

            # Strict fail-safe: if there are any reasons to veto, we veto.
            veto_applied = len(veto_reasons) > 0

            return {
                "veto": veto_applied,
                "reasons": veto_reasons
            }

        except Exception as e:
            logger.error(f"ContrarianAgent encountered error during evaluation: {e}")
            # STRICT NO-FALLBACK: Any exception defaults to a VETO.
            return {
                "veto": True,
                "reasons": [f"System Exception in Contrarian Evaluation: {str(e)} - STRICT VETO APPLIED."]
            }
