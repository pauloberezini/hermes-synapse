import os
import sys
import json
import asyncio
import logging

logger = logging.getLogger("jarvis.bcm.tools")

# Ensure BCM directory is in sys.path so modules can import from each other correctly
BCM_DIR = os.path.dirname(os.path.abspath(__file__))
if BCM_DIR not in sys.path:
    sys.path.insert(0, BCM_DIR)

def _ensure_bcm_dependencies():
    import subprocess
    required = {
        "yfinance": "yfinance>=0.2.54",
        "OpenSSL": "pyopenssl",
        "google.protobuf": "protobuf",
        "grpc_tools": "grpcio-tools",
        "scipy": "scipy",
        "mplfinance": "mplfinance",
        "plotly": "plotly",
        "fredapi": "fredapi"
    }
    missing = []
    for module_name, pip_name in required.items():
        try:
            __import__(module_name)
        except ImportError:
            missing.append(pip_name)
    if missing:
        logger.info(f"Installing missing BCM dependencies: {missing}")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--break-system-packages", *missing])
            logger.info("BCM dependencies installed successfully.")
        except Exception as e:
            logger.warning(f"Failed to install BCM dependencies {missing}: {e}")

_ensure_bcm_dependencies()


def _run_async(coro):
    """Run async coro from a sync context safely."""
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=20)
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"bcm _run_async error: {e}")
        return {"error": str(e)}

