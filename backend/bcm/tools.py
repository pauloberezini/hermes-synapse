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
        "grpc_tools": "grpcio-tools"
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
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            logger.info("BCM dependencies installed successfully.")
        except Exception as e:
            logger.error(f"Failed to install BCM dependencies {missing}: {e}")

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

SYMBOL_MAP = {
    "EURUSD": 1, "GBPUSD": 2, "EURGBP": 3, "EURJPY": 4, "USDJPY": 5, "AUDUSD": 6, "USDCHF": 7, "USDCAD": 8, "NZDUSD": 9,
    "BTCUSD": 10028, "BTC": 10028, "ETHUSD": 10029, "ETH": 10029,
    "XAUUSD": 10013, "GOLD": 10013, "XAGUSD": 10014, "SILVER": 10014,
    "US500": 10001, "SPX500": 10001, "NAS100": 10002, "US100": 10002, "US30": 10003,
    "BRENT": 10053, "SPOTBRENT": 10053, "OIL": 10053,
    "WTI": 10054, "SPOTCRUDE": 10054,
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
    "BRENT": "BZ=F", "WTI": "CL=F", "OIL": "BZ=F",
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
        symbol = args.get("symbol")
        ticker = yf.Ticker(symbol)
        df = ticker.history(period="30d", interval="1d")
        tech_json = get_technical_analysis(symbol)
        tech_data = json.loads(tech_json) if isinstance(tech_json, str) else tech_json
        shift, _ = calculate_remizov_shift(df)
        atr_data = calculate_atr_keltner(symbol)
        
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
        return {"symbol": symbol, "experiences": results}
    except Exception as e:
        return {"error": str(e)}

def handle_bcm_run_autonomous_cycle(args):
    try:
        from autonomous_trader import run_autonomous_cycle
        import io
        import sys
        symbol = args.get("symbol")
        old_stdout = sys.stdout
        sys.stdout = buffer = io.StringIO()
        try:
            run_autonomous_cycle(symbol)
        finally:
            sys.stdout = old_stdout
        return {"success": True, "output": buffer.getvalue()}
    except Exception as e:
        return {"success": False, "error": str(e)}

# Main router
def bcm_execute_tool(name: str, arguments: dict) -> str:
    logger.info(f"BCM local tool router: {name} with {arguments}")
    
    if name == "ctrader_get_balance":
        res = handle_ctrader_get_balance(arguments)
    elif name == "ctrader_get_positions":
        res = handle_ctrader_get_positions(arguments)
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
    elif name == "bcm_run_autonomous_cycle":
        res = handle_bcm_run_autonomous_cycle(arguments)
    else:
        res = {"error": f"Tool {name} not supported by BCM local router."}
        
    return json.dumps(res, ensure_ascii=False)
