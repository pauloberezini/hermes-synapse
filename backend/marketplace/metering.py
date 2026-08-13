"""
Marketplace Usage Telemetry & Metering Accounting Engine (Phase 3)

Tracks execution frequency, token consumption, latencies, and free-tier quotas
per skill and subagent invocation.
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from backend.database import _execute

logger = logging.getLogger(__name__)


class MeteringEngine:
    """Tracks and queries execution usage, token counts, and quota limits."""

    @staticmethod
    def record_usage(
        skill_id: str,
        subagent_id: str = "",
        execution_time_ms: int = 0,
        tokens_used: int = 0,
        status_code: str = "200"
    ) -> Dict[str, Any]:
        """Record a telemetry data point for a skill tool execution."""
        _execute("""
            INSERT INTO marketplace_telemetry (skill_id, subagent_id, execution_time_ms, tokens_used, status_code)
            VALUES (?, ?, ?, ?, ?)
        """, (skill_id, subagent_id, execution_time_ms, tokens_used, status_code))
        logger.debug(f"Telemetry recorded for skill '{skill_id}': {execution_time_ms}ms, {tokens_used} tokens.")
        return {
            "status": "success",
            "skill_id": skill_id,
            "subagent_id": subagent_id,
            "execution_time_ms": execution_time_ms,
            "tokens_used": tokens_used
        }

    @staticmethod
    def get_skill_stats(skill_id: str) -> Dict[str, Any]:
        """Retrieve aggregated telemetry statistics for a specific skill."""
        rows = _execute("""
            SELECT COUNT(*) as total_calls,
                   COALESCE(SUM(execution_time_ms), 0) as total_time_ms,
                   COALESCE(SUM(tokens_used), 0) as total_tokens,
                   COALESCE(AVG(execution_time_ms), 0) as avg_latency_ms
            FROM marketplace_telemetry
            WHERE skill_id = ?
        """, (skill_id,))
        if not rows:
            return {"skill_id": skill_id, "total_calls": 0, "total_time_ms": 0, "total_tokens": 0, "avg_latency_ms": 0.0}
        r = rows[0]
        if isinstance(r, (list, tuple)):
            total_calls, total_time_ms, total_tokens, avg_latency_ms = r[:4]
        else:
            total_calls = r["total_calls"]
            total_time_ms = r["total_time_ms"]
            total_tokens = r["total_tokens"]
            avg_latency_ms = r["avg_latency_ms"]
        return {
            "skill_id": skill_id,
            "total_calls": total_calls or 0,
            "total_time_ms": total_time_ms or 0,
            "total_tokens": total_tokens or 0,
            "avg_latency_ms": round(float(avg_latency_ms or 0.0), 2)
        }

    @staticmethod
    def check_quota(skill_id: str, daily_limit: int = 1000) -> bool:
        """Check if skill execution is within allowed free-tier daily quota."""
        start_of_day = datetime.now(timezone.utc).strftime('%Y-%m-%d 00:00:00')
        rows = _execute("""
            SELECT COUNT(*) as today_calls
            FROM marketplace_telemetry
            WHERE skill_id = ? AND created_at >= ?
        """, (skill_id, start_of_day))
        if not rows:
            return True
        r = rows[0]
        today_calls = r[0] if isinstance(r, (list, tuple)) else r["today_calls"]
        return today_calls < daily_limit