# Schemas
BCM_TOOLS = [
    {
        "name": "ctrader_get_balance",
        "description": "Получить баланс и свободную маржу торгового счета cTrader (Pepperstone).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "ctrader_get_positions",
        "description": "Получить список всех открытых позиций на счете cTrader.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "ctrader_get_spot_prices",
        "description": "Получить текущие bid/ask котировки с Pepperstone cTrader для одного или нескольких символов по их ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Массив ID символов, например [10028, 10053] для BTC и SpotBrent"
                }
            },
            "required": ["symbol_ids"]
        }
    },
    {
        "name": "bcm_graphrag_ask",
        "description": "Запросить историческую аналитику, сетапы, трейды и лог сделок из базы знаний Pride-GraphRAG по названию тикера или паттерну.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Вопрос или поисковый запрос (например: 'Логика по SPY в апреле 2024')"},
                "channel": {"type": "string", "description": "Фильтр канала: 'pride-premium' или 'trading-plan' (необязательно)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "ctrader_place_order",
        "description": "Открыть новую рыночную сделку (BUY/SELL) с указанием объема, SL и TP. Side: 1=BUY, 2=SELL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol_id": {"type": "integer", "description": "Идентификатор символа (например: 10028 для BTC, 2 для GBPUSD)"},
                "side": {"type": "integer", "description": "Сторона сделки: 1 = BUY, 2 = SELL"},
                "volume": {"type": "number", "description": "Объем сделки (например: 0.01 лота для BTC)"},
                "stop_loss": {"type": "number", "description": "Уровень Stop Loss (необязательно)"},
                "take_profit": {"type": "number", "description": "Уровень Take Profit (необязательно)"}
            },
            "required": ["symbol_id", "side", "volume"]
        }
    },
    {
        "name": "ctrader_close_position",
        "description": "Закрыть существующую открытую позицию по её ID. Side: 1=BUY (закрываемая позиция), 2=SELL.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "position_id": {"type": "integer", "description": "Идентификатор открытой позиции"},
                "symbol_id": {"type": "integer", "description": "Идентификатор символа"},
                "side": {"type": "integer", "description": "Сторона сделки открытой позиции: 1 = BUY, 2 = SELL"},
                "volume": {"type": "number", "description": "Объем закрываемой части (лоты)"}
            },
            "required": ["position_id", "symbol_id", "side", "volume"]
        }
    },
    {
        "name": "ctrader_amend_sltp",
        "description": "Изменить уровни Stop Loss и/или Take Profit для существующей открытой позиции.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "position_id": {"type": "integer", "description": "Идентификатор позиции"},
                "stop_loss": {"type": "number", "description": "Новый уровень Stop Loss (необязательно)"},
                "take_profit": {"type": "number", "description": "Новый уровень Take Profit (необязательно)"}
            },
            "required": ["position_id"]
        }
    },
    {
        "name": "bcm_calculate_remizov_shift",
        "description": "Рассчитать показатель волатильности 2-го порядка (Remizov Shift) для указанного символа Yahoo Finance.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Yahoo Finance тикер символа, например: BTC-USD, GBPUSD=X"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "bcm_get_technical_indicators",
        "description": "Получить технические индикаторы (RSI, MACD и скользящие средние) для указанного символа.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Тикер символа Yahoo Finance (например: BTC-USD, BZ=F)"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "bcm_get_market_experience",
        "description": "Найти похожие исторические рыночные условия и результаты сделок в локальной векторной базе знаний Qdrant.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Тикер символа Yahoo Finance"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "bcm_run_autonomous_cycle",
        "description": "Запустить полный цикл автоматического анализа и исполнения сделок по алгоритму BCM для указанного символа.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Код символа BCM (например: BTC, GBPUSD, US500, BRENT)"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "bybit_get_balance",
        "description": "Получить баланс торгового аккаунта Bybit (UNIFIED, SPOT, CONTRACT).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "account_type": {"type": "string", "description": "Тип аккаунта: UNIFIED (по умолчанию), SPOT, CONTRACT"}
            }
        }
    },
    {
        "name": "bybit_get_positions",
        "description": "Получить открытые позиции на Bybit (фьючерсы linear/inverse или опционы option).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Категория: linear, option, inverse"},
                "symbol": {"type": "string", "description": "Тикер символа (например ETHUSDT)"},
                "base_coin": {"type": "string", "description": "Базовая монета (например ETH)"}
            }
        }
    },
    {
        "name": "bybit_get_options_chain",
        "description": "Получить доску опционов (Option Chain), волатильность (IV) и греки по монете (ETH, BTC).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base_coin": {"type": "string", "description": "Базовая монета: ETH или BTC (по умолчанию ETH)"},
                "exp_date": {"type": "string", "description": "Дата экспирации (необязательно, например 27DEC26)"}
            }
        }
    },
    {
        "name": "bybit_analyze_option_position",
        "description": "Рассчитать риски, точку безубыточности (Breakeven), статус ITM/OTM и сценарии PnL для опционной позиции (например проданный Put ETH 1300).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Символ опциона"},
                "strike": {"type": "number", "description": "Страйк опциона (например 1300)"},
                "option_type": {"type": "string", "description": "Тип: Put или Call"},
                "side": {"type": "string", "description": "Сторона: Sell (короткая) или Buy (длинная)"},
                "premium": {"type": "number", "description": "Полученная или уплаченная премия ($)"},
                "exp_date": {"type": "string", "description": "Месяц/дата экспирации"},
                "current_spot": {"type": "number", "description": "Текущая спотовая цена монеты (необязательно)"}
            }
        }
    },
    {
        "name": "bybit_place_order",
        "description": "Выставить ордер на Bybit (Spot, Linear Futures, Options).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Категория: spot, linear, option, inverse"},
                "symbol": {"type": "string", "description": "Торговый символ (например ETHUSDT)"},
                "side": {"type": "string", "description": "Сторона: Buy или Sell"},
                "order_type": {"type": "string", "description": "Тип ордера: Market или Limit"},
                "qty": {"type": "string", "description": "Количество"},
                "price": {"type": "string", "description": "Цена (для Limit ордеров)"},
                "stop_loss": {"type": "string", "description": "Stop Loss цена"},
                "take_profit": {"type": "string", "description": "Take Profit цена"}
            },
            "required": ["category", "symbol", "side", "qty"]
        }
    },
    {
        "name": "bybit_get_portfolio_greeks",
        "description": "Рассчитать суммарные портфельные Греки (Delta, Gamma, Theta, Vega) по всем опционам и фьючерсам.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base_coin": {"type": "string", "description": "Базовая монета: ETH или BTC (по умолчанию ETH)"}
            }
        }
    },
    {
        "name": "bybit_calc_delta_hedge",
        "description": "Рассчитать объемы ордеров для дельта-хеджирования (приведение Net Delta портфеля к 0).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base_coin": {"type": "string", "description": "Базовая монета: ETH или BTC (по умолчанию ETH)"}
            }
        }
    },
    {
        "name": "bybit_check_margin_safety",
        "description": "Провести стресс-тест маржи и запаса ликвидности с имитацией скачков цены (±5%, ±10%, ±15%).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base_coin": {"type": "string", "description": "Базовая монета: ETH или BTC (по умолчанию ETH)"}
            }
        }
    },
    {
        "name": "bybit_scan_funding_arbitrage",
        "description": "Сканировать фандинг (Funding Rate) по бессрочным фьючерсам для дельта-нейтрального арбитража Cash-and-Carry.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Категория: linear (по умолчанию)"},
                "min_annual_yield": {"type": "number", "description": "Минимальная годовая доходность % (по умолчанию 10%)"}
            }
        }
    },
    {
        "name": "bybit_emergency_close_all",
        "description": "Аварийный Kill-Switch: отменить все активные ордера и рыночно закрыть открытые позиции.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Категория: all, linear, option, spot"},
                "symbol": {"type": "string", "description": "Символ (необязательно)"}
            }
        }
    }
]

