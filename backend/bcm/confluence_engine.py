"""
backend/bcm/confluence_engine.py — Multi-Signal Confluence Engine with Veto Power.

Combines 8 weighted signals across BCM indicators:
  1. Weis-Wyckoff Wave / Market Structure (weight: 1.5x) -> Structural VETO
  2. Remizov Shift / Trend Breakout (weight: 1.2x)
  3. Multi-VWAP Sigma Bands (weight: 1.0x)
  4. Volume Profile Value Area / POC (weight: 1.0x)
  5. EMA Trend Alignment 20/50/100 (weight: 1.0x)
  6. Momentum Oscillators (RSI + MACD) (weight: 0.8x)
  7. ODF Spikes / Bubbles / Volatility (weight: 0.5x)
  8. Options GEX & Dealer Flow (weight: 0.6x)
"""

from typing import Dict, Any, Optional, Tuple


class ConfluenceDecision:
    STRONG_BUY = "STRONG_BUY"
    NORMAL_BUY = "NORMAL_BUY"
    HOLD_SKIP = "HOLD_SKIP"
    NORMAL_SELL = "NORMAL_SELL"
    STRONG_SELL = "STRONG_SELL"


class ConfluenceEngine:
    """
    Weighted Confluence Scoring Engine with Structural Veto Power.
    """

    WEIGHTS = {
        "wyckoff_structure": 1.5,
        "remizov_shift": 1.2,
        "vwap_position": 1.0,
        "volume_profile": 1.0,
        "ema_trend": 1.0,
        "momentum": 0.8,
        "odf_volatility": 0.5,
        "gex_options": 0.6,
    }

    STRONG_THRESHOLD = 0.60
    NORMAL_THRESHOLD = 0.30

    def compute_confluence(
        self,
        wyckoff_score: float = 0.0,      # -1.0 (markdown/bear) to +1.0 (accumulation/bull)
        remizov_score: float = 0.0,      # -1.0 to +1.0
        vwap_score: float = 0.0,         # -1.0 (below -2sigma/downtrend) to +1.0 (above +2sigma/bounce)
        volume_profile_score: float = 0.0,# -1.0 (below VAH rejection) to +1.0 (above VAL acceptance)
        ema_score: float = 0.0,          # -1.0 (death cross) to +1.0 (golden cross)
        momentum_score: float = 0.0,     # -1.0 (RSI < 40 + MACD bear) to +1.0 (RSI > 60 + MACD bull)
        odf_score: float = 0.0,          # -1.0 to +1.0
        gex_score: float = 0.0,          # -1.0 (neg gamma/put wall break) to +1.0 (pos gamma/max pain support)
        is_sideways_regime: bool = False,# True if market is in chop/range-bound
        higher_tf_trend: Optional[str] = None # "BULL", "BEAR", "SIDEWAYS"
    ) -> Dict[str, Any]:
        """
        Compute weighted confluence score and decision.
        """
        scores = {
            "wyckoff_structure": max(-1.0, min(1.0, float(wyckoff_score))),
            "remizov_shift": max(-1.0, min(1.0, float(remizov_score))),
            "vwap_position": max(-1.0, min(1.0, float(vwap_score))),
            "volume_profile": max(-1.0, min(1.0, float(volume_profile_score))),
            "ema_trend": max(-1.0, min(1.0, float(ema_score))),
            "momentum": max(-1.0, min(1.0, float(momentum_score))),
            "odf_volatility": max(-1.0, min(1.0, float(odf_score))),
            "gex_options": max(-1.0, min(1.0, float(gex_score))),
        }

        weighted_sum = sum(self.WEIGHTS[k] * scores[k] for k in self.WEIGHTS)
        total_weight = sum(self.WEIGHTS.values())
        raw_confluence = weighted_sum / total_weight

        # 1. Structural Penalty: Penalize counter-trend trades against Higher Timeframe
        veto_reasons = []
        confluence_score = raw_confluence

        if higher_tf_trend:
            htf_upper = higher_tf_trend.upper()
            if htf_upper == "BEAR" and confluence_score > 0:
                confluence_score -= 0.50
                veto_reasons.append("HTF BEAR Trend: Long signal penalized by 0.50.")
            elif htf_upper == "BULL" and confluence_score < 0:
                confluence_score += 0.50
                veto_reasons.append("HTF BULL Trend: Short signal penalized by 0.50.")

        # 2. Structural VETO: Sideways / Range-bound Chop
        # If market structure is SIDEWAYS, cap maximum absolute confidence at 0.40 (no STRONG signals)
        if is_sideways_regime or abs(wyckoff_score) < 0.20:
            if abs(confluence_score) > 0.40:
                confluence_score = 0.40 if confluence_score > 0 else -0.40
                veto_reasons.append("VETO: Sideways / Chop regime active. Max signal capped at MEDIUM (0.40).")

        # Bound final score to [-1.0, 1.0]
        confluence_score = max(-1.0, min(1.0, confluence_score))

        # 3. Decision Classification
        if confluence_score >= self.STRONG_THRESHOLD:
            decision = ConfluenceDecision.STRONG_BUY
            recommended_rr = "1:3.0"
            risk_multiplier = 1.0
        elif self.NORMAL_THRESHOLD <= confluence_score < self.STRONG_THRESHOLD:
            decision = ConfluenceDecision.NORMAL_BUY
            recommended_rr = "1:2.0"
            risk_multiplier = 0.75
        elif -self.NORMAL_THRESHOLD < confluence_score < self.NORMAL_THRESHOLD:
            decision = ConfluenceDecision.HOLD_SKIP
            recommended_rr = "N/A"
            risk_multiplier = 0.0
        elif -self.STRONG_THRESHOLD < confluence_score <= -self.NORMAL_THRESHOLD:
            decision = ConfluenceDecision.NORMAL_SELL
            recommended_rr = "1:2.0"
            risk_multiplier = 0.75
        else:
            decision = ConfluenceDecision.STRONG_SELL
            recommended_rr = "1:3.0"
            risk_multiplier = 1.0

        return {
            "decision": decision,
            "confluence_score": round(confluence_score, 4),
            "raw_confluence": round(raw_confluence, 4),
            "component_scores": scores,
            "veto_applied": len(veto_reasons) > 0,
            "veto_reasons": veto_reasons,
            "recommended_rr": recommended_rr,
            "risk_multiplier": risk_multiplier,
        }
