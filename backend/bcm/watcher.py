"""
backend/bcm/watcher.py — Zero-Cost Local Watcher.

Monitors broker account state and open positions locally without consuming external LLM tokens.
Alert triggers:
  1. Margin utilization > 30% -> CRITICAL ALERT
  2. Distance to Stop Loss < 5% -> WARNING ALERT
  3. Continuous P&L degradation across 3 consecutive measurements -> ALERT
  4. Automatic Trailing Stop evaluation (+1R Break-Even, +2R Trailing)
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

try:
    from backend.bcm.trailing_stop import TrailingStopEngine
except ImportError:
    from trailing_stop import TrailingStopEngine

logger = logging.getLogger("bcm.watcher")


class ZeroCostWatcher:
    """
    Lightweight rule-based position and risk monitor.
    """

    MARGIN_CRITICAL_THRESHOLD = 0.30  # 30%
    SL_DISTANCE_WARNING_THRESHOLD = 0.05  # 5%

    def __init__(self):
        self._pnl_history: Dict[str, List[float]] = {}

    def inspect_portfolio(
        self,
        account_balance: Dict[str, Any],
        open_positions: List[Dict[str, Any]],
        current_spot_prices: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Evaluate account health and position safety.
        """
        equity = float(account_balance.get("equity", account_balance.get("balance", 0.0)))
        margin_used = float(account_balance.get("margin_used", account_balance.get("used_margin", 0.0)))
        margin_usage_pct = (margin_used / equity) if equity > 0 else 0.0

        alerts = []
        trailing_stop_actions = []
        is_critical = False

        # 1. Check Margin Utilization
        if margin_usage_pct >= self.MARGIN_CRITICAL_THRESHOLD:
            is_critical = True
            alerts.append({
                "severity": "CRITICAL",
                "type": "HIGH_MARGIN_USAGE",
                "message": f"CRITICAL: Margin usage {margin_usage_pct:.1%} exceeds 30% safety limit."
            })

        # 2. Inspect Each Open Position
        open_position_ids = {
            str(pos.get("position_id", pos.get("id", pos.get("symbol", "unknown"))))
            for pos in open_positions
        }

        # Prune P&L history for positions that are no longer open
        for stored_pos_id in list(self._pnl_history.keys()):
            if stored_pos_id not in open_position_ids:
                del self._pnl_history[stored_pos_id]

        for pos in open_positions:
            pos_id = str(pos.get("position_id", pos.get("id", pos.get("symbol", "unknown"))))
            sym = str(pos.get("symbol", "")).upper()
            direction = str(pos.get("direction", "buy")).lower()
            entry_price = float(pos.get("entry_price", 0.0))
            current_sl = float(pos.get("sl", pos.get("stop_loss", 0.0)))
            initial_sl = float(pos.get("initial_sl", current_sl))
            peak_price = float(pos.get("peak_price", entry_price))
            unrealized_pnl = float(pos.get("unrealized_pnl", pos.get("pnl", 0.0)))

            live_price = current_spot_prices.get(sym, entry_price)

            # Record P&L history for degradation tracking
            if pos_id not in self._pnl_history:
                self._pnl_history[pos_id] = []
            self._pnl_history[pos_id].append(unrealized_pnl)
            if len(self._pnl_history[pos_id]) > 5:
                self._pnl_history[pos_id].pop(0)

            # Check 3 consecutive drops in P&L
            pnl_series = self._pnl_history[pos_id]
            if len(pnl_series) >= 3 and pnl_series[-1] < pnl_series[-2] < pnl_series[-3]:
                alerts.append({
                    "severity": "WARNING",
                    "type": "PNL_DEGRADATION",
                    "symbol": sym,
                    "position_id": pos_id,
                    "message": f"Position {sym} ({pos_id}) showing 3 consecutive measurements of P&L degradation."
                })

            # Check Distance to Stop Loss (< 5%)
            if current_sl > 0 and live_price > 0:
                dist_pct = abs(live_price - current_sl) / live_price
                if dist_pct < self.SL_DISTANCE_WARNING_THRESHOLD:
                    alerts.append({
                        "severity": "WARNING",
                        "type": "SL_PROXIMITY",
                        "symbol": sym,
                        "position_id": pos_id,
                        "distance_pct": dist_pct,
                        "message": f"Position {sym} is dangerously close ({dist_pct:.2%}) to Stop Loss (${current_sl})."
                    })

            # 3. Trailing Stop Evaluation
            if initial_sl > 0 and entry_price > 0 and live_price > 0:
                ts_res = TrailingStopEngine.evaluate_stop_adjustment(
                    direction=direction,
                    entry_price=entry_price,
                    current_price=live_price,
                    initial_sl=initial_sl,
                    current_sl=current_sl,
                    peak_price=peak_price
                )
                if ts_res.get("should_update"):
                    trailing_stop_actions.append({
                        "symbol": sym,
                        "position_id": pos_id,
                        "direction": direction,
                        "current_sl": current_sl,
                        "new_sl": ts_res["new_sl"],
                        "reason": ts_res["reason"]
                    })

        # Determine whether to wake up main orchestrator
        should_wake_orchestrator = is_critical or len(alerts) > 0

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "margin_usage_pct": round(margin_usage_pct, 4),
            "equity": equity,
            "open_positions_count": len(open_positions),
            "is_critical": is_critical,
            "should_wake_orchestrator": should_wake_orchestrator,
            "alerts": alerts,
            "trailing_stop_actions": trailing_stop_actions
        }


# Singleton instance
watcher = ZeroCostWatcher()
