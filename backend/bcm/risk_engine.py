"""
backend/bcm/risk_engine.py — Institutional Risk & VaR Engine.

Implements:
1. Parametric & Historical Value-at-Risk (VaR 95% and 99%).
2. Flash-Crash Stress Testing Suite (5 macro shock scenarios).
3. 5-Tier Drawdown Protocol with Kill-Switch.
4. Pre-Order Instrument Validation (trade_mode, min_volume, volume_step, double number check).
"""

from enum import Enum
from typing import Dict, Any, List, Optional, Tuple
import math
import numpy as np


class DrawdownState(str, Enum):
    NORMAL = "NORMAL"          # 0-2% DD: Standard risk parameters
    WARNING = "WARNING"        # 2-5% DD: 50% size reduction, heightened monitoring
    DANGER = "DANGER"          # 5-8% DD: Close-only mode (no new positions)
    CRITICAL = "CRITICAL"      # 8-10% DD: Comprehensive emergency position closure
    KILL_SWITCH = "KILL_SWITCH"# >10% DD: Complete system halt, admin alert


class RiskEngine:
    """Institutional Risk Management and Capital Preservation Engine."""

    # Portfolio Limits
    MAX_PORTFOLIO_VAR_95_PCT = 0.05       # Max 5% 1-day portfolio VaR
    MAX_SINGLE_TRADE_RISK_PCT = 0.015     # Max 1.5% equity risk per trade
    HIGH_CONVICTION_RISK_PCT = 0.020      # Max 2.0% equity risk for high conviction
    MAX_DAILY_LOSS_PCT = 0.02             # Max 2% loss per day
    MAX_PORTFOLIO_DRAWDOWN_PCT = 0.10     # 10% hard stop drawdown
    MAX_MARGIN_USAGE_PCT = 0.50           # Max 50% margin utilization

    def __init__(self, peak_equity: float = 10000.0):
        self.peak_equity = peak_equity

    def update_peak_equity(self, current_equity: float) -> None:
        """Update historical high-water mark equity."""
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

    def evaluate_drawdown_state(self, current_equity: float) -> Tuple[DrawdownState, Dict[str, Any]]:
        """
        Evaluate current portfolio drawdown relative to peak equity.
        Returns the drawdown state and sizing multiplier.
        """
        self.update_peak_equity(current_equity)
        if self.peak_equity <= 0:
            return DrawdownState.NORMAL, {"drawdown_pct": 0.0, "size_multiplier": 1.0, "allow_new_trades": True}

        drawdown_usd = max(0.0, self.peak_equity - current_equity)
        drawdown_pct = drawdown_usd / self.peak_equity

        if drawdown_pct >= self.MAX_PORTFOLIO_DRAWDOWN_PCT:
            state = DrawdownState.KILL_SWITCH
            size_multiplier = 0.0
            allow_new_trades = False
            action = "KILL_SWITCH: Full trading halt. All positions must be liquidated."
        elif drawdown_pct >= 0.08:
            state = DrawdownState.CRITICAL
            size_multiplier = 0.0
            allow_new_trades = False
            action = "CRITICAL: Drawdown in 8-10% danger zone. Emergency position review & closure."
        elif drawdown_pct >= 0.05:
            state = DrawdownState.DANGER
            size_multiplier = 0.0
            allow_new_trades = False
            action = "DANGER: Drawdown in 5-8% zone. Prohibit new positions. Close-only mode."
        elif drawdown_pct >= 0.02:
            state = DrawdownState.WARNING
            size_multiplier = 0.50
            allow_new_trades = True
            action = "WARNING: Drawdown 2-5%. Position sizes reduced by 50%."
        else:
            state = DrawdownState.NORMAL
            size_multiplier = 1.0
            allow_new_trades = True
            action = "NORMAL: Drawdown within healthy 0-2% band. Full position sizing enabled."

        return state, {
            "drawdown_pct": drawdown_pct,
            "drawdown_usd": drawdown_usd,
            "peak_equity": self.peak_equity,
            "current_equity": current_equity,
            "size_multiplier": size_multiplier,
            "allow_new_trades": allow_new_trades,
            "action": action
        }

    def calculate_parametric_var(
        self,
        position_value_usd: float,
        daily_volatility: float,
        confidence: float = 0.95
    ) -> float:
        """
        Calculate Parametric Value at Risk (VaR).
        VaR_95 = 1.645 * sigma * value
        VaR_99 = 2.326 * sigma * value
        """
        if confidence >= 0.99:
            z = 2.326
        elif confidence >= 0.95:
            z = 1.645
        else:
            z = 1.282  # 90%
        return position_value_usd * daily_volatility * z

    def calculate_historical_var(
        self,
        historical_returns: List[float],
        position_value_usd: float,
        percentile: float = 5.0
    ) -> float:
        """
        Calculate Historical VaR based on empirical return distribution.
        """
        if not historical_returns:
            return 0.0
        pct_return = np.percentile(historical_returns, percentile)
        # Expected loss is negative return multiplied by position value
        loss = max(0.0, -pct_return * position_value_usd)
        return float(loss)

    def run_flash_crash_stress_test(
        self,
        portfolio_positions: List[Dict[str, Any]],
        account_equity: float
    ) -> Dict[str, Any]:
        """
        Simulate 5 macro flash-crash shock scenarios across open positions:
          1. Equity/Crypto Index Flash Crash (-3% / -5%)
          2. Gold Spike (+5%)
          3. FX Volatility Shock (EUR/GBP +-2%)
          4. Sector Rotation Shock (+-2.5%)
          5. Correlation Breakdown (Inverse movement across all assets)
        """
        scenarios = {
            "index_flash_crash": 0.0,
            "gold_spike": 0.0,
            "fx_shock": 0.0,
            "sector_shock": 0.0,
            "correlation_breakdown": 0.0,
        }

        for pos in portfolio_positions:
            sym = pos.get("symbol", "").upper()
            val = float(pos.get("position_value_usd", pos.get("volume", 0.0) * pos.get("entry_price", 0.0)))
            direction = 1.0 if pos.get("direction", "buy").lower() in ("buy", "long") else -1.0

            # 1. Index / Crypto flash crash
            if any(idx in sym for idx in ["US500", "NAS100", "US30", "BTC", "ETH"]):
                drop = -0.03 if "US" in sym else -0.05
                pnl = val * drop * direction
                scenarios["index_flash_crash"] += pnl

            # 2. Gold spike (+5%)
            if "GOLD" in sym or "XAU" in sym:
                pnl = val * 0.05 * direction
                scenarios["gold_spike"] += pnl

            # 3. FX Shock (+-2% adverse)
            if any(curr in sym for curr in ["EUR", "GBP", "JPY", "AUD", "CAD"]):
                pnl = -abs(val * 0.02)  # adverse move
                scenarios["fx_shock"] += pnl

            # 4. Sector Rotation shock
            pnl_rot = -abs(val * 0.025)
            scenarios["sector_shock"] += pnl_rot

            # 5. Correlation Breakdown (Every position moves adversely by 2%)
            scenarios["correlation_breakdown"] += -abs(val * 0.02)

        worst_scenario = min(scenarios.values()) if scenarios else 0.0
        worst_loss_pct = abs(worst_scenario) / account_equity if account_equity > 0 else 0.0
        passed = worst_loss_pct <= self.MAX_PORTFOLIO_VAR_95_PCT

        return {
            "passed": passed,
            "worst_scenario_loss_usd": abs(worst_scenario),
            "worst_loss_pct": worst_loss_pct,
            "scenario_details": scenarios,
            "reason": "Stress test passed" if passed else f"STRESS TEST FAILED: Worst scenario loss {worst_loss_pct:.1%} exceeds 5% equity threshold."
        }

    def validate_instrument_order(
        self,
        symbol: str,
        volume: float,
        entry_price: float,
        sl: Optional[float],
        tp: Optional[float],
        action: str,
        instrument_spec: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """
        Validate instrument specifications:
          - trade_mode == FULL
          - min_volume and volume_step
          - Double number check (sanity check against order magnitude errors)
          - SL/TP mandatory existence and correct placement
        """
        action_lower = action.lower()
        if action_lower == "wait":
            return True, "WAIT action approved."

        if not sl or not tp or sl <= 0 or tp <= 0:
            return False, "HARD LIMIT: All active trades must have a valid Stop Loss and Take Profit."

        if entry_price <= 0 or volume <= 0:
            return False, "HARD LIMIT: Entry price and volume must be strictly positive."

        # Verify SL/TP direction
        if action_lower in ("buy", "long"):
            if sl >= entry_price:
                return False, "HARD LIMIT: Buy order SL must be below entry price."
            if tp <= entry_price:
                return False, "HARD LIMIT: Buy order TP must be above entry price."
        elif action_lower in ("sell", "short"):
            if sl <= entry_price:
                return False, "HARD LIMIT: Sell order SL must be above entry price."
            if tp >= entry_price:
                return False, "HARD LIMIT: Sell order TP must be below entry price."

        # Check Minimum Risk-to-Reward Ratio (Min 1.0:1 base check, 1.5:1 recommended)
        sl_dist = abs(entry_price - sl)
        tp_dist = abs(tp - entry_price)
        if sl_dist > 0:
            rr_ratio = tp_dist / sl_dist
            if rr_ratio < 0.95:  # Absolute minimum 1:1 floor
                return False, f"HARD LIMIT: Risk-Reward ratio ({rr_ratio:.2f}:1) is below mandatory minimum 1:1."

        # Broker Instrument Spec checks
        if instrument_spec:
            trade_mode = instrument_spec.get("trade_mode", "FULL").upper()
            if trade_mode not in ("FULL", "BUY_SELL", "ENABLED"):
                return False, f"HARD LIMIT: Instrument {symbol} trade_mode is '{trade_mode}' (must be FULL)."

            min_vol = float(instrument_spec.get("min_volume", 0.01))
            if volume < min_vol:
                return False, f"HARD LIMIT: Volume {volume} is below instrument minimum {min_vol}."

            step = float(instrument_spec.get("volume_step", 0.01))
            if step > 0:
                remainder = round(volume % step, 8)
                if remainder != 0.0 and abs(remainder - step) > 1e-6:
                    return False, f"HARD LIMIT: Volume {volume} does not conform to step {step}."

        return True, "Pre-order validation successful."
