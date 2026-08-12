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

# ─── Symbol Normalization ─────────────────────────────────────────────────────
# FIX / cTrader Symbol IDs
SYMBOL_MAP = {
    "EURUSD": 1,
    "GBPUSD": 2,
    "EURGBP": 3,
    "USDJPY": 4,
    "USDCHF": 5,
    "USDCAD": 6,
    "AUDUSD": 7,
    "NZDUSD": 8,
    "EURJPY": 9,
    "GBPJPY": 10,
    "XAUUSD": 41,
    "GOLD": 41,
    "XAGUSD": 42,
    "SILVER": 42,
    "US500": 10013,
    "SPX": 10013,
    "BTCUSD": 10028,
    "BTC": 10028,
    "ETHUSD": 10029,
    "ETH": 10029,
    "BRENT": 10053,
    "OIL": 10053,
    "USOIL": 10054,
    "WTI": 10054,
    "AMZN": 20001,
    "GOOGL": 20002,
    "NVDA": 20003,
    "TSLA": 20004,
    "AAPL": 20005,
    "MSFT": 20006,
    "META": 20007,
    "SPY": 20008,
    "QQQ": 20009,
    "USO": 20010,
}

# Maps BCM internal symbol names → Yahoo Finance tickers
YF_SYMBOL_MAP = {
    "EURUSD":  "EURUSD=X",
    "GBPUSD":  "GBPUSD=X",
    "USDJPY":  "USDJPY=X",
    "AUDUSD":  "AUDUSD=X",
    "USDCHF":  "USDCHF=X",
    "USDCAD":  "USDCAD=X",
    "NZDUSD":  "NZDUSD=X",
    "EURGBP":  "EURGBP=X",
    "EURJPY":  "EURJPY=X",
    "GBPJPY":  "GBPJPY=X",
    "GOLD":    "GC=F",
    "XAUUSD":  "GC=F",
    "SILVER":  "SI=F",
    "XAGUSD":  "SI=F",
    "BRENT":   "BZ=F",
    "OIL":     "BZ=F",
    "USOIL":   "CL=F",
    "WTI":     "CL=F",
    "US500":   "^GSPC",
    "SPX":     "^GSPC",
    "NDX":     "^NDX",
    "NAS100":  "^NDX",
    "DJI":     "^DJI",
    "BTCUSD":  "BTC-USD",
    "BTC":     "BTC-USD",
    "ETHUSD":  "ETH-USD",
    "ETH":     "ETH-USD",
    "SOL":     "SOL-USD",
    "AMZN":    "AMZN",
    "GOOGL":   "GOOGL",
    "NVDA":    "NVDA",
    "TSLA":    "TSLA",
    "AAPL":    "AAPL",
    "MSFT":    "MSFT",
    "META":    "META",
    "SPY":     "SPY",
    "QQQ":     "QQQ",
    "USO":     "USO",
}
_YF_SYMBOL_MAP = YF_SYMBOL_MAP

def _normalize_yf_symbol(symbol: str) -> str:
    """Convert a BCM/cTrader symbol name to its Yahoo Finance ticker equivalent."""
    if not symbol:
        return symbol
    upper = symbol.upper().replace("/", "").replace("-SPOT", "")
    return _YF_SYMBOL_MAP.get(upper, symbol)


# ─── cTrader Lot-Size Factors ─────────────────────────────────────────────────
# Raw cTrader volumes are in units; divide by these to get standard lots.
FX_VOLUME_FACTOR = 100_000   # 1 standard FX lot = 100,000 units
VOLUME_FACTOR = {            # Symbol-specific overrides (cTrader symbolId → factor)
    10028: 1,       # BTC (already in BTC)
    10053: 1_000,   # SpotBrent (1 lot = 1,000 barrels)
    41:    100,     # Gold XAU
    42:    5_000,   # Silver XAG
    10013: 1,       # US500
    2:     100_000, # GBPUSD
    1:     100_000, # EURUSD
}

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
        "name": "bcm_analytics_ask",
        "description": "Запросить историческую аналитику, сетапы, трейды и лог сделок из базы знаний по названию тикера или паттерну.",
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
        "description": "Запустить полный цикл автоматического анализа и исполнения сделок по алгоритму BCM для указанного символа (Forex/Crypto через Pepperstone cTrader).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Код символа BCM (например: BTC, GBPUSD, US500, BRENT, XAGUSD)"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "bcm_run_bybit_options_cycle",
        "description": "Запустить автономный цикл торговли опционами BCM на Bybit. Анализирует рынок, выбирает оптимальный спред (Put-спред, Call-спред, Iron Condor), проверяет через Compliance Officer и РЕАЛЬНО исполняет обе ноги спреда через Bybit API.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base_coin": {"type": "string", "description": "Базовая монета: BTC или ETH (по умолчанию BTC)"},
                "exp_date": {"type": "string", "description": "Дата экспирации в формате Bybit (например 27DEC26). Если не указана — система выберет лучшую сама."}
            },
            "required": []
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

