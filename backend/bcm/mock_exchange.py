from typing import Dict, Any, Optional
import uuid
import time
from .exchange_interfaces import SpotBrokerInterface, OptionsBrokerInterface

class MockExchange(SpotBrokerInterface, OptionsBrokerInterface):
    """
    Mock Exchange Provider for local paper trading and testing.
    Maintains state in memory to avoid zero-friction onboarding issues.
    """
    def __init__(self):
        self.balance = 10000.0
        self.positions = []
        self.orders = []

    def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict[str, Any]:
        return {
            "status": "success",
            "accounts": [{
                "coin": [
                    {"coin": "USDT", "equity": str(self.balance), "availableToWithdraw": str(self.balance)},
                    {"coin": "USDC", "equity": str(self.balance), "availableToWithdraw": str(self.balance)}
                ]
            }]
        }

    def get_positions(self, category: str = "linear", symbol: Optional[str] = None, base_coin: Optional[str] = None) -> Dict[str, Any]:
        return {
            "status": "success",
            "positions": self.positions
        }

    def get_spot_prices(self, symbols: list[str]) -> Dict[str, Any]:
        """Mock spot prices."""
        prices = []
        for sym in symbols:
            prices.append({
                "symbolId": sym,
                "name": sym,
                "bid": 50000.0 if "BTC" in sym else (2000.0 if "ETH" in sym else 100.0),
                "ask": 50010.0 if "BTC" in sym else (2001.0 if "ETH" in sym else 100.1),
                "mid": 50005.0 if "BTC" in sym else (2000.5 if "ETH" in sym else 100.05),
                "high": 51000.0,
                "low": 49000.0,
                "sessionClose": 49500.0
            })
        return {"status": "success", "prices": prices}

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
        order = {
            "order_id": str(uuid.uuid4()),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "status": "filled"
        }
        self.orders.append(order)
        # Dummy position creation
        self.positions.append({
            "symbol": symbol,
            "side": side,
            "size": qty,
            "entryPrice": price or "100"
        })
        return {"status": "success", "order_id": order["order_id"]}

    def get_option_chain(self, base_coin: str = "ETH", exp_date: Optional[str] = None) -> Dict[str, Any]:
        # Generate some mock options
        return {
            "status": "success",
            "chain": [
                {
                    "symbol": f"{base_coin}-30DEC26-100000-C",
                    "markPrice": "500",
                    "openInterest": "100",
                    "iv": "0.5",
                    "delta": "0.3",
                    "gamma": "0.01",
                    "theta": "-10",
                    "vega": "2",
                    "bid1Price": "490",
                    "ask1Price": "510"
                },
                {
                    "symbol": f"{base_coin}-30DEC26-80000-P",
                    "markPrice": "300",
                    "openInterest": "200",
                    "iv": "0.6",
                    "delta": "-0.2",
                    "gamma": "0.01",
                    "theta": "-5",
                    "vega": "1.5",
                    "bid1Price": "290",
                    "ask1Price": "310"
                }
            ]
        }

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
        return {"status": "success", "analysis": "Mock analysis"}

    def get_portfolio_greeks(self, base_coin: str = "ETH") -> Dict[str, Any]:
        return {"status": "success", "greeks": {"delta": "0", "gamma": "0", "theta": "0", "vega": "0"}}

    def calc_delta_hedge(self, base_coin: str = "ETH") -> Dict[str, Any]:
        return {"status": "success", "hedge_qty": "0"}

    def check_margin_safety(self, base_coin: str = "ETH") -> Dict[str, Any]:
        return {"status": "success", "safe": True}

    def place_option_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        qty: str,
        price: Optional[str] = None
    ) -> Dict[str, Any]:
        return self.place_order("option", symbol, side, order_type, qty, price)

