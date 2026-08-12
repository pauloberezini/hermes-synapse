from typing import Dict, Any, Optional
import subprocess
import json
import os
from .exchange_interfaces import SpotBrokerInterface

class CTraderBroker(SpotBrokerInterface):
    """cTrader implementation for SpotBrokerInterface."""
    
    def __init__(self):
        # We assume openapi_client.py is in the same directory
        self.client_script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "openapi_client.py")
        # In a real environment we would locate the python executable properly
        self.python_exec = "python3"

    def _run_client(self, *args) -> Dict[str, Any]:
        try:
            cmd = [self.python_exec, self.client_script] + list(args)
            result = subprocess.run(cmd, capture_output=True, text=True, check=True)
            # Try parsing JSON output if possible
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"status": "success", "output": result.stdout}
        except subprocess.CalledProcessError as e:
            return {"status": "error", "error": e.stderr}

    def get_wallet_balance(self, account_type: str = "UNIFIED") -> Dict[str, Any]:
        """Fetch the wallet balance."""
        return self._run_client("balance")

    def get_positions(self, category: str = "linear", symbol: Optional[str] = None, base_coin: Optional[str] = None) -> Dict[str, Any]:
        """Fetch active positions."""
        return self._run_client("positions")

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
        # Mapping generic side to cTrader specific if needed. '1' for Buy, '2' for Sell.
        ctrader_side = "1" if side.lower() == "buy" else "2"
        # Optional args
        args_list = ["place", symbol, ctrader_side, str(qty)]
        if sl is not None:
            args_list.append(str(sl))
        if tp is not None:
            if sl is None:
                args_list.append("0") # padding for empty sl
            args_list.append(str(tp))
            
        return self._run_client(*args_list)

    def get_spot_prices(self, symbols: list[str]) -> Dict[str, Any]:
        import asyncio
        import os
        from backend.mcp_client import MCPServerClient
        import json as _json

        _local_map = {
            "EURUSD": 1, "GBPUSD": 2, "EURGBP": 3, "EURJPY": 4, "USDJPY": 5,
            "AUDUSD": 6, "USDCHF": 7, "USDCAD": 8, "NZDUSD": 9,
            "BTCUSD": 10028, "BTC": 10028, "ETHUSD": 10029, "ETH": 10029,
            "XAUUSD": 41, "GOLD": 41, "XAGUSD": 42, "SILVER": 42,
            "US500": 10013, "SPX500": 10013, "NAS100": 10014, "US100": 10014, "US30": 10015,
            "BRENT": 10053, "SPOTBRENT": 10053, "OIL": 10053,
        }
        PRICE_DIVISOR = {
            1: 100000, 2: 100000, 3: 100000, 4: 1000, 5: 1000,
            6: 100000, 7: 100000, 8: 100000, 9: 100000,
            10028: 100, 10029: 100, 41: 100, 42: 100,
            10013: 100, 10014: 100, 10015: 100, 10053: 100
        }
        DEFAULT_PRICE_DIVISOR = 100000

        resolved_ids = []
        for s in symbols:
            sid = _local_map.get(s.upper())
            if sid:
                resolved_ids.append(sid)

        async def _action():
            token = os.environ.get(
                "CTRADER_TOKEN",
                "eyJwbGFudCI6InBlcHBlcnN0b25lIiwiZW52aXJvbm1lbnQiOiJkZW1vIiwidG9rZW4iOiJJV2lzRnZWNC82Q2pLdGlYdXQ1OWVZQlRUZHFlT1NPUUp0S3hZMFJmbEkwPSJ9"
            )
            config = {
                'url': 'https://mcp.ctrader.com/trading/mcp',
                'headers': {'Authorization': f'Bearer {token}'}
            }
            client = MCPServerClient('ctrader', config)
            await client.start()
            raw = await client.call_tool('get_spot_prices', {'symbolId': resolved_ids})
            if isinstance(raw, str):
                raw = _json.loads(raw)
            return raw

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(1) as pool:
                    raw_result = pool.submit(lambda: asyncio.run(_action())).result()
            else:
                raw_result = asyncio.run(_action())
        except Exception as e:
            return {"error": str(e)}

        if isinstance(raw_result, dict) and 'prices' in raw_result:
            normalised = []
            for p in raw_result['prices']:
                sid = p.get('symbolId', 0)
                div = PRICE_DIVISOR.get(sid, DEFAULT_PRICE_DIVISOR)
                bid  = round(p['bid']  / div, 5) if p.get('bid')  else None
                ask  = round(p['ask']  / div, 5) if p.get('ask')  else None
                mid  = round((bid + ask) / 2, 5) if bid is not None and ask is not None else None
                high = round(p['high'] / div, 5) if p.get('high') else None
                low  = round(p['low']  / div, 5) if p.get('low')  else None
                sess_close = round(p['sessionClose'] / div, 5) if p.get('sessionClose') else None
                
                name_lookup = {v: k for k, v in _local_map.items()}
                name = name_lookup.get(sid, str(sid))
                
                normalised.append({
                    'symbolId': name,
                    'name': name,
                    'bid': bid, 'ask': ask, 'mid': mid,
                    'high': high, 'low': low, 'sessionClose': sess_close,
                    'timestamp': p.get('timestamp')
                })
            return {"prices": normalised}
        return {"error": "Failed to parse prices"}

