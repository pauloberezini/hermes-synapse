import pandas as pd
import requests

import sys
import os

BCM_DIR = os.path.dirname(os.path.abspath(__file__))
if BCM_DIR not in sys.path:
    sys.path.insert(0, BCM_DIR)
INDICATORS_DIR = os.path.join(BCM_DIR, "indicators")
if INDICATORS_DIR not in sys.path:
    sys.path.insert(0, INDICATORS_DIR)

import subprocess
import json

import time
import threading
from datetime import datetime

try:
    from backend.bcm.memory_manager import BCMMemory
except ImportError:
    from memory_manager import BCMMemory

try:
    from backend.bcm.compliance_officer import ComplianceOfficer
except ImportError:
    from compliance_officer import ComplianceOfficer

try:
    from dotenv import load_dotenv
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    load_dotenv(env_path)
except ImportError:
    pass

# Initialize Memory
memory = BCMMemory()

# Self-healing DNS for Amvera environment
try:
    # Use sudo if possible, or direct echo as root
    dns_cmd = "echo 'nameserver 127.0.0.11' > /etc/resolv.conf; echo 'nameserver 1.1.1.1' >> /etc/resolv.conf; echo 'nameserver 8.8.8.8' >> /etc/resolv.conf; echo 'options ndots:0' >> /etc/resolv.conf"
    subprocess.run(["bash", "-c", dns_cmd], capture_output=True)
except Exception as de:
    print(f"DNS Fix Warning: {de}")

# Configuration
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
MODEL = os.environ.get("BCM_MODEL", os.environ.get("LLM_MODEL", "deepseek/deepseek-chat"))

def israel_time():
    """Return current Israel time string (IDT/IST)."""
    from datetime import datetime, timezone, timedelta
    israel_tz = timezone(timedelta(hours=3))  # IDT = UTC+3
    now = datetime.now(israel_tz)
    return now.strftime("%d/%m %H:%M IDT")

def get_market_session():
    """Returns the current active global market session and its expected volatility based on UTC time."""
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    hour = now_utc.hour
    
    if 13 <= hour < 16:
        # 13:00 - 16:00 UTC is the overlap between London and NY (highest volatility)
        return "London & NY Overlap (EXTREME VOLATILITY - Expect large institutional moves and fakeouts)"
    elif 16 <= hour < 20:
        return "New York Session (HIGH VOLATILITY - Trend continuation or afternoon reversals)"
    elif 8 <= hour < 13:
        return "London Session (HIGH VOLATILITY - Establishing the daily trend)"
    elif 0 <= hour < 8:
        return "Asian Session (LOW VOLATILITY - Ranging, consolidation, mean-reverting)"
    else:
        return "Late NY / Sydney Session (VERY LOW VOLATILITY - Market is quiet, spreads may widen)"

try:
    from backend.bcm.notifications import get_notifier
except ImportError:
    from notifications import get_notifier

def extract_json(text):
    """Safely extract the FIRST JSON (object or list) from a noisy string."""
    try:
        # Find first occurrence of either { or [
        start_obj = text.find('{')
        start_list = text.find('[')
        
        if start_obj == -1 and start_list == -1: return None
        
        if start_list != -1 and (start_obj == -1 or start_list < start_obj):
            # It's likely a list
            start = start_list
            bracket_type = 'list'
        else:
            # It's likely an object
            start = start_obj
            bracket_type = 'obj'
            
        # Find the matching closing bracket
        # This is a simple balance check, not full-blown parser
        open_b = '[' if bracket_type == 'list' else '{'
        close_b = ']' if bracket_type == 'list' else '}'
        
        count = 0
        end = -1
        for i in range(start, len(text)):
            if text[i] == open_b:
                count += 1
            elif text[i] == close_b:
                count -= 1
                if count == 0:
                    end = i + 1
                    break
        
        if start != -1 and end > start:
            return text[start:end]
        return None
    except:
        return None


def _fetch_yahoo_direct(ticker, period="60d", interval="1d"):
    

    url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval={interval}&range={period}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    for attempt in range(3):
        try:
            print('  >>> GET', url); r = requests.get(url, headers=headers, timeout=(5,5)); print('  >>> GOT', r.status_code)
            if r.status_code == 200:
                data = r.json()['chart']['result'][0]
                timestamps = data['timestamp']
                quote = data['indicators']['quote'][0]
                df = pd.DataFrame({
                    'Open': quote['open'],
                    'High': quote['high'],
                    'Low': quote['low'],
                    'Close': quote['close'],
                    'Volume': quote.get('volume', [0]*len(timestamps))
                }, index=pd.to_datetime(timestamps, unit='s'))
                df.dropna(subset=['Close'], inplace=True)
                return df
        except Exception:
            pass
        import time; time.sleep(1)
    return pd.DataFrame()

def get_technical_analysis(ticker):
    """Fetch RSI/MACD/Bollinger technicals locally using yfinance and advanced BCM indicators."""
    import yfinance as yf

    try:
        try:
            from backend.bcm.tools import _normalize_yf_symbol
        except ImportError:
            try:
                from tools import _normalize_yf_symbol
            except ImportError:
                _normalize_yf_symbol = lambda s: s
        ticker = _normalize_yf_symbol(ticker)
        print(f"DEBUG: Fetching yfinance data for {ticker}...")
        
        
        
        # Changed to 1h interval over 60 days for a strong swing-trading macro structure
        df = _fetch_yahoo_direct(ticker, period="60d", interval="1h")
        if df.empty:
            raise ValueError(f"No data for {ticker}")
        
        # Calculate RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # Calculate MACD
        exp1 = df['Close'].ewm(span=12, adjust=False).mean()
        exp2 = df['Close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macdhist'] = df['macd'] - df['signal']
        
        last = df.iloc[-1]
        
        res = {
            "rsi": {ticker: float(last['rsi'].iloc[0] if isinstance(last['rsi'], pd.Series) else last['rsi'])},
            "macd": {ticker: float(last['macd'].iloc[0] if isinstance(last['macd'], pd.Series) else last['macd'])},
            "macdhist": {ticker: float(last['macdhist'].iloc[0] if isinstance(last['macdhist'], pd.Series) else last['macdhist'])},
            "close": {ticker: float(last['Close'].iloc[0] if isinstance(last['Close'], pd.Series) else last['Close'])}
        }
        
        # === Advanced Indicators (Volume Profile & VWAP) ===
        try:
            from backend.bcm.indicators.volume_profile import VolumeProfile
            from backend.bcm.indicators.models_utils.profile_models import DistributionData
            from backend.bcm.indicators.multi_vwap import MultiVwap
            import numpy as np
            
            # Prepare dataframe for indicators (lowercase columns)
            df_ind = df.copy()
            # If MultiIndex columns (like yfinance sometimes does), flatten them
            if isinstance(df_ind.columns, pd.MultiIndex):
                df_ind.columns = [c[0].lower() for c in df_ind.columns]
            else:
                df_ind.columns = [c.lower() for c in df_ind.columns]
                
            # Strip timezone from index to avoid VWAP comparison errors
            if df_ind.index.tz is not None:
                df_ind.index = df_ind.index.tz_localize(None)
                
            if 'volume' not in df_ind.columns or (df_ind['volume'] == 0).all():
                df_ind['volume'] = 1.0 # Failsafe for forex data without volume
                
            rng = df_ind['high'].max() - df_ind['low'].min()
            row_height = max(rng / 100.0, 0.0001)
            
            # VWAP
            try:
                mvwap = MultiVwap(df_ind)
                df_vwap = mvwap.daily(df_ind)
                daily_vwap = float(df_vwap['daily_vwap_median'].iloc[-1])
                res["vwap"] = {"daily": daily_vwap}
            except Exception as ve:
                print(f"VWAP calc error: {ve}")
                
            # Volume Profile
            try:
                # Limit to last 14 days for swing-trading volume profile resolution
                last_time = df_ind.index[-1]
                df_vp = df_ind[df_ind.index >= last_time - pd.Timedelta(days=14)].copy()
                
                vp = VolumeProfile(df_vp, None, row_height, pd.Timedelta(days=14), DistributionData.OHLC_No_Avg, with_plotly_columns=False)
                # VP outputs list of intervals, list of profiles
                _, df_profiles = vp.normal() 
                if len(df_profiles) > 0:
                    last_prof = df_profiles[-1]
                    if 'vp_prices' in last_prof.columns and 'vp_normal' in last_prof.columns:
                        prices = last_prof['vp_prices'].values
                        volumes = last_prof['vp_normal'].values
                        if len(volumes) > 0:
                            poc_idx = np.argmax(volumes)
                            poc = float(prices[poc_idx])
                            res["volume_profile"] = {"poc": poc}
            except Exception as vpe:
                print(f"VP calc error: {vpe}")
                
        except Exception as adv_e:
            print(f"Advanced indicators skip: {adv_e}")

        return json.dumps(res)
    except Exception as e:
        print(f"⚠️ yfinance Technical Analysis Error: {e}")
        return json.dumps({"rsi": {ticker: 50.0}, "warning": str(e)})

script_dir = os.path.dirname(os.path.abspath(__file__))

# Mapping between Analysis Ticker (Yahoo format) and Trading ID (Exchange Exchange format)
TICKER_MAP = {
    "BTC": {"analysis": "BTC-USD", "trade_id": 10028, "volume": 0.01},
    "GBPUSD": {"analysis": "GBPUSD=X", "trade_id": 2, "volume": 1000},
    "EURUSD": {"analysis": "EURUSD=X", "trade_id": 1, "volume": 1000},
    "US500": {"analysis": "^GSPC", "trade_id": 10013, "volume": 0.1},
    "BRENT": {"analysis": "BZ=F", "trade_id": 10053, "volume": 1},
    "OIL": {"analysis": "BZ=F", "trade_id": 10053, "volume": 1},
    "GOLD": {"analysis": "GC=F", "trade_id": 41, "volume": 1},
    "XAUUSD": {"analysis": "GC=F", "trade_id": 41, "volume": 1},
    "SILVER": {"analysis": "SI=F", "trade_id": 42, "volume": 1},
    "XAGUSD": {"analysis": "SI=F", "trade_id": 42, "volume": 1},
}