# Implementations
def handle_ctrader_get_balance(args):
    async def _action():
        from backend.mcp_client import MCPServerClient
        token = os.environ.get("CTRADER_TOKEN", "eyJwbGFudCI6InBlcHBlcnN0b25lIiwiZW52aXJvbm1lbnQiOiJkZW1vIiwidG9rZW4iOiJJV2lzRnZWNC82Q2pLdGlYdXQ1OWVZQlRUZHFlT1NPUUp0S3hZMFJmbEkwPSJ9")
        config = {
            'url': 'https://mcp.ctrader.com/trading/mcp',
            'headers': {'Authorization': f'Bearer {token}'}
        }
        client = MCPServerClient('ctrader', config)
        await client.start()
        return await client.call_tool('get_balance', {})
    return _run_async(_action())

def handle_ctrader_get_positions(args):
    async def _action():
        from backend.mcp_client import MCPServerClient
        token = os.environ.get("CTRADER_TOKEN", "eyJwbGFudCI6InBlcHBlcnN0b25lIiwiZW52aXJvbm1lbnQiOiJkZW1vIiwidG9rZW4iOiJJV2lzRnZWNC82Q2pLdGlYdXQ1OWVZQlRUZHFlT1NPUUp0S3hZMFJmbEkwPSJ9")
        config = {
            'url': 'https://mcp.ctrader.com/trading/mcp',
            'headers': {'Authorization': f'Bearer {token}'}
        }
        client = MCPServerClient('ctrader', config)
        await client.start()
        res = await client.call_tool('get_positions', {})
        if isinstance(res, str):
            try:
                import json
                res = json.loads(res)
            except:
                pass
        return res
    return _run_async(_action())

def handle_ctrader_get_spot_prices(args):
    """Fetch live bid/ask spot prices from Pepperstone cTrader for given symbol IDs.

    Args:
        args: dict with key 'symbol_ids' (list[int]) or 'symbol_id' (int/list).
              Accepts symbol names too (e.g. 'BTC', 'BRENT') and resolves via SYMBOL_MAP.

    Returns:
        dict: {
            prices: [
                {symbolId, name, bid, ask, mid, high, low, sessionClose, timestamp},
                ...
            ]
        }
    """
    # Resolve symbol_ids from args — accept list of ints, single int, or symbol names
    raw_ids = args.get("symbol_ids") or args.get("symbol_id") or []
    if isinstance(raw_ids, (int, str)):
        raw_ids = [raw_ids]

    # Build final list of integer symbol IDs
    resolved_ids = []
    for s in raw_ids:
        if isinstance(s, int):
            resolved_ids.append(s)
        elif isinstance(s, str) and s.isdigit():
            resolved_ids.append(int(s))
        else:
            # Try resolving by name using SYMBOL_MAP (populated after this function in file)
            # We use a local lookup here to avoid forward-reference
            _local_map = {
                "EURUSD": 1, "GBPUSD": 2, "EURGBP": 3, "EURJPY": 4, "USDJPY": 5,
                "AUDUSD": 6, "USDCHF": 7, "USDCAD": 8, "NZDUSD": 9,
                "BTCUSD": 10028, "BTC": 10028, "ETHUSD": 10029, "ETH": 10029,
                "XAUUSD": 10013, "GOLD": 10013, "XAGUSD": 10014, "SILVER": 10014,
                "US500": 10001, "SPX500": 10001, "NAS100": 10002, "US30": 10003,
                "BRENT": 10053, "SPOTBRENT": 10053, "OIL": 10053,
                "USOIL": 10054, "WTI": 10054, "SPOTCRUDE": 10054,
            }
            sid = _local_map.get(str(s).upper())
            if sid:
                resolved_ids.append(sid)
            else:
                logger.warning(f"handle_ctrader_get_spot_prices: unknown symbol '{s}', skipping")

    if not resolved_ids:
        # Default: return prices for the core watchlist
        resolved_ids = [10028, 10053, 10054, 10013, 1, 2]

    async def _action():
        from backend.mcp_client import MCPServerClient
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
            import json as _json
            raw = _json.loads(raw)
        return raw

    raw_result = _run_async(_action())

    # Normalise raw integer prices → human-readable floats
    # cTrader encodes all prices as integers with 5 implied decimal places (÷ 100000)
    if isinstance(raw_result, dict) and 'prices' in raw_result:
        _id_to_name = {
            10028: "BTCUSD", 10029: "ETHUSD",
            10013: "XAUUSD", 10014: "XAGUSD",
            10001: "US500",  10002: "NAS100", 10003: "US30",
            10053: "SpotBrent", 10054: "SpotCrude",
            1: "EURUSD", 2: "GBPUSD", 3: "EURGBP", 4: "EURJPY", 5: "USDJPY",
            6: "AUDUSD", 7: "USDCHF", 8: "USDCAD", 9: "NZDUSD",
        }
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
            normalised.append({
                'symbolId':     sid,
                'name':         _id_to_name.get(sid, f'ID:{sid}'),
                'bid':          bid,
                'ask':          ask,
                'mid':          mid,
                'high':         high,
                'low':          low,
                'sessionClose': sess_close,
                'timestamp':    p.get('timestamp'),
            })
        return {'prices': normalised}

    return raw_result if raw_result else {'error': 'get_spot_prices returned empty result'}

