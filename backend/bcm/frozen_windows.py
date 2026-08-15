"""
backend/bcm/frozen_windows.py — Macro Calendar & Frozen Windows Controller.

Manages market-wide and instrument-specific trading lockouts around high-impact
macroeconomic events (FOMC, CPI, NFP, Interest Rate decisions, GDP).
"""

from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
import os
import json


class EventImpact:
    HIGH = "HIGH"        # FOMC, NFP, CPI, Central Bank Rate Decisions
    MEDIUM = "MEDIUM"    # PMI, Retail Sales, Housing Starts
    LOW = "LOW"          # Consumer Confidence, Factory Orders


class FrozenWindowsController:
    """
    Controls trading freezes around high-impact economic releases.
    Rules:
      - HIGH events: Freeze new entries 2 hours before, during, and 2 hours after.
      - MEDIUM events: Freeze new entries 15 minutes before and 15 minutes after.
      - LOW events: Informational only (no lock).
    """

    def __init__(self, high_freeze_minutes: int = 120, medium_freeze_minutes: int = 15):
        self.high_freeze_minutes = high_freeze_minutes
        self.medium_freeze_minutes = medium_freeze_minutes
        self._events: List[Dict[str, Any]] = []

    def register_event(
        self,
        event_name: str,
        event_time_utc: datetime,
        impact: str = EventImpact.HIGH,
        affected_currencies: Optional[List[str]] = None,
        affected_symbols: Optional[List[str]] = None,
    ) -> None:
        """Register a scheduled macroeconomic event."""
        if event_time_utc.tzinfo is None:
            event_time_utc = event_time_utc.replace(tzinfo=timezone.utc)
        self._events.append({
            "name": event_name,
            "time": event_time_utc,
            "impact": impact.upper(),
            "currencies": [c.upper() for c in (affected_currencies or ["USD"])],
            "symbols": [s.upper() for s in (affected_symbols or [])],
        })

    def clear_events(self) -> None:
        """Clear all registered events."""
        self._events.clear()

    def get_active_frozen_window(
        self,
        symbol: str,
        current_time_utc: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Check if trading is currently frozen for a given symbol.

        Returns:
            dict with:
                is_frozen (bool): True if trading is blocked.
                reason (str): Reason for the freeze if active.
                event_name (str): The blocking event name.
                time_to_event_min (float): Minutes until/since the event.
                window_type (str): 'PRE_EVENT', 'DURING_EVENT', 'POST_EVENT', or 'NONE'.
        """
        if current_time_utc is None:
            current_time_utc = datetime.now(timezone.utc)
        elif current_time_utc.tzinfo is None:
            current_time_utc = current_time_utc.replace(tzinfo=timezone.utc)

        sym_upper = symbol.upper()

        for ev in self._events:
            ev_time = ev["time"]
            impact = ev["impact"]

            # Determine freeze window in minutes
            if impact == EventImpact.HIGH:
                pre_freeze = self.high_freeze_minutes
                post_freeze = self.high_freeze_minutes
            elif impact == EventImpact.MEDIUM:
                pre_freeze = self.medium_freeze_minutes
                post_freeze = self.medium_freeze_minutes
            else:
                continue  # LOW impact does not freeze

            diff_sec = (ev_time - current_time_utc).total_seconds()
            diff_min = diff_sec / 60.0

            # Check if symbol is affected (USD affects US500, BTC, GOLD, GBPUSD, BRENT, etc.)
            affects_all = "USD" in ev["currencies"] or not ev["currencies"]
            symbol_affected = affects_all or sym_upper in ev["symbols"] or any(curr in sym_upper for curr in ev["currencies"])

            if not symbol_affected:
                continue

            # Within pre-event freeze window: 0 < diff_min <= pre_freeze
            if 0 < diff_min <= pre_freeze:
                return {
                    "is_frozen": True,
                    "reason": f"FROZEN WINDOW: High-impact event '{ev['name']}' in {diff_min:.1f} minutes. New entries locked.",
                    "event_name": ev["name"],
                    "time_to_event_min": diff_min,
                    "window_type": "PRE_EVENT",
                }

            # Within post-event freeze window: -post_freeze <= diff_min <= 0
            if -post_freeze <= diff_min <= 0:
                return {
                    "is_frozen": True,
                    "reason": f"FROZEN WINDOW: High-impact event '{ev['name']}' occurred {abs(diff_min):.1f} minutes ago. Post-event volatility lock.",
                    "event_name": ev["name"],
                    "time_to_event_min": diff_min,
                    "window_type": "POST_EVENT",
                }

        return {
            "is_frozen": False,
            "reason": "Market open. No active macro event frozen windows.",
            "event_name": "",
            "time_to_event_min": 0.0,
            "window_type": "NONE",
        }


# Singleton instance for system-wide access
_global_frozen_controller = FrozenWindowsController()

def get_frozen_windows_controller() -> FrozenWindowsController:
    return _global_frozen_controller