def get_live_exchange_positions():
    """Fetch live positions from Exchange Exchange API via tools module."""
    try:
        try:
            from backend.bcm.tools import handle_exchange_get_positions, VOLUME_FACTOR, FX_VOLUME_FACTOR
        except ImportError:
            from tools import handle_exchange_get_positions, VOLUME_FACTOR, FX_VOLUME_FACTOR
            
        res = handle_exchange_get_positions({})
        if isinstance(res, str):
            try:
                res = json.loads(res)
            except Exception:
                pass
        
        positions = []
        if isinstance(res, dict):
            positions = res.get("positions", res.get("data", []))
        elif isinstance(res, list):
            positions = res
            
        if not isinstance(positions, list) or len(positions) == 0:
            return [], "LIVE EXCHANGE OPEN POSITIONS: NONE (0 open positions)."

        # Enrich positions with live spot prices from Exchange
        sym_ids = list({p.get("symbolId") or p.get("symbol_id") for p in positions
                        if p.get("symbolId") or p.get("symbol_id")})
        live_prices = get_live_spot_prices(sym_ids) if sym_ids else {}

        formatted_positions = []
        for p in positions:
            sym_id = p.get("symbolId") or p.get("symbol_id")
            pos_id = p.get("positionId") or p.get("id")
            trade_side = "BUY" if str(p.get("tradeSide") or p.get("side")) in ("1", "BUY", "BUY_SIDE") else "SELL"
            # Convert raw volume units -> lots using per-symbol VOLUME_FACTOR
            raw_vol = p.get("volume", 0)
            factor = VOLUME_FACTOR.get(sym_id, FX_VOLUME_FACTOR)
            vol = round(raw_vol / factor, 4)
            entry = p.get("entryPrice", p.get("price", 0))
            # Use live mid/bid price as current_price; fall back to entry price
            live_p = live_prices.get(sym_id, {})
            current = live_p.get("mid") or live_p.get("bid") or p.get("currentPrice", entry)
            sl = p.get("stopLoss")
            tp = p.get("takeProfit")
            pnl = p.get("unrealizedPnl", p.get("pnl", 0))
            
            sym_name = f"Symbol-{sym_id}"
            for k, v in TICKER_MAP.items():
                if v.get("trade_id") == sym_id:
                    sym_name = k
                    break

            formatted_positions.append({
                "symbol": sym_name,
                "symbol_id": sym_id,
                "position_id": pos_id,
                "side": trade_side,
                "volume": vol,
                "entry_price": entry,
                "current_price": current,
                "sl": sl,
                "tp": tp,
                "unrealized_pnl": pnl
            })

        summary = f"LIVE EXCHANGE OPEN POSITIONS ({len(formatted_positions)} active):\n"
        for item in formatted_positions:
            summary += f"• {item['symbol']} (ID: {item['position_id']}): {item['side']} {item['volume']} lots @ Entry: {item['entry_price']} | Current: {item['current_price']} | SL: {item['sl']} | TP: {item['tp']} | PnL: ${item['unrealized_pnl']}\n"
            
        return formatted_positions, summary
    except Exception as e:
        print(f"⚠️ Error fetching live Exchange positions: {e}")
        return [], f"LIVE EXCHANGE OPEN POSITIONS: Unavailable ({str(e)})"


def get_live_spot_prices(symbol_ids: list = None):
    """
    Request current bid/ask quotes directly from Exchange.

    Returns:
        dict: {symbolId: {'bid': float, 'ask': float, 'mid': float, 'name': str}, ...}
    """
    if symbol_ids is None:
        # Default watchlist: BTC, SpotBrent, Gold, Silver, US500
        symbol_ids = [10028, 10053, 41, 42, 10013]
    try:
        try:
            from backend.bcm.tools import handle_exchange_get_spot_prices
        except ImportError:
            from tools import handle_exchange_get_spot_prices

        res = handle_exchange_get_spot_prices({"symbol_ids": symbol_ids})
        if isinstance(res, str):
            res = json.loads(res)

        price_map = {}
        for p in res.get("prices", []):
            sid = p.get("symbolId")
            if sid:
                price_map[sid] = {
                    "bid":  p.get("bid"),
                    "ask":  p.get("ask"),
                    "mid":  p.get("mid"),
                    "high": p.get("high"),
                    "low":  p.get("low"),
                    "name": p.get("name", f"ID:{sid}"),
                }
        return price_map
    except Exception as e:
        return {}

def check_liquidity_layer_0(symbol: str) -> dict:
    """
    Cognitive Cycle v5.0 - Layer 0: Liquidity & Market Structure.
    Checks spread, active trading session, and sweeps before allowing LLM/Tech analysis.
    Returns: {"passed": bool, "reason": str, "spread": float}
    """
    import datetime
    now_utc = datetime.datetime.utcnow()
    hour = now_utc.hour

    # 1. Simple Session check (avoiding dead zones like 21:00-23:00 UTC for FX)
    if "EURUSD" in symbol or "GBPUSD" in symbol or "GOLD" in symbol or "XAU" in symbol:
        if 21 <= hour <= 23:
            return {"passed": False, "reason": f"Dead zone (Hour {hour} UTC). Low liquidity.", "spread": 0}

    # 2. Check live spread via Exchange if available
    try:
        trade_id = None
        for k, v in TICKER_MAP.items():
            if k == symbol or v.get("analysis") == symbol:
                trade_id = v.get("trade_id")
                break
        
        if trade_id:
            prices = get_live_spot_prices([trade_id])
            if trade_id in prices:
                p = prices[trade_id]
                bid = p.get("bid")
                ask = p.get("ask")
                if bid and ask:
                    spread = ask - bid
                    
                    # Hardcoded spread thresholds
                    max_spread = 2.0
                    if "EURUSD" in symbol or "GBPUSD" in symbol:
                        max_spread = 0.00030 # 3 pips max
                    elif "BTC" in symbol:
                        max_spread = 50.0
                    elif "GOLD" in symbol or "XAU" in symbol:
                        max_spread = 0.50 # 50 cents max

                    if spread > max_spread:
                        return {"passed": False, "reason": f"Spread too high: {spread:.5f} (max {max_spread})", "spread": spread}
                    
                    return {"passed": True, "reason": "Liquidity OK", "spread": spread}
    except Exception as e:
        print(f"Layer 0 Spread check error: {e}")
        pass

    return {"passed": True, "reason": "Liquidity assumed OK", "spread": 0}

def get_global_macro_metrics() -> str:
    """Fetch live VIX and Ten Year Yield via yfinance for macro context."""
    import yfinance as yf
    try:
        # Fetch ^VIX and ^TNX (10Y Yield)
        vix_df = yf.Ticker("^VIX").history(period="1d")
        tnx_df = yf.Ticker("^TNX").history(period="1d")
        
        vix_val = round(vix_df['Close'].iloc[-1], 2) if not vix_df.empty else "Unavailable"
        tnx_val = round(tnx_df['Close'].iloc[-1], 2) if not tnx_df.empty else "Unavailable"
        
        return f"VIX (Volatility Index): {vix_val}\nUS 10Y Treasury Yield: {tnx_val}%"
    except Exception as e:
        print(f"Error fetching global macro metrics: {e}")
        return "Global Macro Metrics (VIX/10Y): Unavailable"

def get_fred_macro_regime() -> str:
    """Fetch structural macro data from FRED (Fed Funds Rate, Balance Sheet)."""
    import os
    try:
        from fredapi import Fred
    except ImportError:
        return "FRED API module not installed."
        
    # Use the explicitly provided key or environment variable
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        return "FRED API Key missing."
        
    try:
        fred = Fred(api_key=api_key)
        
        # Effective Federal Funds Rate (Cost of Capital)
        fedfunds = fred.get_series('FEDFUNDS').iloc[-1]
        
        # Total Assets of the Federal Reserve (Liquidity) - expressed in Millions, convert to Trillions
        walcl_raw = fred.get_series('WALCL').iloc[-1]
        walcl_trillions = round(walcl_raw / 1_000_000, 2)
        
        return (
            f"Effective Federal Funds Rate: {round(fedfunds, 2)}%\n"
            f"Federal Reserve Total Assets (Liquidity): ${walcl_trillions} Trillion"
        )
    except Exception as e:
        print(f"Error fetching FRED macro regime: {e}")
        return "FRED Macro Regime: Unavailable"

def get_fred_intraday_filters() -> str:
    """Fetch daily FRED risk metrics and today's economic releases."""
    import os
    
    from datetime import datetime
    
    api_key = os.getenv("FRED_API_KEY")
    if not api_key:
        return ""
        
    try:
        from fredapi import Fred
        fred = Fred(api_key=api_key)
        
        # 1. Fetch Daily Risk Metrics
        # SOFR
        sofr = fred.get_series('SOFR').iloc[-1]
        # High Yield Spread
        hy_spread = fred.get_series('BAMLH0A0HYM2').iloc[-1]
        # NFCI
        nfci = fred.get_series('NFCI').iloc[-1]
        
        risk_block = (
            f"Secured Overnight Financing Rate (SOFR): {round(sofr, 2)}%\n"
            f"High Yield Corporate Bond Spread: {round(hy_spread, 2)}%\n"
            f"Chicago Fed NFCI (Financial Conditions): {round(nfci, 2)}"
        )
        
        # 2. Fetch Today's Releases (Economic Calendar)
        today_str = datetime.now().strftime("%Y-%m-%d")
        url = f"https://api.stlouisfed.org/fred/releases/dates?api_key={api_key}&file_type=json&realtime_start={today_str}&realtime_end={today_str}"
        response = requests.get(url, timeout=5)
        data = response.json()
        
        calendar_block = "No major economic releases scheduled for today."
        if 'release_dates' in data and len(data['release_dates']) > 0:
            releases = []
            for r in data['release_dates'][:5]:  # Limit to top 5
                rel_id = r.get('release_id')
                if rel_id:
                    # Fetch release name
                    r_url = f"https://api.stlouisfed.org/fred/release?api_key={api_key}&file_type=json&release_id={rel_id}"
                    r_resp = requests.get(r_url, timeout=2).json()
                    name = r_resp.get('releases', [{}])[0].get('name', 'Unknown Release')
                    releases.append(f"- {name} (ID: {rel_id})")
            
            if releases:
                calendar_block = "WARNING: Major economic data releases today:\n" + "\n".join(releases)
                
        return f"{risk_block}\n\n{calendar_block}"
    except Exception as e:
        print(f"Error fetching FRED intraday filters: {e}")
        return "FRED Intraday Filters: Unavailable"

def get_macro_terminal_context(ticker: str) -> str:
    """Fetch live news, sentiment, and macro context from Macro Terminal MCP server."""
    try:
        from backend.mcp_client import MCPServerClient
        import asyncio

        config = {'url': 'http://localhost:8100/mcp', 'headers': {}}
        client = MCPServerClient('macro-terminal', config)

        async def _fetch():
            await client.start()
            blocks = []
            # 1. Ticker specific news
            try:
                raw_news = await client.call_tool('macro_get_ai_ticker_news', {'ticker': ticker})
                if raw_news:
                    blocks.append(f"TICKER NEWS & SENTIMENT ({ticker}):\n{str(raw_news)[:1500]}")
            except Exception as _ne:
                print(f"⚠️ Macro Terminal ticker news error: {_ne}")

            # 2. General news sentiment summary
            try:
                raw_sent = await client.call_tool('macro_get_sentiment_summary', {})
                if raw_sent:
                    blocks.append(f"MARKET SENTIMENT SUMMARY:\n{str(raw_sent)[:1000]}")
            except Exception as _se:
                print(f"⚠️ Macro Terminal sentiment error: {_se}")

            return "\n\n".join(blocks)

        # Run async call safely
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    return pool.submit(lambda: asyncio.run(_fetch())).result(timeout=10)
            else:
                return loop.run_until_complete(_fetch())
        except Exception:
            return asyncio.run(_fetch())
    except Exception as e:
        print(f"⚠️ Macro Terminal context fetch error: {e}")
        return ""