SYMBOL_MAP = {
    "EURUSD": 1, "GBPUSD": 2, "EURGBP": 3, "EURJPY": 4, "USDJPY": 5, "AUDUSD": 6, "USDCHF": 7, "USDCAD": 8, "NZDUSD": 9,
    "BTCUSD": 10028, "BTC": 10028, "ETHUSD": 10029, "ETH": 10029,
    "XAUUSD": 10013, "GOLD": 10013, "XAGUSD": 10014, "SILVER": 10014,
    "US500": 10001, "SPX500": 10001, "NAS100": 10002, "US100": 10002, "US30": 10003,
    "BRENT": 10053, "SPOTBRENT": 10053, "OIL": 10053,
    "USOIL": 10054, "WTI": 10054, "SPOTCRUDE": 10054,
    # US Stock & ETF CFDs on Pepperstone
    "AMZN": 10098, "AMZN.US": 10098,
    "GOOGL": 11621, "GOOGL.US": 11621, "GOOG": 10101, "GOOG.US": 10101,
    "AAPL": 10099, "AAPL.US": 10099,
    "NVDA": 10104, "NVDA.US": 10104,
    "TSLA": 10105, "TSLA.US": 10105,
    "MSFT": 10097, "MSFT.US": 10097,
    "META": 10100, "META.US": 10100,
    "SPY": 10118, "SPY.US": 10118,
    "QQQ": 11827, "QQQ.US": 11827,
    "USO": 11973, "USO.US": 11973,
}

# ---------------------------------------------------------------------------
# Price divisors: cTrader raw integer price → float price
# cTrader sends prices as integers with 5 decimal places of precision:
#   e.g. BTCUSD:  6428304000 / 100000 = 64283.04
#        Brent:     8040500  / 100000 = 80.405
#        EURUSD:    1085420  / 100000 = 1.08542
# Most symbols use 100000 (5 dp). FX majors also use 100000.
# ---------------------------------------------------------------------------
PRICE_DIVISOR: dict[int, int] = {
    10028: 100000,  # BTCUSD
    10029: 100000,  # ETHUSD
    10053: 100000,  # SpotBrent
    10054: 100000,  # SpotCrude/WTI
    10013: 100000,  # XAUUSD (Gold)
    10014: 100000,  # XAGUSD (Silver)
    10001: 100000,  # US500
    10002: 100000,  # NAS100
    10003: 100000,  # US30
    # FX pairs
    1: 100000, 2: 100000, 3: 100000, 4: 100000, 5: 100000,
    6: 100000, 7: 100000, 8: 100000, 9: 100000,
}
DEFAULT_PRICE_DIVISOR = 100000

# Volume conversion: cTrader API units → lots
# Empirically derived from live account data:
#   SpotBrent (10053): volume=600 → 0.06 lots  → factor=10000
#   BTCUSD   (10028): volume=1   → 0.01 lots  → factor=100
VOLUME_FACTOR = {
    # Crypto CFDs: 1 lot = 1 coin, step 0.01, API units = lots × 100
    10028: 100,   # BTCUSD
    10029: 100,   # ETHUSD
    # Commodity CFDs: 1 lot = 100 barrels/oz, step 0.01, API units = lots × 10000
    10053: 10000, # SpotBrent
    10054: 10000, # SpotCrude/WTI
    10013: 10000, # XAUUSD (Gold)
    10014: 10000, # XAGUSD (Silver)
    # Index CFDs
    10001: 100,   # US500
    10002: 100,   # NAS100
    10003: 100,   # US30
}
FX_VOLUME_FACTOR = 100000  # FX pairs: 1 lot = 100,000 base currency units

# Reverse lookup: symbolId → canonical display name
SYMBOL_ID_TO_NAME = {
    1: "EURUSD", 2: "GBPUSD", 3: "EURGBP", 4: "EURJPY", 5: "USDJPY",
    6: "AUDUSD", 7: "USDCHF", 8: "USDCAD", 9: "NZDUSD",
    10028: "BTCUSD", 10029: "ETHUSD",
    10013: "XAUUSD", 10014: "XAGUSD",
    10001: "US500", 10002: "NAS100", 10003: "US30",
    10053: "SpotBrent",  # Brent Crude — NOT USOIL/WTI
    10054: "SpotCrude",  # WTI Crude — NOT Brent
}


