"""
backend/bcm/self_learning_pipeline.py — Self Learning & Shadow Optimization Pipeline

Analyzes closed trades to calculate Predicted vs Actual metrics (Delta).
Triggers notifications if structural decay is detected in the Confluence weights.
"""

import logging
import sqlite3
import os
import json
from datetime import datetime

logger = logging.getLogger("hermes.bcm.self_learning")

class SelfLearningEngine:
    def __init__(self):
        self.workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.bcm_memory_db = os.path.join(self.workspace_root, "logs/bcm_memory.db")
        self.performance_threshold_delta = 0.5  # Max tolerated deviation in R:R

    def analyze_closed_trades(self):
        """
        Calculates predicted vs actual metrics for recently closed trades.
        """
        if not os.path.exists(self.bcm_memory_db):
            logger.warning("No BCM memory database found for self-learning analysis.")
            return

        try:
            conn = sqlite3.connect(self.bcm_memory_db)
            c = conn.cursor()
            
            # Fetch closed trades where PnL is resolved
            c.execute("""
                SELECT trade_id, symbol, side, entry_price, exit_price, pnl, reasoning 
                FROM trades 
                WHERE status='CLOSED' AND pnl IS NOT NULL
                ORDER BY timestamp DESC LIMIT 50
            """)
            closed_trades = c.fetchall()
            conn.close()

            deltas = []
            for t in closed_trades:
                trade_id, symbol, side, entry, exit_p, pnl, reasoning = t
                
                # Naive actual R:R based on Entry, Exit, PnL
                # In a real scenario, we parse the "reasoning" for the exact recommended SL to calculate Predicted RR.
                # Here we fallback to deterministic checking if parsing fails.
                predicted_rr = 2.0  # Assumed default normal buy
                if "Confluence Score" in reasoning:
                    if "STRONG" in reasoning.upper():
                        predicted_rr = 3.0
                
                # Assume risk was 1% of something. We just calculate raw delta.
                # For simplicity in this demo, actual RR is roughly proportional to PNL > 0
                actual_rr = (pnl / abs(entry)) * 100 if entry != 0 else 0
                
                delta = abs(predicted_rr - actual_rr)
                deltas.append(delta)
                
                # Log to traceability database
                try:
                    from backend.database import _execute
                    # We use trade_id as trace_id mapping for now
                    sql = """
                        INSERT INTO self_learning_metrics (trace_id, predicted_rr, actual_rr, delta, timestamp)
                        VALUES (?, ?, ?, ?, ?)
                    """
                    ts = datetime.utcnow().isoformat() + "Z"
                    _execute(sql, (trade_id, str(predicted_rr), str(actual_rr), float(delta), ts))
                except Exception as e:
                    logger.error(f"Failed to log self learning metric: {e}")

            if deltas:
                avg_delta = sum(deltas) / len(deltas)
                if avg_delta > self.performance_threshold_delta:
                    logger.warning(f"Self-Learning: Model decay detected. Avg Delta {avg_delta:.2f} > {self.performance_threshold_delta}.")
                    # Here we would normally trigger shadow A/B weight rebalancing
                    return {"status": "decay_detected", "avg_delta": avg_delta}
                return {"status": "optimal", "avg_delta": avg_delta}
            
            return {"status": "no_data", "avg_delta": 0}

        except Exception as e:
            logger.error(f"Error in SelfLearningEngine: {e}")
            return {"status": "error", "error": str(e)}

