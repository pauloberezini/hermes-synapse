import sys
import os

BCM_DIR = os.path.dirname(os.path.abspath(__file__))
if BCM_DIR not in sys.path:
    sys.path.insert(0, BCM_DIR)

import sqlite3
import json
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.http import models

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(WORKSPACE_ROOT, "logs/bcm_memory.db")
QDRANT_STORAGE_PATH = os.path.join(WORKSPACE_ROOT, "logs/qdrant_data")
COLLECTION_NAME = "bcm_market_memory"

class BCMMemory:
    def __init__(self):
        self.init_db()
        try:
            os.makedirs(QDRANT_STORAGE_PATH, exist_ok=True)
            self.qclient = QdrantClient(path=QDRANT_STORAGE_PATH)
            self.init_qdrant()
        except Exception as e:
            print(f"⚠️ Memory Error (Qdrant local): {e}")
            self.qclient = None

    def init_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # Trade Log Table
        c.execute('''CREATE TABLE IF NOT EXISTS trades 
                     (trade_id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT, 
                      side TEXT, volume REAL, entry_price REAL, exit_price REAL, 
                      pnl REAL, status TEXT, reasoning TEXT, context_json TEXT)''')
        conn.commit()
        conn.close()

    def has_open_position(self, symbol):
        """Return True if there is already an OPEN trade logged for this symbol."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM trades WHERE symbol=? AND status='OPEN'", (symbol,))
        count = c.fetchone()[0]
        conn.close()
        return count > 0


    def init_qdrant(self):
        if not self.qclient: return
        collections = self.qclient.get_collections().collections
        exists = any(c.name == COLLECTION_NAME for c in collections)
        if not exists:
            self.qclient.recreate_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(size=8, distance=models.Distance.COSINE),
            )

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
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO trades (trade_id, timestamp, symbol, side, volume, entry_price, status, reasoning, context_json) VALUES (?,?,?,?,?,?,?,?,?)",
                  (trade_id, datetime.now().isoformat(), symbol, side, volume, price, "OPEN", reasoning, json.dumps(context_data)))
        conn.commit()
        conn.close()

    def update_trade_result(self, trade_id, exit_price, pnl):
        """Update trade with final result and store context in Qdrant."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT context_json, side, symbol FROM trades WHERE trade_id=?", (trade_id,))
        row = c.fetchone()
        if not row:
            conn.close()
            return
        
        context_data = json.loads(row[0])
        side = row[1]
        
        c.execute("UPDATE trades SET exit_price=?, pnl=?, status=? WHERE trade_id=?", 
                  (exit_price, pnl, "CLOSED", trade_id))
        conn.commit()
        conn.close()

        # Store in Vector Memory
        if self.qclient:
            vector = self._get_market_vector(context_data)
            self.qclient.upsert(
                collection_name=COLLECTION_NAME,
                points=[
                    models.PointStruct(
                        id=hash(trade_id) % (10**10), # Simple unique ID
                        vector=vector,
                        payload={
                            "trade_id": trade_id,
                            "symbol": row[2],
                            "pnl": pnl,
                            "side": side,
                            "timestamp": datetime.now().isoformat()
                        }
                    )
                ]
            )

    def get_similar_experience(self, current_context_data):
        """Search for similar past situations and return results."""
        if not self.qclient: return []
        
        try:
            vector = self._get_market_vector(current_context_data)
            
            # Try query_points (newer versions) then search (older versions)
            if hasattr(self.qclient, "query_points"):
                search_result = self.qclient.query_points(
                    collection_name=COLLECTION_NAME,
                    query=vector,
                    limit=5
                ).points
            elif hasattr(self.qclient, "search"):
                search_result = self.qclient.search(
                    collection_name=COLLECTION_NAME,
                    query_vector=vector,
                    limit=5
                )
            else:
                print("⚠️ QdrantClient has neither 'query_points' nor 'search' method.")
                return []
                
            return [res.payload for res in search_result]
        except Exception as e:
            print(f"⚠️ Memory Search Failed: {e}")
            return []