def format_live_positions_guardrail(positions_data: dict) -> str:
    """Convert raw cTrader positions JSON into an authoritative guardrail string.

    Converts internal volume units → lots using VOLUME_FACTOR per symbolId,
    adds the canonical symbol name, and formats for LLM injection.
    Returns a plain-text block to prepend to the bcm_orchestrator prompt.
    """
    positions = positions_data.get("positions", []) if isinstance(positions_data, dict) else []
    orders = positions_data.get("orders", []) if isinstance(positions_data, dict) else []

    if not positions:
        return (
            "[LIVE CTRADER POSITIONS — AUTHORITATIVE]\n"
            "NO OPEN POSITIONS. Account is flat. Do NOT invent any positions.\n"
        )

    lines = ["[LIVE CTRADER POSITIONS — AUTHORITATIVE]",
             "These are the ONLY real open positions. Do NOT invent or hallucinate any others.",
             ""]
    for i, p in enumerate(positions, 1):
        sym_id = p.get("symbolId", "?")
        sym_name = SYMBOL_ID_TO_NAME.get(sym_id, f"ID:{sym_id}")
        factor = VOLUME_FACTOR.get(sym_id, FX_VOLUME_FACTOR)
        raw_vol = p.get("volume", 0)
        lots = round(raw_vol / factor, 4)
        side = p.get("tradeSide", "?")
        entry = p.get("entryPrice", "?")
        sl = p.get("stopLoss", "none")
        tp = p.get("takeProfit", "none")
        pos_id = p.get("positionId", "?")
        lines.append(
            f"  Position {i}: {sym_name} (symbolId={sym_id}, positionId={pos_id})"
        )
        lines.append(
            f"    {side} {lots} lots | Entry: {entry} | SL: {sl} | TP: {tp}"
        )
    if orders:
        lines.append("")
        lines.append(f"  Pending orders: {len(orders)} (STOP orders on SpotBrent)")
    lines.append("")
    lines.append("CRITICAL: Use EXACTLY the above symbol names, lot sizes, and prices.")
    lines.append("Do NOT use USOIL for SpotBrent. Do NOT fabricate lot sizes.")
    lines.append("")
    return "\n".join(lines)


def handle_ctrader_place_order(args):
    try:
        import subprocess
        sym_arg = str(args.get("symbol_id") or args.get("symbol") or "10028")
        if not sym_arg.isdigit():
            sym_id = SYMBOL_MAP.get(sym_arg.upper(), 10028)
        else:
            sym_id = int(sym_arg)
        
        raw_side = str(args.get("side", 1)).upper()
        side_val = "1" if raw_side in ("1", "BUY") else "2"
        volume = float(args.get("volume", 0.01))
        sl = args.get("stop_loss") or args.get("sl")
        tp = args.get("take_profit") or args.get("tp")

        cmd = [sys.executable, os.path.join(BCM_DIR, "pepperstone_trader.py"), "place", str(sym_id), side_val, str(volume)]
        if sl: cmd.append(str(sl))
        if tp: cmd.append(str(tp))

        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = (res.stdout + res.stderr).strip()
        logger.info(f"Pepperstone FIX place_order output: {output}")

        # Auto-attach SL/TP to Position object via MCP amend_position so cTrader UI populates SL/TP columns
        if (sl or tp) and ("FILLED" in output or "accepted" in output or res.returncode == 0):
            try:
                import time
                time.sleep(1)
                pos_data = handle_ctrader_get_positions({})
                positions = pos_data.get("positions", []) if isinstance(pos_data, dict) else []
                target_pos = None
                for p in positions:
                    if p.get("symbolId") == sym_id:
                        target_pos = p
                        break
                if target_pos and target_pos.get("positionId"):
                    amend_args = {"position_id": target_pos["positionId"]}
                    if sl: amend_args["stop_loss"] = float(sl)
                    if tp: amend_args["take_profit"] = float(tp)
                    handle_ctrader_amend_sltp(amend_args)
                    logger.info(f"Auto-applied SL/TP ({sl}/{tp}) to positionId {target_pos['positionId']} via cTrader MCP")
            except Exception as e_amend:
                logger.warning(f"Auto SL/TP amend failed: {e_amend}")

        if "FILLED" in output or "accepted" in output or res.returncode == 0:
            return {"status": "success", "executed": True, "details": output}
        else:
            return {"status": "failed", "executed": False, "error": output}
    except Exception as e:
        logger.error(f"Failed to execute Pepperstone FIX place_order: {e}")
        return {"status": "failed", "error": str(e)}

def handle_ctrader_close_position(args):
    try:
        import subprocess
        order_id = str(args.get("position_id") or args.get("order_id") or "1")
        sym_arg = str(args.get("symbol_id") or args.get("symbol") or "10028")
        if not sym_arg.isdigit():
            sym_id = SYMBOL_MAP.get(sym_arg.upper(), 10028)
        else:
            sym_id = int(sym_arg)
            
        raw_side = str(args.get("side", 1)).upper()
        side_val = "1" if raw_side in ("1", "BUY") else "2"
        volume = float(args.get("volume", 0.01))

        cmd = [sys.executable, os.path.join(BCM_DIR, "pepperstone_trader.py"), "close", order_id, str(sym_id), side_val, str(volume)]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        output = (res.stdout + res.stderr).strip()
        logger.info(f"Pepperstone FIX close_position output: {output}")
        return {"status": "success", "details": output}
    except Exception as e:
        logger.error(f"Failed to execute Pepperstone FIX close_position: {e}")
        return {"status": "failed", "error": str(e)}