def handle_bcm_calculate_remizov_shift(args):
    try:
        try:
            from backend.bcm.autonomous_trader import calculate_remizov_shift, _fetch_yahoo_direct
        except ImportError:
            from autonomous_trader import calculate_remizov_shift, _fetch_yahoo_direct
        raw_symbol = args.get("symbol")
        yf_symbol = _normalize_yf_symbol(raw_symbol)
        df = _fetch_yahoo_direct(yf_symbol, period="30d", interval="1d")
        if df.empty:
            return {"error": f"No data for {yf_symbol}"}
        shift, resolvent = calculate_remizov_shift(df)
        return {"symbol": raw_symbol, "yf_symbol": yf_symbol, "remizov_shift": shift, "resolvent": resolvent}
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


def handle_exchange_run_options_cycle(args):
    """Run the autonomous options spread cycle for BTC or ETH."""
    try:
        from backend.bcm.autonomous_trader import run_options_cycle
        import io
        import sys
        base_coin = args.get("base_coin", "BTC").upper()
        exp_date = args.get("exp_date")
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()
        try:
            result = run_options_cycle(base_coin=base_coin, exp_date=exp_date)
        finally:
            sys.stdout = old_stdout
        log_output = buffer.getvalue()
        return {"success": True, "result": result, "log": log_output[-3000:] if len(log_output) > 3000 else log_output}
    except Exception as e:
        return {"success": False, "error": str(e)}


def handle_analytics_query(args: dict) -> dict:
    """Query the configured analytics backend for playbooks or retrospectives.

    Args:
        args: {"query": str, "channel": Optional[str], "timeout": Optional[int]}

    Returns:
        dict: API response with synthesized answer and source citations
    """
    query = args.get("query", "")
    channel = args.get("channel")
    timeout_val = int(args.get("timeout", 60))

    try:
        from backend.bcm.analytics_factory import AnalyticsFactory
    except ImportError:
        from analytics_factory import AnalyticsFactory
        
    provider = AnalyticsFactory.get_provider()
    return provider.query_playbook(query=query, channel=channel, timeout=timeout_val)


# ── Generic Exchange Handlers (via Factory) ───────────────────────
def _get_spot_broker():
    try:
        from backend.bcm.exchange_factory import ExchangeFactory
    except ImportError:
        from exchange_factory import ExchangeFactory
    return ExchangeFactory.get_spot_broker()

def _get_options_broker():
    try:
        from backend.bcm.exchange_factory import ExchangeFactory
    except ImportError:
        from exchange_factory import ExchangeFactory
    return ExchangeFactory.get_options_broker()

def handle_exchange_get_balance(args: dict) -> dict:
    account_type = args.get("account_type", "UNIFIED")
    broker = _get_spot_broker()
    return broker.get_wallet_balance(account_type=account_type)

def handle_exchange_get_positions(args: dict) -> dict:
    category = args.get("category", "linear")
    symbol = args.get("symbol")
    base_coin = args.get("base_coin")
    broker = _get_spot_broker()
    return broker.get_positions(category=category, symbol=symbol, base_coin=base_coin)

def handle_exchange_get_spot_prices(args: dict) -> dict:
    symbols = args.get("symbols", ["BTCUSD"])
    if not isinstance(symbols, list):
        symbols = [symbols]
    broker = _get_spot_broker()
    return broker.get_spot_prices(symbols=symbols)

