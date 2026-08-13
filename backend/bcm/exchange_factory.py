import os
try:
    from backend.bcm.exchange_interfaces import ExchangeBrokerInterface, SpotBrokerInterface, OptionsBrokerInterface
    from backend.bcm.bybit_trader import BybitTrader
    from backend.bcm.mock_exchange import MockExchange
except ImportError:
    from exchange_interfaces import ExchangeBrokerInterface, SpotBrokerInterface, OptionsBrokerInterface
    from bybit_trader import BybitTrader
    from mock_exchange import MockExchange

class ExchangeFactory:
    """Factory to return the active exchange broker based on configuration."""
    
    _instance = None

    @classmethod
    def get_broker(cls, provider: str = None) -> ExchangeBrokerInterface:
        if cls._instance is not None and provider is None:
            return cls._instance

        provider = provider or os.environ.get("BCM_ACTIVE_BROKER", "bybit").lower()
        
        if provider == "mock":
            cls._instance = MockExchange()
        elif provider == "bybit":
            cls._instance = BybitTrader()
        else:
            cls._instance = BybitTrader()  # fallback

        return cls._instance

    @classmethod
    def get_options_broker(cls, provider: str = None) -> OptionsBrokerInterface:
        broker = cls.get_broker(provider)
        if not isinstance(broker, OptionsBrokerInterface):
            raise ValueError(f"Active broker {type(broker).__name__} does not support options.")
        return broker

    @classmethod
    def get_spot_broker(cls, provider: str = None) -> SpotBrokerInterface:
        broker = cls.get_broker(provider)
        if not isinstance(broker, SpotBrokerInterface):
            raise ValueError(f"Active broker {type(broker).__name__} does not support spot trading.")
        return broker