def handle_ctrader_amend_sltp(args):
    async def _action():
        from backend.mcp_client import MCPServerClient
        token = os.environ.get("CTRADER_TOKEN", "eyJwbGFudCI6InBlcHBlcnN0b25lIiwiZW52aXJvbm1lbnQiOiJkZW1vIiwidG9rZW4iOiJJV2lzRnZWNC82Q2pLdGlYdXQ1OWVZQlRUZHFlT1NPUUp0S3hZMFJmbEkwPSJ9")
        config = {
            'url': 'https://mcp.ctrader.com/trading/mcp',
            'headers': {'Authorization': f'Bearer {token}'}
        }
        client = MCPServerClient('ctrader', config)
        await client.start()
        
        pos_id = int(args.get("position_id") or args.get("positionId") or 0)
        sl = args.get("stop_loss") or args.get("stopLoss") or args.get("sl")
        tp = args.get("take_profit") or args.get("takeProfit") or args.get("tp")
        
        params = {"positionId": pos_id}
        if sl is not None:
            params["stopLoss"] = float(sl)
        if tp is not None:
            params["takeProfit"] = float(tp)
            
        res = await client.call_tool('amend_position', params)
        if isinstance(res, str):
            try:
                import json
                res = json.loads(res)
            except:
                pass
        return {"status": "success", "details": res}
    return _run_async(_action())

YF_SYMBOL_MAP = {
    "BTCUSD": "BTC-USD", "BTC": "BTC-USD",
    "ETHUSD": "ETH-USD", "ETH": "ETH-USD",
    "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "EURGBP": "EURGBP=X", "EURJPY": "EURJPY=X", "USDJPY": "JPY=X", "AUDUSD": "AUDUSD=X", "USDCHF": "CHF=X", "USDCAD": "CAD=X", "NZDUSD": "NZDUSD=X",
    "XAUUSD": "GC=F", "GOLD": "GC=F", "XAGUSD": "SI=F", "SILVER": "SI=F",
    "US500": "^GSPC", "SPX500": "^GSPC", "NAS100": "^NDX", "US100": "^NDX", "US30": "^DJI",
    "BRENT": "BZ=F", "WTI": "CL=F", "USOIL": "CL=F", "OIL": "BZ=F",
    # US Stock & ETF CFDs
    "AMZN": "AMZN", "AMZN.US": "AMZN",
    "GOOGL": "GOOGL", "GOOGL.US": "GOOGL", "GOOG": "GOOG", "GOOG.US": "GOOG",
    "AAPL": "AAPL", "AAPL.US": "AAPL",
    "NVDA": "NVDA", "NVDA.US": "NVDA",
    "TSLA": "TSLA", "TSLA.US": "TSLA",
    "MSFT": "MSFT", "MSFT.US": "MSFT",
    "META": "META", "META.US": "META",
    "SPY": "SPY", "SPY.US": "SPY",
    "QQQ": "QQQ", "QQQ.US": "QQQ",
    "USO": "USO", "USO.US": "USO",
}

def _normalize_yf_symbol(symbol: str) -> str:
    s = str(symbol or "BTCUSD").upper().strip()
    s_clean = s.replace("=X", "")
    return YF_SYMBOL_MAP.get(s_clean, YF_SYMBOL_MAP.get(s, s))

def handle_bcm_calculate_remizov_shift(args):
    try:
        try:
            from backend.bcm.autonomous_trader import calculate_remizov_shift
        except ImportError:
            from autonomous_trader import calculate_remizov_shift
        import yfinance as yf
        raw_symbol = args.get("symbol")
        yf_symbol = _normalize_yf_symbol(raw_symbol)
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period="30d", interval="1d")
        shift, _ = calculate_remizov_shift(df)
        return {"symbol": raw_symbol, "yf_symbol": yf_symbol, "remizov_shift": shift}
    except Exception as e:
        return {"error": str(e)}

def handle_bcm_get_technical_indicators(args):
    try:
        try:
            from backend.bcm.autonomous_trader import get_technical_analysis
        except ImportError:
            from autonomous_trader import get_technical_analysis
        raw_symbol = args.get("symbol")
        yf_symbol = _normalize_yf_symbol(raw_symbol)
        analysis = get_technical_analysis(yf_symbol)
        if isinstance(analysis, str):
            return json.loads(analysis)
        return analysis
    except Exception as e:
        return {"error": str(e)}

