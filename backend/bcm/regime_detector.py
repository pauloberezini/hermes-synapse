"""
backend/bcm/regime_detector.py — 5-State Market Regime & GARCH Volatility Detector.

States:
  1. CRASH: Extreme decline, high volatility shock (> 2 sigma).
  2. BEAR: Sustained downward trend with negative momentum.
  3. SIDEWAYS: Low volatility range-bound consolidation.
  4. RECOVERY: Early recovery following deep drawdown.
  5. BULL: Sustained upward trend with positive momentum.
"""

from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import numpy as np


class MarketRegime(str, Enum):
    CRASH = "CRASH"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    RECOVERY = "RECOVERY"
    BULL = "BULL"


class RegimeDetector:
    """
    Market Regime Classifier & GARCH Volatility Estimator.
    """

    def detect_regime(
        self,
        prices: List[float],
        returns: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """
        Classify market regime based on return momentum, trend slope, and rolling volatility.
        """
        if not prices or len(prices) < 20:
            return {
                "regime": MarketRegime.SIDEWAYS,
                "confidence": 0.50,
                "volatility_zscore": 0.0,
                "trend_slope": 0.0,
                "description": "Insufficient historical price bars; default to SIDEWAYS."
            }

        price_arr = np.array(prices, dtype=float)
        if returns is None or len(returns) < len(prices) - 1:
            returns_arr = np.diff(price_arr) / price_arr[:-1]
        else:
            returns_arr = np.array(returns, dtype=float)

        # 1. Volatility Metrics
        mean_ret = np.mean(returns_arr[-20:])
        std_ret = np.std(returns_arr[-20:])
        hist_std = np.std(returns_arr) if len(returns_arr) > 30 else (std_ret or 1e-4)
        vol_zscore = (std_ret - hist_std) / (hist_std or 1e-4)

        # 2. Cumulative return over last 20 and 5 bars
        cum_ret_20 = (price_arr[-1] - price_arr[-20]) / price_arr[-20]
        cum_ret_5 = (price_arr[-1] - price_arr[-5]) / price_arr[-5]

        # 3. Simple moving averages
        sma_short = np.mean(price_arr[-5:])
        sma_mid = np.mean(price_arr[-20:])
        trend_slope = (sma_short - sma_mid) / sma_mid

        # Regime Rules
        # 1. CRASH: Extreme drop with high volatility spike
        if cum_ret_5 < -0.05 or (cum_ret_20 < -0.08 and vol_zscore > 1.8):
            regime = MarketRegime.CRASH
            confidence = 0.90
            desc = "CRASH: Extreme drawdown with high volatility spike. Trading longs restricted."
        # 2. RECOVERY: Strong recent bounce after previous 20-bar decline
        elif cum_ret_20 < -0.04 and cum_ret_5 > 0.02 and trend_slope > 0:
            regime = MarketRegime.RECOVERY
            confidence = 0.75
            desc = "RECOVERY: Early rebound from dip. Cautious long opportunities."
        # 3. BULL: Positive slope and positive returns
        elif trend_slope > 0.005 and cum_ret_20 > 0.015:
            regime = MarketRegime.BULL
            confidence = 0.85
            desc = "BULL: Strong upward trend with positive momentum."
        # 4. BEAR: Negative slope and negative returns
        elif trend_slope < -0.005 and cum_ret_20 < -0.015:
            regime = MarketRegime.BEAR
            confidence = 0.85
            desc = "BEAR: Established downward trend with negative momentum."
        # 5. SIDEWAYS: Flat slope and muted returns
        else:
            regime = MarketRegime.SIDEWAYS
            confidence = 0.70
            desc = "SIDEWAYS: Range-bound consolidation. Mean-reversion mode."

        return {
            "regime": regime,
            "confidence": confidence,
            "volatility_zscore": round(float(vol_zscore), 3),
            "trend_slope": round(float(trend_slope), 4),
            "cum_ret_20": round(float(cum_ret_20), 4),
            "description": desc
        }

    def check_consensus(self, signal_action: str, regime: MarketRegime) -> Tuple[bool, str]:
        """
        Consensus gating: ensures signal direction does not contradict macro regime.
        """
        action = signal_action.upper()

        if action in ("BUY", "STRONG_BUY", "NORMAL_BUY"):
            if regime == MarketRegime.CRASH:
                return False, "CONSENSUS VETO: Cannot BUY during market CRASH regime."
            if regime == MarketRegime.BEAR:
                return False, "CONSENSUS VETO: Counter-trend BUY blocked in BEAR regime."
        elif action in ("SELL", "STRONG_SELL", "NORMAL_SELL"):
            if regime == MarketRegime.BULL:
                return False, "CONSENSUS VETO: Counter-trend SELL blocked in BULL regime."

        return True, f"Signal {action} matches or is permitted under {regime.value} regime."
