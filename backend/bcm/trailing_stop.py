"""
backend/bcm/trailing_stop.py — Post-Execution Trailing Stop Engine.

Rules:
  - +1.0R Profit: Move Stop Loss to Break-Even (Entry Price).
  - +2.0R+ Profit: Activate Trailing Stop locking in 50% of the peak profit retracement.
"""

from typing import Dict, Any, Optional, Tuple


class TrailingStopEngine:
    """
    Manages dynamic stop-loss adjustments based on R-multiples of profit.
    """

    @staticmethod
    def evaluate_stop_adjustment(
        direction: str,
        entry_price: float,
        current_price: float,
        initial_sl: float,
        current_sl: float,
        peak_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Evaluate if Stop-Loss needs to be moved to Break-Even or Trailed.

        Parameters:
            direction: 'buy' / 'sell'
            entry_price: Original entry price
            current_price: Live market price
            initial_sl: Original stop loss set at entry
            current_sl: Currently active stop loss on the broker
            peak_price: Highest (for buy) or lowest (for sell) price reached since entry
        """
        is_buy = direction.lower() in ("buy", "long")
        sl_distance = abs(entry_price - initial_sl)

        if sl_distance <= 0 or entry_price <= 0:
            return {"should_update": False, "new_sl": current_sl, "reason": "Invalid entry or SL parameters."}

        # Calculate current profit in R-units
        if is_buy:
            profit_points = current_price - entry_price
            effective_peak = max(peak_price or entry_price, current_price)
            peak_profit_points = effective_peak - entry_price
        else:
            profit_points = entry_price - current_price
            effective_peak = min(peak_price or entry_price, current_price)
            peak_profit_points = entry_price - effective_peak

        current_r = profit_points / sl_distance
        peak_r = peak_profit_points / sl_distance

        should_update = False
        new_sl = current_sl
        reason = "Current price within standard holding range."

        # Level 2: +2.0R+ Peak Profit -> 50% Profit Retracement Trailing Stop
        if peak_r >= 2.0:
            locked_profit_points = peak_profit_points * 0.50
            if is_buy:
                target_sl = entry_price + locked_profit_points
                if target_sl > current_sl:
                    new_sl = target_sl
                    should_update = True
                    reason = f"+2R+ Profit reached (Peak {peak_r:.2f}R). Trailing Stop trailed to lock 50% profit (${new_sl:.2f})."
            else:
                target_sl = entry_price - locked_profit_points
                if target_sl < current_sl:
                    new_sl = target_sl
                    should_update = True
                    reason = f"+2R+ Profit reached (Peak {peak_r:.2f}R). Trailing Stop trailed to lock 50% profit (${new_sl:.2f})."

        # Level 1: +1.0R Profit -> Move SL to Break-Even (entry price)
        elif current_r >= 1.0 or peak_r >= 1.0:
            if is_buy:
                if current_sl < entry_price:
                    new_sl = entry_price
                    should_update = True
                    reason = f"+1.0R profit reached ({current_r:.2f}R). SL moved to Break-Even (${entry_price:.2f})."
            else:
                if current_sl > entry_price:
                    new_sl = entry_price
                    should_update = True
                    reason = f"+1.0R profit reached ({current_r:.2f}R). SL moved to Break-Even (${entry_price:.2f})."

        return {
            "should_update": should_update,
            "new_sl": round(new_sl, 5),
            "current_sl": current_sl,
            "current_r": round(current_r, 2),
            "peak_r": round(peak_r, 2),
            "reason": reason
        }