def handle_bcm_get_market_experience(args):
    try:
        try:
            from backend.bcm.autonomous_trader import get_technical_analysis, calculate_remizov_shift, calculate_atr_keltner
            from backend.bcm.memory_manager import BCMMemory
        except ImportError:
            from autonomous_trader import get_technical_analysis, calculate_remizov_shift, calculate_atr_keltner
            from memory_manager import BCMMemory
        import yfinance as yf
        raw_symbol = args.get("symbol")
        yf_symbol = _normalize_yf_symbol(raw_symbol)
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period="30d", interval="1d")
        tech_json = get_technical_analysis(yf_symbol)
        tech_data = json.loads(tech_json) if isinstance(tech_json, str) else tech_json
        shift, _ = calculate_remizov_shift(df)
        atr_data = calculate_atr_keltner(yf_symbol)
        
        context = {
            "rsi": list(tech_data.get("rsi", {}).values())[0] if tech_data.get("rsi") else 50.0,
            "remizov_shift": shift,
            "ema_dist": 0.0,
            "macd_hist": list(tech_data.get("macdhist", {}).values())[0] if tech_data.get("macdhist") else 0.0,
            "atr": atr_data.get("atr_d1", 1.0),
            "keltner_upper_dist": 0.0,
            "keltner_lower_dist": 0.0
        }
        mem = BCMMemory()
        results = mem.get_similar_experience(context)
        return {"symbol": raw_symbol, "yf_symbol": yf_symbol, "experiences": results}
    except Exception as e:
        return {"error": str(e)}

def handle_bcm_run_autonomous_cycle(args):
    try:
        from autonomous_trader import run_autonomous_cycle, format_any_bcm_response
        import io
        import sys
        import re
        symbol = args.get("symbol")
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()
        try:
            run_autonomous_cycle(symbol)
        finally:
            sys.stdout = old_stdout
        raw_output = buffer.getvalue()
        raw_output = format_any_bcm_response(raw_output, symbol=symbol or "BTC")
        return {"success": True, "output": raw_output}
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_graphrag_query(args: dict) -> dict:
    """Query Pride-GraphRAG Q&A API (http://localhost:8088/api/v1/analytics/ask).

    Args:
        args: {"query": str, "channel": Optional[str]}

    Returns:
        dict: API response with synthesized answer and source citations
    """
    query = args.get("query", "")
    channel = args.get("channel")
    if not query:
        return {"error": "Query parameter is required"}

    import requests
    default_host = "host.docker.internal" if os.path.exists("/.dockerenv") else "localhost"
    default_url = f"http://{default_host}:8088/api/v1/analytics/ask"
    url = os.environ.get("GRAPHRAG_API_URL", default_url)
    payload = {"query": query}
    if channel:
        payload["channel"] = channel

    timeout_val = int(args.get("timeout", 60))
    try:
        resp = requests.post(url, json=payload, timeout=timeout_val)
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"GraphRAG API returned HTTP {resp.status_code}: {resp.text[:300]}"}
    except Exception as e:
        if "localhost" in url or "127.0.0.1" in url:
            alt_url = url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
            try:
                resp = requests.post(alt_url, json=payload, timeout=timeout_val)
                if resp.status_code == 200:
                    return resp.json()
                return {"error": f"GraphRAG API returned HTTP {resp.status_code}: {resp.text[:300]}"}
            except Exception:
                pass
        logger.warning(f"GraphRAG API error: {e}")
        return {"error": f"Failed to connect to Pride-GraphRAG API ({url}): {e}"}


# ── Bybit Handlers ────────────────────────────────────────────────
_bybit_client = None

def _get_bybit_client():
    global _bybit_client
    if _bybit_client is None:
        try:
            from backend.bcm.bybit_trader import BybitTrader
        except ImportError:
            from bybit_trader import BybitTrader
        _bybit_client = BybitTrader()
    return _bybit_client

def handle_bybit_get_balance(args: dict) -> dict:
    account_type = args.get("account_type", "UNIFIED")
    client = _get_bybit_client()
    return client.get_wallet_balance(account_type=account_type)

def handle_bybit_get_positions(args: dict) -> dict:
    category = args.get("category", "linear")
    symbol = args.get("symbol")
    base_coin = args.get("base_coin")
    client = _get_bybit_client()
    return client.get_positions(category=category, symbol=symbol, base_coin=base_coin)

def handle_bybit_get_options_chain(args: dict) -> dict:
    base_coin = args.get("base_coin", "ETH")
    exp_date = args.get("exp_date")
    client = _get_bybit_client()
    return client.get_option_chain(base_coin=base_coin, exp_date=exp_date)

