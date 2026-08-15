"""
backend/bcm/fast_market_cache.py — Fast Data Layer & Staleness Guard.

Provides in-memory / Redis fast-cache access for market snapshots, indicators, and regimes
with strict staleness metadata validation (_meta.is_stale, ttl_remaining).
"""

from typing import Dict, Any, Optional
import time
import json
import os


class FastMarketCache:
    """
    Sub-millisecond market cache with TTL and staleness validation.
    Falls back to in-memory store if Redis is unavailable.
    """

    def __init__(self, default_ttl_sec: int = 1800):
        self.default_ttl = default_ttl_sec
        self._memory_store: Dict[str, Dict[str, Any]] = {}
        self._redis_client = None
        self._init_redis()

    def _init_redis(self):
        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            try:
                import redis
                self._redis_client = redis.from_url(redis_url, decode_responses=True)
            except Exception:
                self._redis_client = None

    def set(self, key: str, data: Any, ttl_sec: Optional[int] = None) -> None:
        """Store key with timestamp and TTL."""
        ttl = ttl_sec or self.default_ttl
        now = time.time()
        payload = {
            "data": data,
            "_meta": {
                "source": "fast_cache",
                "timestamp": now,
                "ttl_sec": ttl,
                "expires_at": now + ttl
            }
        }
        if self._redis_client:
            try:
                self._redis_client.setex(key, ttl, json.dumps(payload))
                return
            except Exception:
                pass

        self._memory_store[key] = payload

    def get(self, key: str) -> Dict[str, Any]:
        """
        Retrieve data with staleness validation.
        """
        now = time.time()
        raw_payload = None

        if self._redis_client:
            try:
                val = self._redis_client.get(key)
                if val:
                    raw_payload = json.loads(val)
            except Exception:
                raw_payload = None

        if not raw_payload:
            raw_payload = self._memory_store.get(key)

        if not raw_payload:
            return {
                "data": None,
                "_meta": {
                    "source": "none",
                    "timestamp": 0,
                    "is_stale": True,
                    "staleness_warning": f"Key '{key}' not found in cache."
                }
            }

        meta = raw_payload.get("_meta", {})
        ts = meta.get("timestamp", 0)
        ttl = meta.get("ttl_sec", self.default_ttl)
        age = now - ts
        is_stale = age > ttl

        return {
            "data": raw_payload.get("data"),
            "_meta": {
                "source": meta.get("source", "memory"),
                "timestamp": ts,
                "age_sec": round(age, 1),
                "ttl_remaining_sec": max(0.0, round(ttl - age, 1)),
                "is_stale": is_stale,
                "staleness_warning": f"Data is stale (age: {age:.1f}s > TTL {ttl}s)" if is_stale else ""
            }
        }


# Global Cache Instance
fast_market_cache = FastMarketCache()
