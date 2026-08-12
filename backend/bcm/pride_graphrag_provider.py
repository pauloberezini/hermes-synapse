import os
import requests
import logging
from typing import Optional, Dict, Any
try:
    from backend.bcm.analytics_interfaces import AnalyticsProviderInterface
except ImportError:
    from analytics_interfaces import AnalyticsProviderInterface

logger = logging.getLogger(__name__)

class PrideGraphRAGProvider(AnalyticsProviderInterface):
    """Implementation for Pride-GraphRAG Q&A API."""
    
    def query_playbook(self, query: str, channel: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
        if not query:
            return {"error": "Query parameter is required"}

        default_host = "host.docker.internal" if os.path.exists("/.dockerenv") else "localhost"
        default_url = f"http://{default_host}:8088/api/v1/analytics/ask"
        url = os.environ.get("GRAPHRAG_API_URL", default_url)
        
        payload = {"query": query}
        if channel:
            payload["channel"] = channel

        try:
            resp = requests.post(url, json=payload, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"GraphRAG API returned HTTP {resp.status_code}: {resp.text[:300]}"}
        except Exception as e:
            if "localhost" in url or "127.0.0.1" in url:
                alt_url = url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
                try:
                    resp = requests.post(alt_url, json=payload, timeout=timeout)
                    if resp.status_code == 200:
                        return resp.json()
                    return {"error": f"GraphRAG API returned HTTP {resp.status_code}: {resp.text[:300]}"}
                except Exception:
                    pass
            logger.warning(f"GraphRAG API error: {e}")
            return {"error": f"Failed to connect to Pride-GraphRAG API ({url}): {e}"}
