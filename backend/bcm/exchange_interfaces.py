from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

class ExchangeBrokerInterface(ABC):
    """Base interface for all exchange providers."""

    @abstractmethod
    def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict[str, Any]:
        """Fetch the wallet balance."""
        pass


class SpotBrokerInterface(ExchangeBrokerInterface):
    """Interface for spot and linear futures trading."""

    @abstractmethod
    def get_positions(self, category: str = "linear", symbol: Optional[str] = None, base_coin: Optional[str] = None) -> Dict[str, Any]:
        """Fetch active positions."""
        pass

    @abstractmethod
    def get_spot_prices(self, symbols: list[str]) -> Dict[str, Any]:
        """Fetch live spot prices for the given standardized ticker symbols (e.g. ['BTCUSD', 'XAUUSD'])."""
        pass

    @abstractmethod
    def place_order(
        self,
        category: str,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: Optional[str] = None,
        sl: Optional[str] = None,
        tp: Optional[str] = None
    ) -> Dict[str, Any]:
        """Place an order."""
        pass


class OptionsBrokerInterface(ExchangeBrokerInterface):
    """Interface for options and derivatives trading."""

    @abstractmethod
    def get_option_chain(self, base_coin: str = "ETH", exp_date: Optional[str] = None) -> Dict[str, Any]:
        """Fetch the options chain for a given base coin."""
        pass

    @abstractmethod
    def analyze_option_position(
        self,
        symbol: str,
        strike: float,
        option_type: str,
        side: str,
        premium: float,
        exp_date: str,
        current_spot: float
    ) -> Dict[str, Any]:
        """Analyze an option position."""
        pass

    @abstractmethod
    def get_portfolio_greeks(self, base_coin: str = "ETH") -> Dict[str, Any]:
        """Fetch portfolio Greeks."""
        pass

    @abstractmethod
    def calc_delta_hedge(self, base_coin: str = "ETH") -> Dict[str, Any]:
        """Calculate the delta hedge required."""
        pass

    @abstractmethod
    def check_margin_safety(self, base_coin: str = "ETH") -> Dict[str, Any]:
        """Check margin safety."""
        pass

    @abstractmethod
    def place_option_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: Optional[str] = None
    ) -> Dict[str, Any]:
        """Place an options order."""
        pass
