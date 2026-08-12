import os
try:
    from backend.bcm.analytics_interfaces import AnalyticsProviderInterface
except ImportError:
    from analytics_interfaces import AnalyticsProviderInterface

class AnalyticsFactory:
    """Factory for instantiating the appropriate AnalyticsProvider based on configuration."""

    _provider: AnalyticsProviderInterface = None

    @classmethod
    def get_provider(cls) -> AnalyticsProviderInterface:
        """Get the active analytics provider."""
        if cls._provider is not None:
            return cls._provider

        active_analytics = os.environ.get("BCM_ACTIVE_ANALYTICS", "mock").lower()

        if active_analytics == "pride-graphrag":
            try:
                from backend.bcm.pride_graphrag_provider import PrideGraphRAGProvider
            except ImportError:
                from pride_graphrag_provider import PrideGraphRAGProvider
            cls._provider = PrideGraphRAGProvider()
        elif active_analytics == "mock":
            try:
                from backend.bcm.mock_analytics_provider import MockAnalyticsProvider
            except ImportError:
                from mock_analytics_provider import MockAnalyticsProvider
            cls._provider = MockAnalyticsProvider()
        else:
            # Default to mock if unknown
            try:
                from backend.bcm.mock_analytics_provider import MockAnalyticsProvider
            except ImportError:
                from mock_analytics_provider import MockAnalyticsProvider
            cls._provider = MockAnalyticsProvider()

        return cls._provider