def handle_exchange_get_options_chain(args: dict) -> dict:
    base_coin = args.get("base_coin", "ETH")
    exp_date = args.get("exp_date")
    broker = _get_options_broker()
    return broker.get_option_chain(base_coin=base_coin, exp_date=exp_date)

def handle_exchange_analyze_option_position(args: dict) -> dict:
    symbol = args.get("symbol", "ETH-DEC26-1300-P")
    strike = float(args.get("strike", 1300.0))
    option_type = args.get("option_type", "Put")
    side = args.get("side", "Sell")
    premium = float(args.get("premium", 0.0))
    exp_date = args.get("exp_date", "December")
    current_spot = float(args.get("current_spot", 0.0))
    broker = _get_options_broker()
    return broker.analyze_option_position(
        symbol=symbol,
        strike=strike,
        option_type=option_type,
        side=side,
        premium=premium,
        exp_date=exp_date,
        current_spot=current_spot
    )

def handle_exchange_place_order(args: dict) -> dict:
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
    broker = _get_spot_broker()
    return broker.place_order(
        category=category,
        symbol=symbol,
        side=side,
        order_type=order_type,
        qty=qty,
        price=price,
        sl=sl,
        tp=tp
    )

def handle_exchange_get_portfolio_greeks(args: dict) -> dict:
    base_coin = args.get("base_coin", "ETH")
    broker = _get_options_broker()
    return broker.get_portfolio_greeks(base_coin=base_coin)

def handle_exchange_calc_delta_hedge(args: dict) -> dict:
    base_coin = args.get("base_coin", "ETH")
    broker = _get_options_broker()
    return broker.calc_delta_hedge(base_coin=base_coin)

def handle_exchange_check_margin_safety(args: dict) -> dict:
    base_coin = args.get("base_coin", "ETH")
    broker = _get_options_broker()
    return broker.check_margin_safety(base_coin=base_coin)

def handle_exchange_scan_funding_arbitrage(args: dict) -> dict:
    category = args.get("category", "linear")
    min_annual_yield = float(args.get("min_annual_yield", 10.0))
    # Needs a specific arbitrage broker or spot broker depending on features, assuming spot for now
    broker = _get_spot_broker()
    if hasattr(broker, "scan_funding_arbitrage"):
        return broker.scan_funding_arbitrage(category=category, min_annual_yield=min_annual_yield)
    return {"status": "error", "message": "Method scan_funding_arbitrage not supported by current broker."}

def handle_exchange_emergency_close_all(args: dict) -> dict:
    category = args.get("category", "all")
    symbol = args.get("symbol")
    broker = _get_spot_broker()
    if hasattr(broker, "emergency_close_all"):
        return broker.emergency_close_all(category=category, symbol=symbol)
    return {"status": "error", "message": "Method emergency_close_all not supported by current broker."}


