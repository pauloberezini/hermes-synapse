import sys
import os

BCM_DIR = os.path.dirname(os.path.abspath(__file__))
if BCM_DIR not in sys.path:
    sys.path.insert(0, BCM_DIR)

from backend.database import _execute
import json
from datetime import datetime
from backend.memory import get_memory_engine

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class BCMMemory:
    def __init__(self):
        self.init_db()
        try:
            self.memory_engine = get_memory_engine()
            self.init_vector_db()
        except Exception as e:
            print(f"⚠️ Memory Warning (Vector DB initialization): {e}")
            self.memory_engine = None

    def init_db(self):
        # Trade Log Table
        _execute('''CREATE TABLE IF NOT EXISTS trades 
                     (trade_id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT, 
                      side TEXT, volume REAL, entry_price REAL, exit_price REAL, 
                      pnl REAL, status TEXT, reasoning TEXT, context_json TEXT)''')

    def has_open_position(self, symbol):
        """Return True if there is already an OPEN trade logged for this symbol."""
        rows = _execute("SELECT COUNT(*) as count FROM trades WHERE symbol=? AND status='OPEN'", (symbol,))
        count = 0
        if rows:
            count = rows[0][0] if isinstance(rows[0], (list, tuple)) else rows[0]["count"]
        return count > 0

    def init_vector_db(self):
        if not self.memory_engine: return
        self.memory_engine.init_memory()

    def _get_market_vector(self, data):
        """Convert market indicators to a fixed-size 8D vector."""
        try:
            v = [
                float(data.get('rsi', 50)) / 100.0,
                float(data.get('remizov_shift', 0)) + 0.5, # Offset to positive
                float(data.get('ema_dist', 0)) / 1000.0, # Normalized dist
                float(data.get('macd_hist', 0)) / 10.0,
                float(data.get('atr', 1)) / 100.0,
                float(data.get('keltner_upper_dist', 0)) / 500.0,
                float(data.get('keltner_lower_dist', 0)) / 500.0,
                float(datetime.now().hour) / 24.0 # Time of day component
            ]
            return v
        except:
            return [0.5] * 8

    def log_decision(self, trade_id, symbol, side, volume, price, reasoning, context_data):
        """Log the initial entry decision."""
        _execute("INSERT INTO trades (trade_id, timestamp, symbol, side, volume, entry_price, status, reasoning, context_json) VALUES (?,?,?,?,?,?,?,?,?)",
                  (trade_id, datetime.now().isoformat(), symbol, side, volume, price, "OPEN", reasoning, json.dumps(context_data)))

    def update_trade_result(self, trade_id, exit_price, pnl):
        """Update trade with final result and store context in Qdrant."""
        rows = _execute("SELECT context_json, side, symbol FROM trades WHERE trade_id=?", (trade_id,))
        if not rows:
            return
        
        row = rows[0]
        context_data = json.loads(row[0] if isinstance(row, (list, tuple)) else row["context_json"])
        side = row[1] if isinstance(row, (list, tuple)) else row["side"]
        symbol = row[2] if isinstance(row, (list, tuple)) else row["symbol"]
        
        _execute("UPDATE trades SET exit_price=?, pnl=?, status=? WHERE trade_id=?", 
                  (exit_price, pnl, "CLOSED", trade_id))

        # Store in Vector Memory
        if self.memory_engine:
            vector = self._get_market_vector(context_data)
            self.memory_engine.index_vector(
                doc_id=str(hash(trade_id) % (10**10)), # Simple unique ID
                vector=vector,
                payload={
                    "trade_id": trade_id,
                    "symbol": row[2],
                    "pnl": pnl,
                    "side": side,
                    "timestamp": datetime.now().isoformat(),
                    "paradigm": f"Trade closed with PnL {pnl}. Re-evaluate technical entries similar to this condition."
                },
                collection_name="bcm_market_memory"
            )

    def get_similar_experience(self, current_context_data):
        """Search for similar past situations and return results."""
        if not self.memory_engine: return []
        
        try:
            vector = self._get_market_vector(current_context_data)
            return self.memory_engine.search_vector(
                vector=vector,
                limit=5,
                collection_name="bcm_market_memory"
            )
        except Exception as e:
            print(f"⚠️ Memory Search Failed: {e}")
            return []

    def extract_paradigms_for_context(self, current_context_data):
        """Extract paradigms (lessons) from similar past trades for dynamic prompt injection."""
        experiences = self.get_similar_experience(current_context_data)
        if not experiences:
            return "No specific paradigms found for this market context."
        
        paradigms = []
        for exp in experiences:
            pnl = exp.get("pnl", 0)
            side = exp.get("side", "UNKNOWN")
            sym = exp.get("symbol", "UNKNOWN")
            paradigm_text = exp.get("paradigm", "")
            
            if pnl < 0:
                result = f"📉 AVOID PAST MISTAKE (Lost ${abs(pnl)} on {side} {sym}): {paradigm_text}"
            else:
                result = f"📈 SUCCESS PATTERN (Won ${pnl} on {side} {sym}): {paradigm_text}"
            paradigms.append(result)
            
        return "\n".join(paradigms)