def fetch_analytics_playbook(ticker: str) -> str:
    """Fetch historical trading channel playbook & retrospectives from analytics provider."""
    try:
        notifier = get_notifier()
        
        try:
            from backend.bcm.exchange_factory import ExchangeFactory
        except ImportError:
            from exchange_factory import ExchangeFactory
            
        broker = ExchangeFactory.get_spot_broker()
        try:
            options_broker = ExchangeFactory.get_options_broker()
        except ValueError:
            options_broker = broker # fallback if options not supported, we'll handle below
            
        try:
            from backend.bcm.tools import handle_analytics_query
        except ImportError:
            from tools import handle_analytics_query
            
        res = handle_analytics_query({"query": f"Историческая логика, сетапы и результаты по {ticker}"})
        if res and isinstance(res, dict) and "answer" in res:
            return res["answer"]
        return ""
    except Exception as e:
        raise e
        return ""


# Per-role AI model selection (overrideable via environment variables)
DEFAULT_MODEL = os.environ.get("BCM_MODEL", os.environ.get("LLM_MODEL", "deepseek/deepseek-chat"))
ROLE_MODELS = {
    "Quant Analyst": os.environ.get("BCM_MODEL_QUANT", DEFAULT_MODEL),
    "Macro Analyst": os.environ.get("BCM_MODEL_MACRO", DEFAULT_MODEL),
    "Risk Manager": os.environ.get("BCM_MODEL_RISK", DEFAULT_MODEL),
    "Managing Director": os.environ.get("BCM_MODEL_MD", DEFAULT_MODEL),
    "Options Strategist": os.environ.get("BCM_MODEL_OPTIONS", DEFAULT_MODEL),
}

# Role-specific institutional system pre-prompts
ROLE_SYSTEM_PROMPTS = {
    "Quant Analyst": (
        "You are the Lead Quantitative & Technical Analyst at Berezini Capital Management (BCM). "
        "Your mandate is to perform rigorous swing-trading technical analysis and momentum assessment. "
        "Focus exclusively on multi-day to multi-week structures. Ignore intraday noise. "
        "Analyze daily/weekly indicators (RSI, ATR), macro liquidity pools, structural price shifts, and historical setup patterns. "
        "Provide a data-driven report with major swing support/resistance zones, macro trend bias, and swing momentum signals."
    ),
    "Macro Analyst": (
        "You are the Senior Macro & Geopolitical Strategist at Berezini Capital Management (BCM). "
        "Your mandate is to evaluate global macroeconomic drivers, central bank interest rate policies, energy market trends, "
        "and live news sentiment from Berezini Macro Terminal. "
        "Provide a clear macro risk assessment (Bullish / Bearish / Neutral) suitable for a swing trader, highlighting tail-risk events."
    ),
    "Risk Manager": (
        "You are the Chief Risk Officer (CRO) at Berezini Capital Management (BCM). "
        "Your sole mandate is capital preservation and drawdown prevention for a Swing Trading portfolio. "
        "You MUST verify that SL/TP levels are wide enough to withstand normal daily volatility (using Daily ATR), "
        "check for a minimum 1:1.5 Risk-to-Reward ratio, review active open positions to prevent duplicate exposure, and veto any short-term or high-risk setup."
    ),
    "Managing Director": (
        "You are the Managing Director & Chief Investment Officer (CIO) at Berezini Capital Management (BCM). "
        "Your mandate is executive portfolio leadership for a pure Swing Trading fund (holding positions for days to weeks). "
        "You synthesize multi-agent inputs and continuous learning from trade execution outcomes. "
        "You MUST produce a comprehensive, detailed, in-depth analytical breakdown covering: "
        "1. ACCOUNT & PORTFOLIO HEALTH: Detailed audit of Balance, Equity, Margin Usage, Free Margin, and Floating PnL. "
        "2. ACTIVE POSITIONS & ORDERS AUDIT: Thorough evaluation of every open trade, volume, entry vs current price, SL/TP safety. "
        "3. HISTORICAL CLOSED TRADES & LEARNING: Analysis of past completed trades, realized PnL, win-rate %, and lessons learned from past mistakes. "
        "4. MULTI-AGENT SYNTHESIS: Cross-referencing Quant Analyst, Macro Analyst, and Risk Manager reports. "
        "5. EXECUTIVE ACTION PLAN: A binding decision ('buy'|'sell'|'wait') with a detailed, in-depth reasoning essay and confidence rating. "
        "Your output MUST be valid JSON with keys: 'decision', 'reasoning', 'confidence', 'account_summary', 'recommended_sl', 'recommended_tp'."
    ),
    "Options Strategist": (
        "You are the Senior Options Strategist at Berezini Capital Management (BCM), specializing in Bitcoin and Ethereum derivatives. "
        "Your mandate is to design and execute institutional-grade options spread strategies. "
        "CORE PRINCIPLES: "
        "1. SELL PREMIUM when IV is elevated (IV > 50%). Prefer Put Spreads in bullish/neutral regimes. "
        "2. ALWAYS use defined-risk spreads (Put Spread or Call Spread). NEVER recommend naked options. "
        "3. Strikes must be OTM: Sell-leg at least 5% below spot (Puts) or 5% above spot (Calls). Buy-leg 8-12% from spot. "
        "4. Max loss must be < 2% of account equity. "
        "5. Target net credit > 0 (credit spread). If market structure makes credit impossible, output strategy='wait'. "
        "OUTPUT FORMAT: You MUST respond with ONLY a valid JSON object (no markdown, no extra text): "
        "{ "
        "  \"strategy\": \"put_spread|call_spread|iron_condor|wait\", "
        "  \"reasoning\": \"concise essay on why this setup qualifies\", "
        "  \"confidence\": 0-100, "
        "  \"sell_leg\": {\"symbol\": \"BTC-27DEC26-63000-P\", \"side\": \"Sell\", \"qty\": \"1\", \"price\": \"2200\"}, "
        "  \"buy_leg\": {\"symbol\": \"BTC-27DEC26-60000-P\", \"side\": \"Buy\", \"qty\": \"1\", \"price\": \"1100\"}, "
        "  \"net_credit_usd\": 1100, "
        "  \"max_loss_usd\": 1900, "
        "  \"breakeven_price\": 61900 "
        "} "
        "If strategy is 'wait', the sell_leg and buy_leg can be null. "
        "CRITICAL: If you output strategy='wait', do NOT hallucinate order execution. The system will NOT place any orders."
    ),
}


# Rate Limiting & Concurrency Control for OpenRouter API Calls
BCM_MAX_CONCURRENT_LLM = int(os.environ.get("BCM_MAX_CONCURRENT_LLM", "2"))
LLM_SEMAPHORE = threading.Semaphore(BCM_MAX_CONCURRENT_LLM)
LLM_MIN_DELAY_SECONDS = 0.5


def call_llm(role_name, prompt):
    """Generic helper to call LLM with a specific role, system pre-prompt, targeted model, retries, and rate limiting."""
    headers = {"Content-Type": "application/json"}
    
    api_key = OPENROUTER_API_KEY
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
        
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Select role-specific model and system prompt
    model_to_use = ROLE_MODELS.get(role_name, DEFAULT_MODEL)
    sys_prompt = ROLE_SYSTEM_PROMPTS.get(
        role_name,
        f"You are the {role_name} at Berezini Capital Management. Current Time: {current_time}"
    )
    full_system_content = f"{sys_prompt}\n\nCurrent UTC Time: {current_time}"

    payload = {
        "model": model_to_use,
        "messages": [
            {"role": "system", "content": full_system_content},
            {"role": "user", "content": prompt}
        ]
    }

    max_retries = 3
    last_error = ""

    with LLM_SEMAPHORE:
        time.sleep(LLM_MIN_DELAY_SECONDS)
        for attempt in range(1, max_retries + 1):
            try:
                # Fallback to local LLM endpoint if no API_BASE provided and no API_KEY
                base_url = os.environ.get('LLM_API_BASE')
                if not base_url:
                    base_url = 'https://openrouter.ai/api/v1' if api_key else 'http://localhost:11434/v1'
                
                url = f"{base_url.rstrip('/')}/chat/completions"
                response = requests.post(url, headers=headers, json=payload, timeout=60)
                
                if response.status_code != 200:
                    try:
                        err_json = response.json()
                        err_msg = err_json.get("error", {}).get("message", response.text)
                    except Exception:
                        err_msg = response.text
                    last_error = f"HTTP {response.status_code}: {err_msg}"
                    if response.status_code in [429, 500, 502, 503, 504] and attempt < max_retries:
                        time.sleep(attempt * 3)
                        continue
                    return f"Agent {role_name} Error: {last_error}"

                data = response.json()
                if "error" in data:
                    err_msg = data["error"].get("message", str(data["error"]))
                    last_error = err_msg
                    if attempt < max_retries:
                        time.sleep(attempt * 3)
                        continue
                    return f"Agent {role_name} Error: {err_msg}"

                choices = data.get("choices")
                if not choices or not isinstance(choices, list):
                    last_error = "Empty or missing choices in response"
                    if attempt < max_retries:
                        time.sleep(attempt * 2)
                        continue
                    return f"Agent {role_name} Error: {last_error}"

                content = choices[0].get("message", {}).get("content", "")
                if not content:
                    last_error = "Returned empty message content"
                    if attempt < max_retries:
                        time.sleep(attempt * 2)
                        continue
                    return f"Agent {role_name} returned empty content."

                return content
            except Exception as e:
                last_error = str(e)
                if attempt < max_retries:
                    time.sleep(attempt * 3)
                    continue

    return f"Agent {role_name} Error: {last_error}"