def handle_bybit_analyze_option_position(args: dict) -> dict:
    symbol = args.get("symbol", "ETH-DEC26-1300-P")
    strike = float(args.get("strike", 1300.0))
    option_type = args.get("option_type", "Put")
    side = args.get("side", "Sell")
    premium = float(args.get("premium", 0.0))
    exp_date = args.get("exp_date", "December")
    current_spot = float(args.get("current_spot", 0.0))
    client = _get_bybit_client()
    return client.analyze_option_position(
        symbol=symbol,
        strike=strike,
        option_type=option_type,
        side=side,
        premium=premium,
        exp_date=exp_date,
        current_spot=current_spot
    )

def handle_bybit_place_order(args: dict) -> dict:
    category = args.get("category", "spot")
    symbol = args.get("symbol")
    side = args.get("side")
    order_type = args.get("order_type", "Market")
    qty = str(args.get("qty"))
    price = args.get("price")
    sl = args.get("stop_loss")
    tp = args.get("take_profit")
    if not symbol or not side or not qty:
        return {"error": "symbol, side, and qty parameters are required"}
    client = _get_bybit_client()
    return client.place_order(
        category=category,
        symbol=symbol,
        side=side,
        order_type=order_type,
        qty=qty,
        price=price,
        sl=sl,
        tp=tp
    )

def handle_bybit_get_portfolio_greeks(args: dict) -> dict:
    base_coin = args.get("base_coin", "ETH")
    client = _get_bybit_client()
    return client.get_portfolio_greeks(base_coin=base_coin)

def handle_bybit_calc_delta_hedge(args: dict) -> dict:
    base_coin = args.get("base_coin", "ETH")
    client = _get_bybit_client()
    return client.calc_delta_hedge(base_coin=base_coin)

def handle_bybit_check_margin_safety(args: dict) -> dict:
    base_coin = args.get("base_coin", "ETH")
    client = _get_bybit_client()
    return client.check_margin_safety(base_coin=base_coin)

def handle_bybit_scan_funding_arbitrage(args: dict) -> dict:
    category = args.get("category", "linear")
    min_annual_yield = float(args.get("min_annual_yield", 10.0))
    client = _get_bybit_client()
    return client.scan_funding_arbitrage(category=category, min_annual_yield=min_annual_yield)

def handle_bybit_emergency_close_all(args: dict) -> dict:
    category = args.get("category", "all")
    symbol = args.get("symbol")
    client = _get_bybit_client()
    return client.emergency_close_all(category=category, symbol=symbol)


# Main router
def bcm_execute_tool(name: str, arguments: dict) -> str:
    logger.info(f"BCM local tool router: {name} with {arguments}")
    
    if name == "ctrader_get_balance":
        res = handle_ctrader_get_balance(arguments)
    elif name == "ctrader_get_positions":
        res = handle_ctrader_get_positions(arguments)
    elif name == "ctrader_get_spot_prices":
        res = handle_ctrader_get_spot_prices(arguments)
    elif name == "ctrader_place_order":
        res = handle_ctrader_place_order(arguments)
    elif name == "ctrader_close_position":
        res = handle_ctrader_close_position(arguments)
    elif name == "ctrader_amend_sltp":
        res = handle_ctrader_amend_sltp(arguments)
    elif name == "bcm_calculate_remizov_shift":
        res = handle_bcm_calculate_remizov_shift(arguments)
    elif name == "bcm_get_technical_indicators":
        res = handle_bcm_get_technical_indicators(arguments)
    elif name == "bcm_get_market_experience":
        res = handle_bcm_get_market_experience(arguments)
    elif name == "bcm_graphrag_ask":
        res = handle_graphrag_query(arguments)
    elif name == "bcm_run_autonomous_cycle":
        res = handle_bcm_run_autonomous_cycle(arguments)
    elif name == "bybit_get_balance":
        res = handle_bybit_get_balance(arguments)
    elif name == "bybit_get_positions":
        res = handle_bybit_get_positions(arguments)
    elif name == "bybit_get_options_chain":
        res = handle_bybit_get_options_chain(arguments)
    elif name == "bybit_analyze_option_position":
        res = handle_bybit_analyze_option_position(arguments)
    elif name == "bybit_place_order":
        res = handle_bybit_place_order(arguments)
    elif name == "bybit_get_portfolio_greeks":
        res = handle_bybit_get_portfolio_greeks(arguments)
    elif name == "bybit_calc_delta_hedge":
        res = handle_bybit_calc_delta_hedge(arguments)
    elif name == "bybit_check_margin_safety":
        res = handle_bybit_check_margin_safety(arguments)
    elif name == "bybit_scan_funding_arbitrage":
        res = handle_bybit_scan_funding_arbitrage(arguments)
    elif name == "bybit_emergency_close_all":
        res = handle_bybit_emergency_close_all(arguments)
    else:
        res = {"error": f"Tool {name} not supported by BCM local router."}
        
    return json.dumps(res, ensure_ascii=False)