# Main router
def bcm_execute_tool(name: str, arguments: dict) -> str:
    logger.info(f"BCM local tool router: {name} with {arguments}")
    
    if name in ("ctrader_get_balance", "exchange_get_balance", "bybit_get_balance"):
        res = handle_exchange_get_balance(arguments)
    elif name in ("ctrader_get_positions", "exchange_get_positions", "bybit_get_positions"):
        res = handle_exchange_get_positions(arguments)
    elif name in ("ctrader_get_spot_prices", "exchange_get_spot_prices"):
        res = handle_exchange_get_spot_prices(arguments)
    elif name in ("ctrader_place_order", "exchange_place_order", "bybit_place_order"):
        res = handle_exchange_place_order(arguments)
    elif name in ("ctrader_close_position", "exchange_close_position", "bybit_close_position"):
        # We need a generic close_position handler if needed, but for now map it to emergency close or placeholder
        res = handle_exchange_emergency_close_all(arguments)
    elif name == "bcm_calculate_remizov_shift":
        res = handle_bcm_calculate_remizov_shift(arguments)
    elif name == "bcm_get_technical_indicators":
        res = handle_bcm_get_technical_indicators(arguments)
    elif name == "bcm_get_market_experience":
        res = handle_bcm_get_market_experience(arguments)
    elif name == "bcm_analytics_ask" or name == "bcm_graphrag_ask":
        res = handle_analytics_query(arguments)
    elif name == "bcm_run_autonomous_cycle":
        res = handle_bcm_run_autonomous_cycle(arguments)
    elif name == "exchange_run_options_cycle" or name == "bcm_run_bybit_options_cycle":
        res = handle_exchange_run_options_cycle(arguments)
    elif name == "exchange_get_options_chain" or name == "bybit_get_options_chain":
        res = handle_exchange_get_options_chain(arguments)
    elif name == "exchange_analyze_option_position" or name == "bybit_analyze_option_position":
        res = handle_exchange_analyze_option_position(arguments)
    elif name == "exchange_get_portfolio_greeks" or name == "bybit_get_portfolio_greeks":
        res = handle_exchange_get_portfolio_greeks(arguments)
    elif name == "exchange_calc_delta_hedge" or name == "bybit_calc_delta_hedge":
        res = handle_exchange_calc_delta_hedge(arguments)
    elif name == "exchange_check_margin_safety" or name == "bybit_check_margin_safety":
        res = handle_exchange_check_margin_safety(arguments)
    elif name == "exchange_scan_funding_arbitrage" or name == "bybit_scan_funding_arbitrage":
        res = handle_exchange_scan_funding_arbitrage(arguments)
    elif name == "exchange_emergency_close_all" or name == "bybit_emergency_close_all":
        res = handle_exchange_emergency_close_all(arguments)
    else:
        res = {"error": f"Tool {name} not supported by BCM local router."}
        
    return json.dumps(res, ensure_ascii=False)


# ─── Compatibility shims (legacy names used by autonomous_trader.py) ──────────
# These were renamed to handle_exchange_* during refactoring.
# Keep these aliases so autonomous_trader.py doesn't need a full rewrite.

def handle_ctrader_get_balance(args: dict) -> dict:
    """Compatibility alias → handle_exchange_get_balance."""
    return handle_exchange_get_balance(args)

def handle_ctrader_get_positions(args: dict) -> dict:
    """Compatibility alias → handle_exchange_get_positions."""
    return handle_exchange_get_positions(args)

def handle_ctrader_get_spot_prices(args: dict) -> dict:
    """Compatibility alias → handle_exchange_get_spot_prices."""
    return handle_exchange_get_spot_prices(args)

def handle_ctrader_place_order(args: dict) -> dict:
    """Compatibility alias → handle_exchange_place_order."""
    return handle_exchange_place_order(args)

def handle_ctrader_close_position(args: dict) -> dict:
    """Compatibility alias → handle_exchange_emergency_close_all."""
    return handle_exchange_emergency_close_all(args)


def format_live_positions_guardrail(pos_data: dict) -> str:
    """Format live cTrader/exchange positions into a strict prompt guardrail string."""
    if not pos_data or "error" in pos_data or not isinstance(pos_data, dict):
        return "\n[WARNING: Live account positions unavailable — proceed with caution]\n"

    positions = pos_data.get("positions", [])
    if not positions:
        return (
            "\n--- REAL-TIME CTRADER ACCOUNT POSITIONS ---\n"
            "ACTIVE POSITIONS: NONE (0 open trades)\n"
            "CRITICAL MANDATE: No positions are currently open. Do NOT assume or hallucinate open trades.\n"
            "-------------------------------------------\n"
        )

    lines = ["--- REAL-TIME CTRADER ACCOUNT POSITIONS ---"]
    for p in positions:
        sym = p.get("symbol", "UNKNOWN")
        side = p.get("side", "BUY")
        vol = p.get("volume", p.get("qty", 0))
        entry = p.get("entry_price", p.get("price", 0))
        pnl = p.get("unrealized_pnl", p.get("pnl", 0))
        lines.append(f"• {side} {vol} {sym} @ {entry} (Unrealized PnL: ${pnl:+.2f})")
    lines.append("CRITICAL MANDATE: Only evaluate the positions listed above.")
    lines.append("-------------------------------------------")
    return "\n" + "\n".join(lines) + "\n"