def get_completed_trades_summary(limit=10) -> str:
    """Fetch completed/closed trades history from SQLite database memory."""
    try:
        import sqlite3
        workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(workspace_root, "logs/bcm_memory.db")
        if not os.path.exists(db_path):
            return "HISTORICAL CLOSED TRADES: No recorded past trade history yet (clean database)."

        conn = sqlite3.connect(db_path)
        c = conn.cursor()
        c.execute("""
            SELECT trade_id, timestamp, symbol, side, volume, entry_price, exit_price, pnl, status, reasoning 
            FROM trades 
            WHERE status='CLOSED' OR pnl IS NOT NULL 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (limit,))
        rows = c.fetchall()

        c.execute("SELECT COUNT(*), SUM(pnl), SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) FROM trades WHERE status='CLOSED'")
        summary_row = c.fetchone()
        conn.close()

        total_closed = summary_row[0] or 0
        total_pnl = summary_row[1] or 0.0
        winning_trades = summary_row[2] or 0
        win_rate = (winning_trades / total_closed * 100.0) if total_closed > 0 else 0.0

        if not rows:
            return (
                f"HISTORICAL CLOSED TRADES SUMMARY:\n"
                f"• Total Closed Trades: {total_closed}\n"
                f"• Total Realized PnL: ${total_pnl:.2f}\n"
                f"• Historical Win Rate: {win_rate:.1f}%\n"
                f"• Status: No individual closed trade post-mortems logged yet."
            )

        trade_lines = [
            f"HISTORICAL CLOSED TRADES & LEARNING LOG (Total Closed: {total_closed}, Win Rate: {win_rate:.1f}%, Realized PnL: ${total_pnl:.2f}):"
        ]
        for r in rows:
            t_id, ts, sym, side, vol, entry, exit_p, pnl, st, reason = r
            pnl_val = pnl or 0.0
            pnl_str = f"+${pnl_val:.2f}" if pnl_val >= 0 else f"-${abs(pnl_val):.2f}"
            trade_lines.append(
                f"  • [{ts[:16]}] {sym} {side} {vol} lots | Entry: {entry} -> Exit: {exit_p} | PnL: {pnl_str} | Post-mortem/Reasoning: {reason[:150]}"
            )
        return "\n".join(trade_lines)
    except Exception as e:
        return f"⚠️ Error fetching closed trades history: {e}"


def ask_ai_decision(ticker, analysis_data):
    """A true Multi-Agent workflow: Analyst -> Risk Manager -> Managing Director."""
    _, live_pos_summary = get_live_exchange_positions()

    # Fetch live spot prices for the ticker being analysed + key watchlist symbols
    ticker_id = TICKER_MAP.get(ticker, {}).get("trade_id")
    spot_ids = [10028, 10053, 41, 42, 10013, 2, 1]  # BTC, SpotBrent, Gold, Silver, US500, GBPUSD, EURUSD
    if ticker_id and ticker_id not in spot_ids:
        spot_ids.insert(0, ticker_id)
    live_prices = get_live_spot_prices(spot_ids)

    # Fetch account equity & margin balance
    equity, free_margin = get_account_balance()
    closed_trades_history = get_completed_trades_summary(limit=10)

    # Fetch historical playbook & trade retrospectives from Analytics
    analytics_playbook = fetch_analytics_playbook(ticker)
    analytics_block = (
        f"\n\n--- HISTORICAL PLAYBOOK & RETROSPECTIVES ({ticker}) ---\n{analytics_playbook}\n---------------------------------------------------------------\n"
        if analytics_playbook else ""
    )

    # Format live prices block for LLM context
    if live_prices:
        price_lines = []
        for sid, pdata in live_prices.items():
            price_lines.append(
                f"  {pdata['name']} (ID {sid}): bid={pdata['bid']}, ask={pdata['ask']}, mid={pdata['mid']}"
            )
        live_price_block = (
            "\n\n--- LIVE PEPPERSTONE SPOT PRICES (FROM EXCHANGE) ---\n"
            + "\n".join(price_lines)
            + "\n---------------------------------------------------\n"
            "Use these prices as the AUTHORITATIVE current market prices. "
            "Do NOT use any other price sources.\n"
        )
    else:
        live_price_block = "\n[WARNING: Live spot prices unavailable from Exchange — use caution]\n"

    positions_guardrail = (
        f"\n\n--- REAL-TIME PEPPERSTONE EXCHANGE ACCOUNT POSITIONS ---\n"
        f"{live_pos_summary}\n"
        f"CRITICAL MANDATE: You MUST ONLY evaluate real positions listed above. "
        f"Do NOT assume or hallucinate any other open positions or trades that are not explicitly in this list.\n"
        f"---------------------------------------------------------\n"
        f"{live_price_block}"
    )

    account_audit_block = (
        f"\n\n--- BCM ACCOUNT EQUITY & MARGIN AUDIT ---\n"
        f"• Total Account Equity: ${equity:,.2f}\n"
        f"• Free Available Margin: ${free_margin:,.2f}\n"
        f"• Active Positions Summary:\n{live_pos_summary}\n"
        f"-----------------------------------------\n"
        f"\n--- CLOSED TRADES LEARNING LOG & PERFORMANCE ---\n"
        f"{closed_trades_history}\n"
        f"-------------------------------------------------\n"
    )

    print("--- 🕵️ Calling QUANT ANALYST ---")
    market_session = get_market_session()
    analyst_prompt = f"""Analyze these indicators and Remizov shift for {ticker}. 
    Focus on momentum, structural shifts, and institutional levels. 
    CRITICAL: Pay special attention to 'volume_profile.poc' (Point of Control) as a high-probability liquidity level, and 'vwap.daily' for swing positioning and institutional bias.
    CRITICAL VOLATILITY ADJUSTMENT: The current market session is '{market_session}'. You MUST weigh the importance of breakouts vs mean-reversions depending on this session's expected volatility. 
    Check 'past_experience' for historical similarities: {analysis_data}
    {analytics_block}
    {positions_guardrail}"""
    analyst_report = call_llm("Quant Analyst", analyst_prompt)
    print(f"Analyst Report Length: {len(str(analyst_report))}")

    print("--- 🌍 Calling MACRO ANALYST ---")
    current_date = datetime.now().strftime("%Y-%m-%d")
    oil_context = ""
    if "BRENT" in ticker or "BZ" in ticker:
        print("   Fetching Petro-Macro Terminal context for Oil...")
        raw_oil = get_brent_oil_context()
        if raw_oil:
            oil_context = f"\n\n--- PETRO-MACRO TERMINAL DATA ---\n{raw_oil[:3000]}\n---"
            print(f"   Oil context fetched ({len(raw_oil)} chars)")
        else:
            print("   WARNING: Petro-Macro Terminal unavailable, using training data")

    # Fetch global macro metrics (VIX, 10Y Yield) and FRED Regime
    global_macro_data = get_global_macro_metrics()
    fred_regime_data = get_fred_macro_regime()
    fred_intraday_filters_data = get_fred_intraday_filters()
    global_macro_block = (
        f"\n\n--- GLOBAL MACRO ENVIRONMENT ---\n"
        f"{global_macro_data}\n\n"
        f"--- FRED MACRO REGIME ---\n"
        f"{fred_regime_data}\n\n"
        f"--- FRED INTRADAY FILTERS & ECONOMIC CALENDAR ---\n"
        f"{fred_intraday_filters_data}\n"
        f"-------------------------------------------------\n"
    )

    # Fetch live Macro Terminal MCP context (news sentiment, ticker insights)
    macro_terminal_data = get_macro_terminal_context(ticker)
    macro_terminal_block = (
        f"\n\n--- LIVE BEREZINI MACRO TERMINAL ANALYTICS ---\n{macro_terminal_data}\n-----------------------------------------------\n"
        if macro_terminal_data else ""
    )

    macro_prompt = f"""You are the Macro & Sentiment Analyst for Berezini Capital Management.
    Today is {current_date}. We are analyzing {ticker}.
    {oil_context}
    {global_macro_block}
    {macro_terminal_block}
    {positions_guardrail}
    Please provide a brief assessment of the current macroeconomic environment, central bank policies (Fed/BoE/etc.), geopolitical risks, and overall sentiment that could affect {ticker}. 
    CRITICAL: Evaluate the Global Macro Environment (VIX and 10Y Yield) AND the FRED Macro Regime.
    - If VIX > 20, the market is volatile; advise caution and wider stop losses. If VIX < 15, conditions are favorable for tighter trading.
    - If US 10Y Treasury Yield is rising sharply, advise caution on risk-on assets (Crypto, Tech).
    - FRED data updates slowly (weekly/monthly). Use it ONLY to understand the overarching Macro Regime (e.g. 'We are in a high-rate, tightening regime'), NOT as a timing trigger for a 15-minute trade.
    - INTRADAY FILTERS: If 'High Yield Corporate Bond Spread' is rising sharply, it indicates institutional credit stress (panic). Avoid risk-on long positions. If 'NFCI' > 0, financial conditions are tight (bearish for risk assets).
    - ECONOMIC CALENDAR WARNING: If there are major economic releases scheduled for today, you MUST flag this as a high-risk event to the Risk Manager.
    Incorporate the live Macro Terminal sentiment and news data provided above into your analysis."""
    macro_report = call_llm("Macro Analyst", macro_prompt)

    print(f"Macro Report Length: {len(str(macro_report))}")

    print("--- 🛡️ Calling RISK MANAGER ---")
    risk_prompt = f"""Review Market Data, Quant Analyst Report, and Macro Report. 
    Assess safety (ATR/Keltner) and set SL/TP.
    CRITICAL MANDATE: You MUST mathematically ground your Stop Loss (SL) and Take Profit (TP) using institutional order flow levels. Place SL safely behind the Volume Profile Point of Control (POC) and consider daily VWAP boundaries.
    CRITICAL VOLATILITY ADJUSTMENT: If the Macro Report indicates high VIX (>20), you MUST widen the SL proportionately or advise WAIT if the risk is too high.
    NEWS EVENT OVERRIDE: If the Macro Report flags MAJOR ECONOMIC RELEASES today (like CPI, NFP, FOMC), you MUST advise a WAIT status to prevent news-based slippage, or recommend drastically reduced position sizes with extremely wide stops.
    If 'past_experience' shows consistent failures for these conditions, advise WAIT.
    DATA: {analysis_data} 
    QUANT: {analyst_report}
    MACRO: {macro_report}
    {analytics_block}
    {positions_guardrail}"""
    risk_report = call_llm("Risk Manager", risk_prompt)

    print(f"Risk Report Length: {len(str(risk_report))}")

    print("--- 🏦 Calling MANAGING DIRECTOR ---")
    import os
    base_prompt_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prompts")
    
    with open(os.path.join(base_prompt_dir, "system_core.md"), "r") as f:
        system_core = f.read()
    with open(os.path.join(base_prompt_dir, "cognitive_playbook.md"), "r") as f:
        cognitive_playbook = f.read()
    with open(os.path.join(base_prompt_dir, "context_state.md"), "r") as f:
        context_state = f.read()

    # Fetch Paradigms from memory
    try:
        current_context_data = json.loads(analysis_json) if isinstance(analysis_json, str) else analysis_json
        paradigms_text = memory.extract_paradigms_for_context(current_context_data)
    except Exception:
        paradigms_text = "[No Paradigms Yet]"

    # Fill context_state variables
    context_state = context_state.format(
        ticker=ticker,
        analyst_report=analyst_report,
        macro_report=macro_report,
        risk_report=risk_report,
        account_audit_block=account_audit_block,
        positions_guardrail=positions_guardrail,
        paradigms_block=paradigms_text
    )

    md_prompt = f"{system_core}\n\n{context_state}\n\n{cognitive_playbook}"
    final_decision_raw = call_llm("Managing Director", md_prompt)
    
    # Extract JSON
    content = str(final_decision_raw)
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    return content

def format_md_decision_summary(decision_data, symbol="BTC", execution_gates: list = None) -> str:
    """Format Managing Director decision dictionary or JSON string into a best-practice UI/UX Markdown executive report.
    
    Args:
        decision_data: dict or JSON string from MD agent
        symbol: trading symbol
        execution_gates: list of dicts {"name": str, "status": "pass"|"block"|"warn", "reason": str}
    """
    if isinstance(decision_data, str):
        try:
            cleaned = decision_data.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0].strip()
            decision_data = json.loads(cleaned)
        except Exception:
            return decision_data

    if not isinstance(decision_data, dict):
        return str(decision_data)

    action = str(decision_data.get("decision", "wait")).upper()
    action_emoji = "🚀" if action == "BUY" else "🔻" if action == "SELL" else "⏸️"
    alert_type = "IMPORTANT" if action in ("BUY", "SELL") else "NOTE"
    confidence = decision_data.get("confidence", 0)
    try:
        conf_val = float(confidence)
        conf_str = f"{conf_val:.1f}%"
    except Exception:
        conf_str = f"{confidence}%"

    reasoning = decision_data.get("reasoning", "No reasoning provided.")
    
    sl = decision_data.get("recommended_sl")
    tp = decision_data.get("recommended_tp")
    sl_str = f"`{sl}`" if sl is not None else "`N/A`"
    tp_str = f"`{tp}`" if tp is not None else "`N/A`"

    account_sum = decision_data.get("account_summary", {})
    if isinstance(account_sum, dict):
        eq_status = account_sum.get("equity_status", "")
        pos_audit = account_sum.get("openpositionsaudit") or account_sum.get("open_positions_audit", "")
        learnings = account_sum.get("historical_learnings", "")
    else:
        eq_status = str(account_sum) if account_sum else ""
        pos_audit = ""
        learnings = ""

    lines = [
        f"# 🏛️ Autonomous AI Hedge Fund Manager",
        "",
        f"> [{alert_type}]",
        f"> **Executive Verdict:** {action_emoji} **{action}** | **Asset:** `{symbol}` | **Confidence Level:** `{conf_str}`",
        "",
        "### 📊 **Trade Parameters & Quorum Metrics**",
        "",
        "| Metric | Value | Description |",
        "| :--- | :--- | :--- |",
        f"| **Action Verdict** | {action_emoji} **{action}** | Multi-Agent Quorum Consensus |",
        f"| **Confidence Level** | **{conf_str}** | Weighted Quant + Macro + Volatility Shift |",
        f"| **Stop Loss (SL)** | {sl_str} | Algorithmic Risk Limit |",
        f"| **Take Profit (TP)** | {tp_str} | Target Profit Boundary |",
        "",
        "---",
        "",
        "### 💬 **Managing Director Executive Analysis**",
        "",
        f"{reasoning}",
    ]

    # ── Execution Gate Status ──────────────────────────────────────────────
    if execution_gates:
        STATUS_ICON = {"pass": "✅", "block": "🚫", "warn": "⚠️", "skip": "⏭️"}
        STATUS_LABEL = {"pass": "PASS", "block": "BLOCKED", "warn": "WARNING", "skip": "SKIPPED"}
        
        lines.extend([
            "",
            "---",
            "",
            "### 🚦 **Execution Gate Status**",
            "",
            "| Gate | Status | Details |",
            "| :--- | :---: | :--- |",
        ])
        for gate in execution_gates:
            g_status = gate.get("status", "warn")
            icon = STATUS_ICON.get(g_status, "⚠️")
            label = STATUS_LABEL.get(g_status, g_status.upper())
            reason = gate.get("reason", "").replace("|", "│")  # escape table pipes
            lines.append(f"| **{gate['name']}** | {icon} {label} | {reason} |")
        
        # Overall execution verdict
        blocked_gates = [g for g in execution_gates if g.get("status") == "block"]
        warn_gates = [g for g in execution_gates if g.get("status") == "warn"]
        if blocked_gates:
            lines.extend([
                "",
                f"> [!CAUTION]",
                f"> **Trade NOT Executed** — blocked by: {', '.join(g['name'] for g in blocked_gates)}",
            ])
        elif warn_gates:
            lines.extend([
                "",
                f"> [!WARNING]",
                f"> Trade executed with warnings: {', '.join(g['name'] for g in warn_gates)}",
            ])
        else:
            passed = [g for g in execution_gates if g.get("status") == "pass"]
            if passed:
                lines.extend([
                    "",
                    f"> [!TIP]",
                    f"> **All gates passed** — order dispatched to Exchange OpenAPI",
                ])

    if eq_status or pos_audit or learnings:
        lines.extend([
            "",
            "---",
            "",
            "### 💼 **Portfolio & Account Health Audit**",
        ])
        if eq_status:
            lines.append(f"- 🛡️ **Equity & Margin**: {eq_status}")
        if pos_audit:
            lines.append(f"- 📈 **Active Positions**: {pos_audit}")
        if learnings:
            lines.append(f"- 🎓 **Historical Playbook**: {learnings}")

    lines.extend([
        "",
        "---",
        "*Berezini Capital Management (BCM) Autonomous Trading Engine*",
    ])

    return "\n".join(lines)


def format_any_bcm_response(raw_text: str, symbol="BTC") -> str:
    """Detects raw JSON decision strings and converts them to formatted Executive UI/UX Markdown."""
    if not raw_text or not isinstance(raw_text, str):
        return raw_text
    
    cleaned = raw_text.strip()
    if ("\"decision\"" in cleaned or "'decision'" in cleaned) and ("\"confidence\"" in cleaned or "'confidence'" in cleaned or "\"reasoning\"" in cleaned or "'reasoning'" in cleaned):
        try:
            match_json = cleaned
            if "```json" in cleaned:
                match_json = cleaned.split("```json")[1].split("```")[0].strip()
            elif "```" in cleaned:
                match_json = cleaned.split("```")[1].split("```")[0].strip()
            elif "{" in cleaned and "}" in cleaned:
                s_idx = cleaned.find("{")
                e_idx = cleaned.rfind("}") + 1
                match_json = cleaned[s_idx:e_idx]
            
            parsed = json.loads(match_json)
            if isinstance(parsed, dict) and "decision" in parsed:
                return format_md_decision_summary(parsed, symbol=symbol)
        except Exception:
            pass
            
    return raw_text


def execute_trade(action, ticker_id, volume):
    """Execute trade via trade.sh script inside the container."""
    script_path = os.path.join(script_dir, "trade.sh")
    cmd = ["bash", script_path, action, str(ticker_id), str(volume)]
    try:
        output = subprocess.check_output(cmd).decode('utf-8')
        return output
    except Exception as e:
        return f"Trade execution failed: {str(e)}"


def pre_check_indicators(analysis_json, ticker_key, atr_data=None):
    """
    Perform a mathematical check to see if market is 'interesting'.
    Returns (True, "reason") if we should call AI, else (False, "reason").
    Also checks ATR vs historical average to catch high-volatility windows.
    """
    try:
        data = json.loads(analysis_json)
        # Handle the structure returned by n8n
        ticker_search = list(data.get("rsi", {}).keys())[0]
        rsi = data["rsi"][ticker_search]
        macd_hist = data["macdhist"][ticker_search]

        print(f"DEBUG Pre-check [{ticker_key}]: RSI={rsi:.2f}, MACD Hist={macd_hist:.6f}")

        # Condition 1: RSI is reaching overbought/oversold (Relaxed thresholds)
        if rsi < 35 or rsi > 65:
            # Swing threshold: 35/65 catches real multi-day moves, 40/60 was too tight
            return True, f"RSI swing signal ({rsi:.2f})"

        # Condition 2: MACD Histogram is non-neutral
        threshold = 5.0 if "BTC" in ticker_key or "US500" in ticker_key else 0.0001
        if abs(macd_hist) > threshold:
            return True, f"MACD momentum detected ({macd_hist:.6f})"

        # Condition 3: ATR spike — high volatility is tradeable even in neutral RSI/MACD
        if atr_data:
            atr = atr_data.get("atr_d1", 0)
            ema20 = atr_data.get("ema20", 1)
            # 0.5% threshold matches daily ATR scale (daily ATR ~0.5-2% of price)
            if ema20 > 0 and atr / ema20 > 0.005:
                return True, f"ATR elevated ({atr:.4f} = {atr/ema20*100:.2f}% of EMA20)"

        return False, f"Market is neutral (RSI:{rsi:.1f}, MACD:{macd_hist:.4f})"
    except Exception as e:
        return True, f"Data parsing skipped, calling AI for safety: {str(e)}"


def calculate_atr_keltner(ticker):
    """Fetch historical data and calculate ATR + Keltner Channel locally."""
    import yfinance as yf

    try:
        try:
            from backend.bcm.tools import _normalize_yf_symbol
        except ImportError:
            try:
                from tools import _normalize_yf_symbol
            except ImportError:
                _normalize_yf_symbol = lambda s: s
        ticker = _normalize_yf_symbol(ticker)
        print(f"DEBUG: Calculating extra indicators for {ticker} using yfinance...", flush=True)
        
        
        # ponytail: Daily ATR for swing SL/TP — 1H ATR is 4-5x smaller and would stop out on normal intraday noise
        # RSI/MACD entry signals stay on 1H (get_technical_analysis) for precise timing
        df = _fetch_yahoo_direct(ticker, period="60d", interval="1d")
        if df.empty:
            return {}
        
        # Clean multi-index columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # ATR Calculation (14 periods)
        df['H-L'] = df['High'] - df['Low']
        df['H-PC'] = abs(df['High'] - df['Close'].shift(1))
        df['L-PC'] = abs(df['Low'] - df['Close'].shift(1))
        df['TR'] = df[['H-L', 'H-PC', 'L-PC']].max(axis=1)
        atr = df['TR'].rolling(window=14).mean().iloc[-1]
        
        # Keltner Channel (EMA 20, multiplier 2)
        ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
        keltner_upper = ema20 + (atr * 2)
        keltner_lower = ema20 - (atr * 2)
        
        return {
            "atr_d1": round(float(atr), 4),
            "keltner_upper": round(float(keltner_upper), 4),
            "keltner_lower": round(float(keltner_lower), 4),
            "ema20": round(float(ema20), 4)
        }
    except Exception as e:
        print(f"⚠️ yfinance ATR/Keltner Error: {e}")
        return {"warning": str(e)}

def get_brent_oil_context():
    """Fetch live Brent oil context from Petro-Macro Terminal (brent-oil-analyst skill)."""
    import requests
    try:
        response = requests.get(
            "https://oil.berezini.com/api/context/raw?commodity=Brent&period=1mo",
            headers={"accept": "text/plain"},
            timeout=15
        )
        if response.status_code == 200 and response.text.strip():
            return response.text.strip()
    except Exception as e:
        print(f"WARNING: Petro-Macro Terminal unavailable: {e}")
    return None


def get_account_balance():
    """Fetch current account equity using mcporter/n8n with retries."""
    import time
    import shutil
    
    # Dynamic paths for cross-platform compatibility (Linux/Amvera vs Mac)
    node_bin = "/usr/local/bin/node" if os.path.exists("/usr/local/bin/node") else "/opt/homebrew/bin/node" if os.path.exists("/opt/homebrew/bin/node") else shutil.which("node")
    mcporter_bin = "/usr/local/bin/mcporter" if os.path.exists("/usr/local/bin/mcporter") else "/opt/homebrew/bin/mcporter" if os.path.exists("/opt/homebrew/bin/mcporter") else shutil.which("mcporter")
    npx_bin = "/usr/local/bin/npx" if os.path.exists("/usr/local/bin/npx") else "/opt/homebrew/bin/npx" if os.path.exists("/opt/homebrew/bin/npx") else shutil.which("npx")

    # Find mcporter.json: try workspace/config first (Amvera), then project config
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(script_dir))), "workspace", "config", "mcporter.json"),
        os.path.join(os.path.dirname(os.path.dirname(script_dir)), "config", "mcporter.json"),
        "/opt/data/workspace/config/mcporter.json",
        "./config/mcporter.json",
    ]
    config_path = None
    for p in search_paths:
        if os.path.exists(p):
            config_path = p
            break
    if not config_path:
        config_path = "./config/mcporter.json"  # last resort

    cmd = None
    if mcporter_bin and node_bin and os.path.exists(str(mcporter_bin)) and os.path.exists(str(node_bin)):
        cmd = [node_bin, mcporter_bin, "call", "my-n8n-mcp.Get_account_data", "--config", config_path, "--timeout", "60000"]
    elif npx_bin:
        cmd = [npx_bin, "-y", "mcporter", "call", "my-n8n-mcp.Get_account_data", "--config", config_path, "--timeout", "60000"]

    if cmd:
        for attempt in range(3):
            try:
                raw = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')
                json_str = extract_json(raw)
                if not json_str: continue
                
                parsed = json.loads(json_str)
                if isinstance(parsed, list) and len(parsed) > 0:
                    data = parsed[0]
                else:
                    data = parsed
                
                # Deep extract
                margin_data = data.get('data', {}).get('margin', data)
                equity = float(margin_data.get('equity', margin_data.get('equity', 0)))
                free_margin = float(margin_data.get('free_margin', margin_data.get('freeMargin', 0)))
                
                return equity, free_margin
            except Exception as e:
                raw_val = raw if 'raw' in locals() else 'None'
                print(f"Attempt {attempt+1} failed: {str(e)}")
                time.sleep(2)

    # Direct fallback to Exchange API tool if n8n/mcporter failed
    try:
        try:
            from backend.bcm.tools import handle_exchange_get_balance
        except ImportError:
            from tools import handle_exchange_get_balance

        bal_res = handle_exchange_get_balance({})
        if isinstance(bal_res, str):
            bal_res = json.loads(bal_res)
        if isinstance(bal_res, dict):
            eq = 0.0
            fm = 0.0
            if "equity" in bal_res or "balance" in bal_res:
                eq = float(bal_res.get("equity", bal_res.get("balance", 0)))
                fm = float(bal_res.get("freeMargin", bal_res.get("free_margin", eq)))
            elif "accounts" in bal_res and isinstance(bal_res["accounts"], list) and len(bal_res["accounts"]) > 0:
                acc = bal_res["accounts"][0]
                eq = float(acc.get("totalEquity", acc.get("equity", acc.get("totalMarginBalance", 0))))
                fm = float(acc.get("totalAvailableBalance", acc.get("freeMargin", acc.get("free_margin", eq))))
            elif "data" in bal_res and isinstance(bal_res["data"], dict):
                data_dict = bal_res["data"]
                eq = float(data_dict.get("equity", data_dict.get("balance", 0)))
                fm = float(data_dict.get("freeMargin", data_dict.get("free_margin", eq)))

            if eq > 0:
                print(f"✅ Account balance loaded from Exchange API: Equity=${eq:.2f}, FreeMargin=${fm:.2f}")
                return eq, fm
    except Exception as cbe:
        print(f"⚠️ Exchange direct balance fetch error: {cbe}")

    print("⚠️ WARNING: Failed to fetch balance from Exchange API. Using fallback evaluation balance.")
    return 10000.0, 9000.0

def calculate_lot_size(equity, risk_pct, distance, symbol_key):
    """
    Standard Quant Risk Management:
    Lot = (Equity * Risk%) / (Distance to SL)
    """
    risk_amount = equity * (risk_pct / 100)
    if distance <= 0: return TICKER_MAP[symbol_key]['volume'] # Fallback
    
    # Simple lot calculation (adjust for pip value if needed, for BTC 1 point = 1 USD)
    lot = risk_amount / distance
    
    # Round to 2 decimals and ensure minimum
    min_vol = TICKER_MAP[symbol_key]['volume']
    lot = max(round(lot, 2), min_vol)
    
    # Cap at reasonable max (e.g., 5.0 for safety)
    lot = min(lot, 5.0)
    return lot

def calculate_remizov_shift(prices_df):
    """
    Implements the Remizov Volatility Shift logic.
    Analyzes acceleration of volatility (2nd derivative) to detect structural shifts.
    """
    try:
        # 1. Calculate Volatility (True Range)
        prices_df['H-L'] = prices_df['High'] - prices_df['Low']
        volatility = prices_df['H-L']
        
        # 2. First Derivative (Speed of Volatility change)
        dv = volatility.diff()
        
        # 3. Second Derivative (Acceleration of Volatility - the 'Remizov' core)
        d2v = dv.diff()
        
        # 4. Resolvent/Smoothing (Laplace-like approximation)
        remizov_resolvent = d2v.ewm(span=5, adjust=False).mean().iloc[-1]
        
        # Normalize shift (cap at +/- 0.15 for confidence adjustment)
        # We look for abnormal acceleration
        std_accel = d2v.std()
        shift = (remizov_resolvent / std_accel) * 0.1 if std_accel != 0 else 0
        shift = max(min(shift, 0.15), -0.15)
        
        return round(shift, 3), round(remizov_resolvent, 4)
    except Exception as e:
        print(f"Remizov Math Error: {e}")
        return 0, 0

def run_autonomous_cycle(symbol_key):
    if symbol_key not in TICKER_MAP:
        print(f"Error: {symbol_key} not in map.")
        return

    config = TICKER_MAP[symbol_key]
    analysis_ticker = config['analysis']
    trade_id = config['trade_id']
    base_volume = config['volume']

    execution_gates = []

    def gate(name, status, reason):
        icon = {"pass": "✅", "block": "🚫", "warn": "⚠️", "skip": "⏭️"}.get(status, "❓")
        print(f"[GATE] {icon} {name}: {reason}")
        execution_gates.append({"name": name, "status": status, "reason": reason})

    def emit_report_and_return(decision_obj=None, trace_data=None):
        if decision_obj is None:
            decision_obj = {
                "decision": "wait",
                "confidence": 0.0,
                "reasoning": "Cycle terminated early — see Execution Gate Status for details.",
                "recommended_sl": None,
                "recommended_tp": None,
            }
        report = format_md_decision_summary(decision_obj, symbol=symbol_key, execution_gates=execution_gates)
        
        # [NEW] Log full-cycle trace if available
        if trace_data:
            try:
                from backend.database import log_trade_trace
                trace_id = trace_data.get("trace_id", "fallback_id")
                layer_02 = json.dumps(trace_data)
                
                # Determine layer_03 action based on gates
                blocked = [g for g in execution_gates if g["status"] == "block"]
                if blocked:
                    layer_03 = f"BLOCKED: {blocked[0]['reason']}"
                    audit_status = "REJECTED"
                else:
                    action_enum = trace_data.get("decision", "wait")
                    layer_03 = f"EXECUTED or SKIPPED: {action_enum}"
                    audit_status = "PASSED" if action_enum != "wait" else "SKIPPED"
                    
                log_trade_trace(
                    trace_id=trace_id,
                    session_id="BCM-AUTO",
                    symbol=symbol_key,
                    layer_01=json.dumps({"tech": "Fetched from BCM Indicators", "gates": execution_gates}),
                    layer_02=layer_02,
                    layer_03=layer_03,
                    audit_status=audit_status
                )
            except Exception as e:
                print(f"⚠️ Failed to log trace: {e}")
        
        blocked = [g for g in execution_gates if g["status"] == "block"]
        warned  = [g for g in execution_gates if g["status"] == "warn"]
        if blocked:
            tg_msg = f"🚫 *BCM Blocked* — {symbol_key}\n"
            for g in blocked:
                tg_msg += f"  • *{g['name']}*: {g['reason']}\n"
            get_notifier().send(tg_msg)
        elif warned:
            tg_msg = f"⚠️ *BCM Warning* — {symbol_key}\n"
            for g in warned:
                tg_msg += f"  • *{g['name']}*: {g['reason']}\n"
            get_notifier().send(tg_msg)
        return report

    try:
        from backend.bcm.fast_market_cache import fast_market_cache
        from backend.bcm.regime_detector import RegimeDetector
        from backend.bcm.confluence_engine import ConfluenceEngine, ConfluenceDecision
        from backend.bcm.frozen_windows import get_frozen_windows_controller
        from backend.bcm.compliance_officer import ComplianceOfficer
    except ImportError:
        from fast_market_cache import fast_market_cache
        from regime_detector import RegimeDetector
        from confluence_engine import ConfluenceEngine, ConfluenceDecision
        from frozen_windows import get_frozen_windows_controller
        from compliance_officer import ComplianceOfficer

    print(f"--- Starting QUANTUM cycle for {symbol_key} ---")

    # Guard: skip if open position
    live_positions, pos_summary = get_live_exchange_positions()
    has_live_pos = any(p.get("symbol") == symbol_key for p in live_positions)
    if has_live_pos or memory.has_open_position(symbol_key):
        gate("Open Position Guard", "skip", f"Active position for {symbol_key}")
        return emit_report_and_return()

    # Step 0: Frozen Windows (Macro gating)
    fw_ctrl = get_frozen_windows_controller()
    fw_res = fw_ctrl.get_active_frozen_window(symbol_key)
    if fw_res.get("is_frozen"):
        gate("Frozen Windows", "block", fw_res.get("reason"))
        return emit_report_and_return()
    gate("Frozen Windows", "pass", "No active high-impact macro events")

    # Step 1: Account Balance
    equity, free_margin = get_account_balance()
    if not equity or equity <= 0:
        gate("Account Balance", "block", "Could not fetch valid account equity/margin from Exchange")
        return emit_report_and_return()
    gate("Account Balance", "pass", f"Equity: ${equity:,.2f}")

    # Step 2: Retrieve Technicals & Staleness Guard via FastMarketCache
    cache_key = f"{analysis_ticker}:technical"
    cached_tech = fast_market_cache.get(cache_key)
    if cached_tech["_meta"]["is_stale"]:
        # Fallback: compute synchronously if stale
        print(f"Cache stale for {cache_key}, computing technicals...")
        tech_json_str = get_technical_analysis(analysis_ticker)
        try:
            tech_data = json.loads(tech_json_str) if tech_json_str else {}
        except:
            tech_data = {}
        fast_market_cache.set(cache_key, tech_data, ttl_sec=900)
    else:
        tech_data = cached_tech["data"] or {}
    
    # Step 3: Remizov & Regime Detection
    import yfinance as yf
    try:
        hist_df = _fetch_yahoo_direct(analysis_ticker, period="60d", interval="1d")
        if not hist_df.empty:
            if isinstance(hist_df.columns, pd.MultiIndex):
                hist_df.columns = hist_df.columns.get_level_values(0)
            remizov_val, _ = calculate_remizov_shift(hist_df)
            
            regime_detector = RegimeDetector()
            regime_res = regime_detector.detect_regime(hist_df['Close'].tolist())
            regime = regime_res['regime']
            current_close = hist_df['Close'].iloc[-1]
            vol_state = {"atr": current_close * 0.015} # basic fallback atr
        else:
            remizov_val, regime, vol_state, current_close = 0.0, "SIDEWAYS", {"garch_vol": 0, "atr": 0}, 0.0
    except Exception as e:
        print(f"Hist Data Error: {e}")
        remizov_val, regime, vol_state, current_close = 0.0, "SIDEWAYS", {"garch_vol": 0, "atr": 0}, 0.0

    # Fallback to current_price_yahoo if needed
    if current_close == 0.0:
        current_close = tech_data.get('close', {}).get(analysis_ticker, 0)
    
    if current_close == 0:
        gate("Data Integrity", "block", "Current price could not be determined")
        return emit_report_and_return()

    # Extract indicators
    rsi = list(tech_data.get('rsi', {}).values())[0] if tech_data.get('rsi') else 50.0
    macd = list(tech_data.get('macd', {}).values())[0] if tech_data.get('macd') else 0.0
    
    # Simple normalizations for Confluence Engine [-1.0, 1.0]
    momentum_score = 0.0
    if rsi > 60 and macd > 0: momentum_score = 1.0
    elif rsi < 40 and macd < 0: momentum_score = -1.0
    elif rsi > 55: momentum_score = 0.5
    elif rsi < 45: momentum_score = -0.5

    # Step 4: Confluence Engine
    confluence = ConfluenceEngine()
    is_sideways = (regime == "SIDEWAYS")
    conf_res = confluence.compute_confluence(
        remizov_score=remizov_val,
        momentum_score=momentum_score,
        is_sideways_regime=is_sideways,
        higher_tf_trend="BULL" if regime in ["BULL", "RECOVERY"] else "BEAR" if regime == "BEAR" else "SIDEWAYS"
    )

    decision_enum = conf_res["decision"]
    conf_score = conf_res["confluence_score"]
    
    if decision_enum in [ConfluenceDecision.HOLD_SKIP]:
        action = "wait"
        gate("Confluence Engine", "skip", f"Veto applied. Score: {conf_score:.2f} (Regime: {regime})")
    elif decision_enum in [ConfluenceDecision.STRONG_BUY, ConfluenceDecision.NORMAL_BUY]:
        action = "buy"
        gate("Confluence Engine", "pass", f"BUY Signal. Score: {conf_score:.2f}")
    else:
        action = "sell"
        gate("Confluence Engine", "pass", f"SELL Signal. Score: {conf_score:.2f}")

    if action == "wait":
        return emit_report_and_return(trace_data=conf_res)

    # Step 5: Risk & SL/TP
    atr = vol_state.get("atr", current_close * 0.01)
    if atr == 0: atr = current_close * 0.01
    
    sl_dist = atr * 1.5 if is_sideways else atr * 2.0
    sl = current_close - sl_dist if action == "buy" else current_close + sl_dist
    
    # Calculate R:R based on recommended_rr from ConfluenceEngine
    rr_str = conf_res["recommended_rr"]
    rr_val = float(rr_str.split(":")[1]) if ":" in rr_str else 2.0
    tp_dist = sl_dist * rr_val
    tp = current_close + tp_dist if action == "buy" else current_close - tp_dist
    
    lot = calculate_lot_size(equity, conf_res["risk_multiplier"], sl_dist, symbol_key)

    # Step 6: Compliance Audit
    cco = ComplianceOfficer(peak_equity=equity)
    md_decision = f"Confluence Score: {conf_score:.2f}, Regime: {regime}, Reasons: {conf_res['veto_reasons']}"
    risk_report = f"Equity: {equity}, Lot: {lot}, SL Dist: {sl_dist:.4f}"
    
    cco_passed, cco_reason = cco.audit_trade(
        symbol=symbol_key,
        action=action,
        volume=lot,
        base_volume=base_volume,
        sl=sl,
        tp=tp,
        entry_price=current_close,
        md_decision=md_decision,
        risk_report=risk_report
    )
    
    if not cco_passed:
        gate("Compliance Officer", "block", f"Rejected: {cco_reason}")
        return emit_report_and_return(trace_data=conf_res)
        
    gate("Compliance Officer", "pass", "Approved by Risk Engine")

    # Step 7: Execution
    print(f"Executing Exchange Order (Lot: {lot}) via OpenAPI...")
    side_cmd = "buy" if action == 'buy' else "sell"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        cmd_place = ["bash", os.path.join(script_dir, "trade.sh"),
                     side_cmd, str(trade_id), str(lot), str(sl), str(tp)]
        res_raw = subprocess.check_output(cmd_place, stderr=subprocess.STDOUT).decode('utf-8')
        
        gate("Exchange Execution", "pass", f"Order dispatched: {action.upper()} {lot} @ SL={sl} TP={tp}")
        
        memory.log_decision(f"BCM-Q-{int(time.time())}", symbol_key, action, lot, current_close,
                            md_decision + f"\n[CCO Audit: {cco_reason}]", tech_data)

        decision_obj = {
            "decision": action,
            "confidence": abs(conf_score) * 100,
            "reasoning": md_decision,
            "recommended_sl": sl,
            "recommended_tp": tp
        }
        report = format_md_decision_summary(decision_obj, symbol=symbol_key, execution_gates=execution_gates)
        
        # Log successful trace
        emit_report_and_return(decision_obj=decision_obj, trace_data=conf_res)
        
        return report

    except Exception as e:
        error_detail = str(e)
        if isinstance(e, subprocess.CalledProcessError) and e.output:
            error_detail += "\n" + e.output.decode('utf-8', errors='replace')
        gate("Exchange Execution", "block", f"subprocess failed: {error_detail[:300]}")
        return emit_report_and_return(trace_data=conf_res)



def run_options_cycle(base_coin: str = "BTC", exp_date: str = None) -> dict:
    """
    Autonomous Options Spread Cycle — BCM v2.0

    Workflow:
    1. Fetch broker balance & equity
    2. Fetch live option chain (Greeks, IV, Mark prices)
    3. Fetch macro context (VIX, FRED, sentiment)
    4. Call Options Strategist LLM → get JSON spread decision
    5. Compliance audit (hard limits + 2% equity cap)
    6. Execute both legs via place_option_order (REAL API calls)
    7. Log to BCM memory + Telegram

    Returns:
        dict with status, strategy, execution results
    """
    try:
        from backend.bcm.exchange_factory import ExchangeFactory
    except ImportError:
        from exchange_factory import ExchangeFactory
        
    broker = ExchangeFactory.get_options_broker()

    print(f"\n{'='*60}")
    print(f"  🏛️ BCM OPTIONS CYCLE — {base_coin} (exp: {exp_date or 'all'}) via {type(broker).__name__}")
    print(f"{'='*60}")

    # ── Step 1: Account Balance ──────────────────────────────────
    print("Step 1: Fetching account balance...")
    balance_res = broker.get_wallet_balance(account_type="UNIFIED")
    account_equity = 0.0
    usdc_avail = 0.0

    if balance_res.get("status") == "success":
        for acct in balance_res.get("accounts", []):
            coins = acct.get("coin", [])
            for c in coins:
                if c.get("coin") in ("USDC", "USDT"):
                    try:
                        account_equity += float(c.get("equity", 0) or 0)
                        usdc_avail += float(c.get("availableToWithdraw", 0) or 0)
                    except Exception:
                        pass
        print(f"   Broker Equity: ${account_equity:,.2f} | Available: ${usdc_avail:,.2f}")
    else:
        print(f"   ⚠️ Balance fetch failed: {balance_res.get('message', 'Unknown error')}")
        return {"status": "error", "reason": "Cannot fetch Broker balance", "details": balance_res}

    if account_equity < 500:
        msg = f"⏸️ BCM Options: Insufficient equity (${account_equity:.2f}). Min $500 required."
        print(msg)
        get_notifier().send(msg)
        return {"status": "skipped", "reason": msg}

    # ── Step 2: Option Chain ─────────────────────────────────────
    print(f"Step 2: Fetching {base_coin} option chain...")
    chain_res = broker.get_option_chain(base_coin=base_coin, exp_date=exp_date)

    if chain_res.get("status") != "success" or not chain_res.get("chain"):
        msg = f"⏸️ BCM Options: Option chain unavailable for {base_coin}. Skipping."
        print(msg)
        return {"status": "skipped", "reason": msg}

    chain = chain_res.get("chain", [])
    print(f"   Chain loaded: {len(chain)} contracts")

    # Summarize chain for LLM (top 30 by open interest, with IV and Greeks)
    def _fmt_chain_summary(contracts, limit=30):
        """Extract key fields for LLM context."""
        rows = []
        for c in contracts[:limit]:
            rows.append({
                "symbol": c.get("symbol"),
                "markPrice": c.get("markPrice"),
                "openInterest": c.get("openInterest"),
                "iv": c.get("iv"),
                "delta": c.get("delta"),
                "gamma": c.get("gamma"),
                "theta": c.get("theta"),
                "vega": c.get("vega"),
                "bid1Price": c.get("bid1Price"),
                "ask1Price": c.get("ask1Price"),
            })
        return rows

    chain_summary = _fmt_chain_summary(chain)
    # Spot price from first contract's underlying or direct fetch
    spot_price = 0.0
    try:
        try:
            from backend.bcm.exchange_factory import ExchangeFactory
        except ImportError:
            from exchange_factory import ExchangeFactory
        spot_broker = ExchangeFactory.get_spot_broker()
        # TODO: Implement get_spot_price in spot broker or get it from chain
        if hasattr(spot_broker, 'get_spot_price'):
            spot_price = spot_broker.get_spot_price(f"{base_coin}USDT")
        else:
            spot_price = 1000.0  # Fallback for now if not implemented
        print(f"   Spot {base_coin}: ${spot_price:,.2f}")
    except Exception as e:
        print(f"   Spot price fetch failed: {e}")

    # ── Step 3: Macro Context ────────────────────────────────────
    print("Step 3: Fetching macro context for options pricing...")
    global_macro = get_global_macro_metrics()
    fred_data = get_fred_macro_regime()
    macro_terminal = get_macro_terminal_context(base_coin)
    current_date = datetime.now().strftime("%Y-%m-%d %H:%M UTC")

    # ── Step 4: Options Strategist LLM Decision ──────────────────
    print("Step 4: Consulting Options Strategist LLM...")
    max_loss_cap = round(account_equity * 0.02, 2)  # 2% equity hard cap

    # Pre-compute conditional blocks (backslash not allowed in f-string expressions in Python < 3.12)
    macro_terminal_section = ("--- MACRO TERMINAL ---\n" + macro_terminal) if macro_terminal else ""

    options_prompt = (
        f"You are the BCM Options Strategist. Today is {current_date}.\n\n"
        f"## Account State\n"
        f"- Broker UNIFIED Equity: ${account_equity:,.2f}\n"
        f"- Available Capital: ${usdc_avail:,.2f}\n"
        f"- Max Allowed Loss (2% cap): ${max_loss_cap:.2f}\n\n"
        f"## Asset\n"
        f"- Base Coin: {base_coin}\n"
        f"- Current Spot Price: ${spot_price:,.2f}\n"
        f"- Expiry Filter: {exp_date or 'All expirations'}\n\n"
        f"## Option Chain Summary (Top 30 by Open Interest)\n"
        f"{json.dumps(chain_summary, indent=2)}\n\n"
        f"## Macro Environment\n"
        f"{global_macro}\n\n"
        f"{fred_data}\n\n"
        f"{macro_terminal_section}\n\n"
        f"## Task\n"
        f"Design the BEST defined-risk credit spread for current conditions.\n"
        f"Constraints:\n"
        f"- Max loss must be <= ${max_loss_cap:.2f} (2% equity cap)\n"
        f"- Only OTM strikes (sell-leg >= 5% from spot)\n"
        f"- Prefer longer-dated expiry (>60 days) for stable IV premium\n"
        f"- Both legs must exist in the chain above (check symbols carefully)\n"
        f"- Output ONLY valid JSON, no markdown, no explanation outside JSON\n\n"
        f"Required JSON keys: strategy, reasoning, confidence, sell_leg, buy_leg, net_credit_usd, max_loss_usd, breakeven_price\n"
        f"If no suitable setup exists, output strategy=\"wait\" with sell_leg=null and buy_leg=null."
    )

    decision_raw = call_llm("Options Strategist", options_prompt)
    print(f"   Options Strategist response ({len(decision_raw)} chars)")


    # Parse LLM JSON
    try:
        content = decision_raw.strip()
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        decision = json.loads(content)
    except Exception as parse_err:
        err_msg = f"❌ BCM Options: Failed to parse Options Strategist JSON: {str(decision_raw)[:300]}"
        print(err_msg)
        get_notifier().send(err_msg)
        return {"status": "error", "reason": "JSON parse error", "raw": decision_raw[:500]}

    strategy = decision.get("strategy", "wait")
    reasoning = decision.get("reasoning", "")
    confidence = float(decision.get("confidence", 0))
    sell_leg = decision.get("sell_leg")
    buy_leg = decision.get("buy_leg")
    net_credit = float(decision.get("net_credit_usd", 0))
    max_loss = float(decision.get("max_loss_usd", 0))
    breakeven = decision.get("breakeven_price", "N/A")

    print(f"   Strategy: {strategy.upper()} | Confidence: {confidence:.0f}% | Net Credit: ${net_credit:.0f} | Max Loss: ${max_loss:.0f}")

    # ── Step 4a: Wait path ───────────────────────────────────────
    if strategy == "wait" or not sell_leg or not buy_leg:
        msg = (
            f"⏸️ *BCM Options — WAIT*\n"
            f"Asset: `{base_coin}` | Confidence: `{confidence:.0f}%`\n"
            f"💬 {reasoning[:500]}"
        )
        print(f"   Decision: WAIT — {reasoning[:200]}")
        get_notifier().send(msg)
        return {"status": "wait", "strategy": strategy, "reasoning": reasoning}

    # ── Step 5: Compliance Audit ─────────────────────────────────
    print("Step 5: Compliance audit...")
    try:
        cco = ComplianceOfficer()
        cco_passed, cco_reason = cco.audit_options_trade(
            base_coin=base_coin,
            strategy=strategy,
            max_loss_usd=max_loss,
            net_credit_usd=net_credit,
            account_equity=account_equity,
            num_legs=2,
            reasoning=reasoning
        )
    except Exception as cco_err:
        cco_passed, cco_reason = False, f"Compliance system error: {cco_err}"

    if not cco_passed:
        msg = (
            f"🚫 *BCM Options — COMPLIANCE REJECTION*\n"
            f"Strategy: `{strategy}` | Asset: `{base_coin}`\n"
            f"Reason: {cco_reason}"
        )
        print(f"   ❌ REJECTED: {cco_reason}")
        get_notifier().send(msg)
        return {"status": "rejected", "reason": cco_reason}

    print(f"   ✅ Compliance Approved: {cco_reason}")

    # ── Step 6: Execute Both Legs ────────────────────────────────
    print("Step 6: Executing options spread on Broker...")
    exec_results = {}

    for leg_name, leg in [("sell_leg", sell_leg), ("buy_leg", buy_leg)]:
        if not leg:
            continue
        print(f"   Placing {leg_name}: {leg.get('side')} {leg.get('symbol')} @ {leg.get('price')}")
        try:
            result = broker.place_option_order(
                symbol=leg["symbol"],
                side=leg["side"],
                order_type=leg.get("order_type", "Limit"),
                qty=str(leg.get("qty", "1")),
                price=str(leg.get("price", "0"))
            )
            exec_results[leg_name] = result
            print(f"   → {leg_name} result: {result}")

            # If first leg fails, abort second leg to avoid unhedged exposure
            if leg_name == "sell_leg" and result.get("status") != "success":
                abort_msg = (
                    f"⚠️ *BCM Options — SELL LEG FAILED*\n"
                    f"Symbol: `{leg.get('symbol')}`\n"
                    f"Error: {result.get('message', 'Unknown')}\n"
                    f"Buy leg NOT placed (avoiding naked exposure)."
                )
                print(f"   ⚠️ Sell leg failed — aborting spread to avoid naked position")
                get_notifier().send(abort_msg)
                return {"status": "partial_failure", "sell_leg": result, "buy_leg": None}

        except Exception as exec_err:
            exec_results[leg_name] = {"status": "error", "error": str(exec_err)}
            print(f"   ❌ {leg_name} exception: {exec_err}")

    # ── Step 7: Log & Notify ─────────────────────────────────────
    print("Step 7: Logging and sending Telegram notification...")
    sell_ok = exec_results.get("sell_leg", {}).get("status") == "success"
    buy_ok  = exec_results.get("buy_leg",  {}).get("status") == "success"

    # Log to BCM memory
    try:
        tracking_id = f"BCM-OPT-{int(time.time())}"
        log_entry = {
            "base_coin": base_coin,
            "strategy": strategy,
            "sell_leg": sell_leg,
            "buy_leg": buy_leg,
            "net_credit_usd": net_credit,
            "max_loss_usd": max_loss,
            "breakeven": breakeven,
            "exec_sell": exec_results.get("sell_leg"),
            "exec_buy":  exec_results.get("buy_leg"),
            "confidence": confidence,
            "compliance": cco_reason,
        }
        memory.log_decision(
            tracking_id,
            f"{base_coin}_OPTIONS",
            strategy,
            1,
            spot_price,
            reasoning,
            log_entry
        )
    except Exception as mem_err:
        print(f"   ⚠️ Memory log failed: {mem_err}")

    # Telegram report
    status_emoji = "✅" if (sell_ok and buy_ok) else "⚠️"
    msg = (
        f"{status_emoji} *BCM Options — EXECUTED*\n"
        f"Strategy: `{strategy.upper()}` | Asset: `{base_coin}` | Conf: `{confidence:.0f}%`\n\n"
        f"📊 *Spread Parameters:*\n"
        f"• Sell: `{sell_leg.get('symbol')}` @ `${sell_leg.get('price')}` → {'✅' if sell_ok else '❌'}\n"
        f"• Buy:  `{buy_leg.get('symbol')}` @ `${buy_leg.get('price')}` → {'✅' if buy_ok else '❌'}\n\n"
        f"💰 Net Credit: `${net_credit:.0f}` | Max Loss: `${max_loss:.0f}` | BE: `${breakeven}`\n"
        f"✅ *CCO:* {cco_reason[:120]}\n\n"
        f"📝 {reasoning[:300]}..."
    )
    get_notifier().send(msg)
    print(f"\n{'='*60}")
    print(f"  Options Cycle Complete: sell_ok={sell_ok}, buy_ok={buy_ok}")
    print(f"{'='*60}\n")

    return {
        "status": "executed" if (sell_ok and buy_ok) else "partial",
        "strategy": strategy,
        "sell_leg": exec_results.get("sell_leg"),
        "buy_leg":  exec_results.get("buy_leg"),
        "net_credit_usd": net_credit,
        "max_loss_usd": max_loss,
        "breakeven_price": breakeven,
        "confidence": confidence,
        "cco_reason": cco_reason
    }


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    run_autonomous_cycle(target)

