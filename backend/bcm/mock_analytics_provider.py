from typing import Optional, Dict, Any
try:
    from backend.bcm.analytics_interfaces import AnalyticsProviderInterface
except ImportError:
    from analytics_interfaces import AnalyticsProviderInterface

class MockAnalyticsProvider(AnalyticsProviderInterface):
    """Mock implementation for AnalyticsProviderInterface for local testing."""
    
    def query_playbook(self, query: str, channel: Optional[str] = None, timeout: int = 60) -> Dict[str, Any]:
        if not query:
            return {"error": "Query parameter is required"}

        # Simulate some logic based on the query to return fake data
        if "BTC" in query.upper():
            answer = "Historical playbook for BTC suggests buying on dips below 200-day moving average. No recent anomalies detected."
        elif "ETH" in query.upper():
            answer = "ETH playbook: Watch for high gas fees correlating with local tops. Delta hedging recommended above $3000."
        else:
            answer = "Generic historical playbook: Trend is your friend. Maintain strict risk management."

        return {
            "answer": answer,
            "citations": [
                {"source": "mock_database_v1", "confidence": 0.99}
            ],
            "channel": channel or "default",
            "mocked": True
        }
