import os
import sys
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("jarvis.bcm.crypto_trader")

# Ensure BCM directory is in sys.path
BCM_DIR = os.path.dirname(os.path.abspath(__file__))
if BCM_DIR not in sys.path:
    sys.path.insert(0, BCM_DIR)

try:
    from backend.bcm.bybit_trader import BybitTrader
except ImportError:
    from bybit_trader import BybitTrader

try:
    from backend.bcm.memory_manager import BCMMemory
except ImportError:
    from memory_manager import BCMMemory


class BCMCryptoTrader:
    """Dedicated Autonomous Crypto & Options Trader for BCM Crypto Orchestrator."""

    def __init__(self):
        self.bybit = BybitTrader()
        self.memory = BCMMemory()

    def run_crypto_cycle(self, symbol: str = "ETHUSDT") -> Dict[str, Any]:
        """Runs an autonomous market & option risk evaluation cycle for Bybit."""
        logger.info(f"Running BCM Crypto autonomous cycle for {symbol}...")

        # 1. Fetch Spot Price & Active Positions
        spot_price = self.bybit.get_spot_price(symbol)
        positions_res = self.bybit.get_positions(category="linear", symbol=symbol)
        options_res = self.bybit.get_positions(category="option", base_coin=symbol.replace("USDT", ""))

        # 2. Analyze portfolio Greeks & Margin Safety
        base_coin = symbol.replace("USDT", "")
        greeks = self.bybit.get_portfolio_greeks(base_coin=base_coin)
        margin_safety = self.bybit.check_margin_safety(base_coin=base_coin)

        # 3. Analyze default/active option position
        eth_put_analysis = self.bybit.analyze_option_position(
            symbol="ETH-DEC26-1300-P",
            strike=1300.0,
            option_type="Put",
            side="Sell",
            premium=50.0,
            exp_date="December",
            current_spot=spot_price
        )

        cycle_result = {
            "status": "success",
            "symbol": symbol,
            "current_spot_price": spot_price,
            "portfolio_greeks": greeks,
            "margin_safety": margin_safety,
            "active_linear_positions": positions_res.get("positions", []),
            "active_options_positions": options_res.get("positions", []),
            "option_risk_assessment": eth_put_analysis,
            "timestamp": json.dumps(eth_put_analysis.get("exp_date"))
        }

        # 4. Log decision into BCM Memory
        try:
            self.memory.log_decision(
                asset=symbol,
                decision="HOLD_OPTION",
                reasoning=eth_put_analysis.get("recommendation", "Option position monitored."),
                macro_ctx=f"Bybit Spot: ${spot_price:.2f}, Net Delta USD: ${greeks.get('net_delta_usd'):.2f}, Margin Utilization: {margin_safety.get('current_margin_utilization_pct')}%"
            )
        except Exception as e:
            logger.warning(f"Failed to log BCM crypto decision to memory: {e}")

        return cycle_result


def run_crypto_cycle_cli():
    trader = BCMCryptoTrader()
    res = trader.run_crypto_cycle("ETHUSDT")
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    run_crypto_cycle_cli()
