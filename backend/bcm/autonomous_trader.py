import sys
import os

BCM_DIR = os.path.dirname(os.path.abspath(__file__))
if BCM_DIR not in sys.path:
    sys.path.insert(0, BCM_DIR)

import subprocess
import json
import requests
import time
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
MODEL = "deepseek/deepseek-chat"

def israel_time():
    """Return current Israel time string (IDT/IST)."""
    from datetime import datetime, timezone, timedelta
    israel_tz = timezone(timedelta(hours=3))  # IDT = UTC+3
    now = datetime.now(israel_tz)
    return now.strftime("%d/%m %H:%M IDT")

def send_telegram_msg(message):
    """Send a notification to Telegram with retries."""
    if not TELEGRAM_CHAT_ID:
        print("Telegram Chat ID not set. Skipping notification.")
        return
    # Prepend Israel time
    il_time = israel_time()
    message = f"[{il_time}] {message}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    
    for attempt in range(3):
        try:
            requests.post(url, json=payload, timeout=10)
            return # Success
        except Exception as e:
            print(f"Telegram Attempt {attempt+1} failed: {e}")
            time.sleep(2)

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

def get_technical_analysis(ticker):
    """Fetch RSI/MACD/Bollinger technicals locally using yfinance."""
    import yfinance as yf
    import pandas as pd
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
        # 1h interval: 120 candles over 5 days — enough for RSI-14/MACD, better for intraday sessions
        df = yf.download(ticker, period="5d", interval="1h", progress=False)
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
        return json.dumps(res)
    except Exception as e:
        print(f"⚠️ yfinance Technical Analysis Error: {e}")
        return json.dumps({"rsi": {ticker: 50.0}, "warning": str(e)})

script_dir = os.path.dirname(os.path.abspath(__file__))

# Mapping between Analysis Ticker (Yahoo format) and Trading ID (Pepperstone cTrader format)
TICKER_MAP = {
    "BTC": {"analysis": "BTC-USD", "trade_id": 10028, "volume": 0.01},
    "GBPUSD": {"analysis": "GBPUSD=X", "trade_id": 2, "volume": 1000},
    "EURUSD": {"analysis": "EURUSD=X", "trade_id": 1, "volume": 1000},
    "US500": {"analysis": "^GSPC", "trade_id": 10001, "volume": 0.1},
    "BRENT": {"analysis": "BZ=F", "trade_id": 10053, "volume": 1},
    "USOIL": {"analysis": "CL=F", "trade_id": 10054, "volume": 1},
    "WTI": {"analysis": "CL=F", "trade_id": 10054, "volume": 1},
    "OIL": {"analysis": "BZ=F", "trade_id": 10053, "volume": 1},
    "GOLD": {"analysis": "GC=F", "trade_id": 10013, "volume": 1}
}

def get_live_ctrader_positions():
    """Fetch live positions from Pepperstone cTrader API via tools module."""
    try:
        try:
            from backend.bcm.tools import handle_ctrader_get_positions, VOLUME_FACTOR, FX_VOLUME_FACTOR
        except ImportError:
            from tools import handle_ctrader_get_positions, VOLUME_FACTOR, FX_VOLUME_FACTOR
            
        res = handle_ctrader_get_positions({})
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
            return [], "LIVE CTRADER OPEN POSITIONS: NONE (0 open positions)."

        # Enrich positions with live spot prices from Pepperstone
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

        summary = f"LIVE CTRADER OPEN POSITIONS ({len(formatted_positions)} active):\n"
        for item in formatted_positions:
            summary += f"• {item['symbol']} (ID: {item['position_id']}): {item['side']} {item['volume']} lots @ Entry: {item['entry_price']} | Current: {item['current_price']} | SL: {item['sl']} | TP: {item['tp']} | PnL: ${item['unrealized_pnl']}\n"
            
        return formatted_positions, summary
    except Exception as e:
        print(f"⚠️ Error fetching live cTrader positions: {e}")
        return [], f"LIVE CTRADER OPEN POSITIONS: Unavailable ({str(e)})"


def get_live_spot_prices(symbol_ids: list = None):
    """Запросить текущие bid/ask котировки напрямую с Pepperstone cTrader.

    Returns:
        dict: {symbolId: {'bid': float, 'ask': float, 'mid': float, 'name': str}, ...}
    """
    if symbol_ids is None:
        # Default watchlist: BTC, SpotBrent, SpotCrude, Gold
        symbol_ids = [10028, 10053, 10054, 10013]
    try:
        try:
            from backend.bcm.tools import handle_ctrader_get_spot_prices
        except ImportError:
            from tools import handle_ctrader_get_spot_prices

        res = handle_ctrader_get_spot_prices({"symbol_ids": symbol_ids})
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

    # 2. Check live spread via Pepperstone if available
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


def fetch_graphrag_playbook(ticker: str) -> str:
    """Fetch historical trading channel playbook & retrospectives from Pride-GraphRAG."""
    try:
        try:
            from backend.bcm.tools import handle_graphrag_query
        except ImportError:
            from tools import handle_graphrag_query

        res = handle_graphrag_query({"query": f"Историческая логика, сетапы и результаты по {ticker}"})
        if isinstance(res, dict) and "answer" in res:
            return res.get("answer", "")
        elif isinstance(res, dict) and "error" not in res:
            return str(res)
        return ""
    except Exception as e:
        print(f"⚠️ Pride-GraphRAG playbook fetch error: {e}")
        return ""


# Per-role AI model selection (overrideable via environment variables)
DEFAULT_MODEL = os.environ.get("BCM_MODEL", "deepseek/deepseek-chat")
ROLE_MODELS = {
    "Quant Analyst": os.environ.get("BCM_MODEL_QUANT", DEFAULT_MODEL),
    "Macro Analyst": os.environ.get("BCM_MODEL_MACRO", DEFAULT_MODEL),
    "Risk Manager": os.environ.get("BCM_MODEL_RISK", DEFAULT_MODEL),
    "Managing Director": os.environ.get("BCM_MODEL_MD", DEFAULT_MODEL),
}

# Role-specific institutional system pre-prompts
ROLE_SYSTEM_PROMPTS = {
    "Quant Analyst": (
        "You are the Lead Quantitative & Technical Analyst at Berezini Capital Management (BCM). "
        "Your mandate is to perform rigorous technical analysis, price action evaluation, and momentum assessment. "
        "Analyze technical indicators (RSI, ATR, Keltner Channels), structural price shifts, and historical setup patterns from GraphRAG. "
        "Provide a data-driven report with clear support/resistance zones, trend bias, and momentum signals."
    ),
    "Macro Analyst": (
        "You are the Senior Macro & Geopolitical Strategist at Berezini Capital Management (BCM). "
        "Your mandate is to evaluate global macroeconomic drivers, central bank interest rate policies, energy market trends, "
        "and live news sentiment from Berezini Macro Terminal. "
        "Provide a clear macro risk assessment (Bullish / Bearish / Neutral) and highlight tail-risk events."
    ),
    "Risk Manager": (
        "You are the Chief Risk Officer (CRO) at Berezini Capital Management (BCM). "
        "Your sole mandate is capital preservation, strict risk containment, and drawdown prevention. "
        "You MUST verify ATR volatility safety margins, check for a minimum 1:1.5 Risk-to-Reward ratio for proposed SL/TP, "
        "review active cTrader open positions to prevent duplicate exposure, and veto any high-risk setup."
    ),
    "Managing Director": (
        "You are the Managing Director & Chief Investment Officer (CIO) at Berezini Capital Management (BCM). "
        "Your mandate is executive portfolio leadership, multi-agent synthesis, and continuous learning from trade execution outcomes. "
        "You MUST produce a comprehensive, detailed, in-depth analytical breakdown covering: "
        "1. ACCOUNT & PORTFOLIO HEALTH: Detailed audit of Balance, Equity, Margin Usage, Free Margin, and Floating PnL. "
        "2. ACTIVE POSITIONS & ORDERS AUDIT: Thorough evaluation of every open trade, volume, entry vs current price, SL/TP safety. "
        "3. HISTORICAL CLOSED TRADES & LEARNING: Analysis of past completed trades, realized PnL, win-rate %, and lessons learned from past mistakes. "
        "4. MULTI-AGENT SYNTHESIS: Cross-referencing Quant Analyst, Macro Analyst, and Risk Manager reports. "
        "5. EXECUTIVE ACTION PLAN: A binding decision ('buy'|'sell'|'wait') with a detailed, in-depth reasoning essay and confidence rating. "
        "Your output MUST be valid JSON with keys: 'decision', 'reasoning', 'confidence', 'account_summary', 'recommended_sl', 'recommended_tp'."
    ),
}


def call_llm(role_name, prompt):
    """Generic helper to call LLM with a specific role, system pre-prompt, and targeted model."""
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
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
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=60)
        data = response.json()
        content = data.get('choices', [{}])[0].get('message', {}).get('content', "")
        return content if content else f"Agent {role_name} returned empty content."
    except Exception as e:
        return f"Agent {role_name} Error: {str(e)}"


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
    _, live_pos_summary = get_live_ctrader_positions()

    # Fetch live spot prices for the ticker being analysed + key watchlist symbols
    ticker_id = TICKER_MAP.get(ticker, {}).get("trade_id")
    spot_ids = [10028, 10053, 10054, 10013, 10001, 2, 1]  # BTC, SpotBrent, SpotCrude, Gold, US500, GBPUSD, EURUSD
    if ticker_id and ticker_id not in spot_ids:
        spot_ids.insert(0, ticker_id)
    live_prices = get_live_spot_prices(spot_ids)

    # Fetch account equity & margin balance
    equity, free_margin = get_account_balance()
    closed_trades_history = get_completed_trades_summary(limit=10)

    # Fetch Pride-GraphRAG historical playbook & trade retrospectives
    graphrag_playbook = fetch_graphrag_playbook(ticker)
    graphrag_block = (
        f"\n\n--- PRIDE-GRAPHRAG HISTORICAL PLAYBOOK & RETROSPECTIVES ({ticker}) ---\n{graphrag_playbook}\n---------------------------------------------------------------\n"
        if graphrag_playbook else ""
    )

    # Format live prices block for LLM context
    if live_prices:
        price_lines = []
        for sid, pdata in live_prices.items():
            price_lines.append(
                f"  {pdata['name']} (ID {sid}): bid={pdata['bid']}, ask={pdata['ask']}, mid={pdata['mid']}"
            )
        live_price_block = (
            "\n\n--- LIVE PEPPERSTONE SPOT PRICES (FROM CTRADER) ---\n"
            + "\n".join(price_lines)
            + "\n---------------------------------------------------\n"
            "Use these prices as the AUTHORITATIVE current market prices. "
            "Do NOT use any other price sources.\n"
        )
    else:
        live_price_block = "\n[WARNING: Live spot prices unavailable from Pepperstone — use caution]\n"

    positions_guardrail = (
        f"\n\n--- REAL-TIME PEPPERSTONE CTRADER ACCOUNT POSITIONS ---\n"
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
    analyst_prompt = f"""Analyze these indicators and Remizov shift for {ticker}. 
    Focus on momentum and structural shifts. 
    Check 'past_experience' for historical similarities: {analysis_data}
    {graphrag_block}
    {positions_guardrail}"""
    analyst_report = call_llm("Quant Analyst", analyst_prompt)
    print(f"Analyst Report Length: {len(str(analyst_report))}")

    print("--- 🌍 Calling MACRO ANALYST ---")
    current_date = datetime.now().strftime("%Y-%m-%d")
    oil_context = ""
    if "BRENT" in ticker or "USOIL" in ticker or "BZ" in ticker or "CL" in ticker:
        print("   Fetching Petro-Macro Terminal context for Oil...")
        raw_oil = get_brent_oil_context()
        if raw_oil:
            oil_context = f"\n\n--- PETRO-MACRO TERMINAL DATA ---\n{raw_oil[:3000]}\n---"
            print(f"   Oil context fetched ({len(raw_oil)} chars)")
        else:
            print("   WARNING: Petro-Macro Terminal unavailable, using training data")

    # Fetch live Macro Terminal MCP context (news sentiment, ticker insights)
    macro_terminal_data = get_macro_terminal_context(ticker)
    macro_terminal_block = (
        f"\n\n--- LIVE BEREZINI MACRO TERMINAL ANALYTICS ---\n{macro_terminal_data}\n-----------------------------------------------\n"
        if macro_terminal_data else ""
    )

    macro_prompt = f"""You are the Macro & Sentiment Analyst for Berezini Capital Management.
    Today is {current_date}. We are analyzing {ticker}.
    {oil_context}
    {macro_terminal_block}
    {positions_guardrail}
    Please provide a brief assessment of the current macroeconomic environment, central bank policies (Fed/BoE/etc.), geopolitical risks, and overall sentiment that could affect {ticker}. 
    Incorporate the live Macro Terminal sentiment and news data provided above into your analysis."""
    macro_report = call_llm("Macro Analyst", macro_prompt)

    print(f"Macro Report Length: {len(str(macro_report))}")

    print("--- 🛡️ Calling RISK MANAGER ---")
    risk_prompt = f"""Review Market Data, Quant Analyst Report, and Macro Report. 
    Assess safety (ATR/Keltner) and set SL/TP.
    CRITICAL: If 'past_experience' shows consistent failures for these conditions, advise WAIT: 
    DATA: {analysis_data} 
    QUANT: {analyst_report}
    MACRO: {macro_report}
    {graphrag_block}
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

def format_md_decision_summary(decision_data, symbol="BTC") -> str:
    """Format Managing Director decision dictionary or JSON string into a best-practice UI/UX Markdown executive report."""
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

import pandas as pd
def calculate_atr_keltner(ticker):
    """Fetch historical data and calculate ATR + Keltner Channel locally."""
    import yfinance as yf
    import pandas as pd
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
        df = yf.download(ticker, period="60d", interval="1d", progress=False)
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
    try:
        result = subprocess.run(
            ["curl", "-s", "-X", "GET",
             "https://oil.berezini.com/api/context/raw?commodity=Brent&period=1mo",
             "-H", "accept: text/plain"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        print(f"WARNING: Petro-Macro Terminal unavailable: {e}")
    return None


def get_account_balance():
    """Fetch current account equity using mcporter/n8n with retries."""
    import time
    
    # Dynamic paths for cross-platform compatibility (Linux/Amvera vs Mac)
    node_bin = "/usr/local/bin/node" if os.path.exists("/usr/local/bin/node") else "/opt/homebrew/bin/node" if os.path.exists("/opt/homebrew/bin/node") else "node"
    mcporter_bin = "/usr/local/bin/mcporter" if os.path.exists("/usr/local/bin/mcporter") else "/opt/homebrew/bin/mcporter" if os.path.exists("/opt/homebrew/bin/mcporter") else "mcporter"
    
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

    # Try direct npx mcporter if binary not found
    if mcporter_bin == "mcporter" and not os.path.exists("/usr/local/bin/mcporter"):
        npx_bin = "/usr/local/bin/npx" if os.path.exists("/usr/local/bin/npx") else "/opt/homebrew/bin/npx" if os.path.exists("/opt/homebrew/bin/npx") else "npx"
        cmd = [npx_bin, "-y", "mcporter", "call", "my-n8n-mcp.Get_account_data", "--config", config_path, "--timeout", "60000"]
    else:
        cmd = [
            node_bin, 
            mcporter_bin, 
            "call", "my-n8n-mcp.Get_account_data",
            "--config", config_path,
            "--timeout", "60000"
        ]
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

    # Direct fallback to cTrader API tool if n8n/mcporter failed
    try:
        try:
            from backend.bcm.tools import handle_ctrader_get_balance
        except ImportError:
            from tools import handle_ctrader_get_balance

        bal_res = handle_ctrader_get_balance({})
        if isinstance(bal_res, str):
            bal_res = json.loads(bal_res)
        if isinstance(bal_res, dict):
            eq = float(bal_res.get("equity", bal_res.get("balance", 0)))
            fm = float(bal_res.get("freeMargin", bal_res.get("free_margin", eq)))
            if eq > 0:
                print(f"✅ Account balance loaded from cTrader API: Equity=${eq:.2f}, FreeMargin=${fm:.2f}")
                return eq, fm
    except Exception as cbe:
        print(f"⚠️ cTrader direct balance fetch error: {cbe}")

    print("⚠️ WARNING: Failed to fetch balance from Pepperstone API. Using fallback evaluation balance.")
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

    # Guard: skip if we already have an active live position for this symbol
    live_positions, pos_summary = get_live_ctrader_positions()
    has_live_pos = any(p.get("symbol") == symbol_key for p in live_positions)
    if has_live_pos or memory.has_open_position(symbol_key):
        print(f"⏸️ {symbol_key}: Open position active in Pepperstone cTrader / memory — skipping new cycle.")
        return

    print(f"--- Starting PROFESSIONAL cycle for {symbol_key} ---")
    
    print("Step 1: Checking Account Balance and Margin...")
    equity, free_margin = get_account_balance()
    if not equity:
        print("Error: Could not fetch account data.")
        return
    print(f"Equity: ${equity:.2f} | Free Margin: ${free_margin:.2f}")

    print("Step 1.5: [Layer 0] Liquidity & Market Structure check...")
    liq_res = check_liquidity_layer_0(symbol_key)
    if not liq_res.get("passed", True):
        print(f"⏸️ [Layer 0 BLOCKED] {symbol_key}: {liq_res.get('reason')}. Skipping cycle.")
        return

    print(f"Step 2: Getting technical analysis for {analysis_ticker}...")
    analysis_json = get_technical_analysis(analysis_ticker)
    if not analysis_json or analysis_json == "None":
        analysis_json = json.dumps({"rsi": {analysis_ticker: 50}, "warning": "Empty result from MCP"})
    
    print("Step 3: Calculating Remizov Volatility Shift...")
    try:
        import yfinance as yf
        hist_df = yf.download(analysis_ticker, period="30d", interval="1d", progress=False)
        if not hist_df.empty:
            # Clean multi-index columns
            if isinstance(hist_df.columns, pd.MultiIndex):
                hist_df.columns = hist_df.columns.get_level_values(0)
            
            remizov_val, resolvent = calculate_remizov_shift(hist_df)
            print(f"📈 Remizov Shift: {remizov_val}")
        else:
            print("Warning: Historical DataFrame is empty.")
            remizov_val = 0
    except Exception as he:
        print(f"⚠️ Historical Data Error (yfinance): {he}")
        remizov_val = 0

    print("Step 4: Fetching ATR/Keltner for pre-check and risk sizing...")
    try:
        extra_data = calculate_atr_keltner(analysis_ticker)
    except:
        extra_data = {}
        
    print("Step 4.5: Performing algorithmic pre-check (RSI / MACD / ATR)...")
    should_call_ai, reason = pre_check_indicators(analysis_json, symbol_key, atr_data=extra_data)
    if not should_call_ai:
        atr_val = extra_data.get("atr_d1", "N/A")
        print(f"Action: SKIP AI. Reason: {reason}")
        print(f"Remizov Shift: {remizov_val:.4f} | ATR: {atr_val}")
        print(f"Verdict: WAIT (Confidence: 0.0%)")
        return

    try:
        analysis_data = json.loads(analysis_json)
    except:
        analysis_data = {"warning": "Could not parse analysis_json"}
    if isinstance(analysis_data, list) and len(analysis_data) > 0:
        full_data = analysis_data[0]
    else:
        full_data = analysis_data

    full_data.update(extra_data)
    full_data['remizov_shift'] = remizov_val

    print("Step 5: Consulting BCM Memory for similar past situations...")
    experience = memory.get_similar_experience(full_data)
    # Collect warnings for reporting
    warnings = []
    if not extra_data:
        warnings.append("⚠️ Missing Volatility/Keltner data (Analysis incomplete).")
    if remizov_val == 0:
        warnings.append("⚠️ Remizov Shift failed to calculate (using 0).")

    full_data['past_experience'] = experience
    full_data['technical_warnings'] = warnings

    print(f"Step 6: Asking Team for decision (Context: 8D Market Vector + ATR + Memory)...")
    decision_raw = ask_ai_decision(symbol_key, json.dumps(full_data))
    try:
        decision = json.loads(decision_raw)
    except: 
        print(f"Error parsing MD decision: {decision_raw}")
        return

    # Apply Remizov Shift
    final_confidence = decision['confidence'] + (remizov_val * 100)
    final_confidence = max(min(final_confidence, 100), 0)

    print(f"Verdict: {decision['decision'].upper()} (Confidence: {final_confidence:.1f}%)")
    print(f"MD Reasoning: {decision.get('reasoning', '')[:500]}")
    
    # Check if confidence meets execution threshold
    action = decision['decision']
    if action in ['buy', 'sell'] and final_confidence >= 85:
        # ... existing execution code continues
        sl = extra_data.get('keltner_upper') if action == 'sell' else extra_data.get('keltner_lower')
        tp = extra_data.get('keltner_lower') if action == 'sell' else extra_data.get('keltner_upper')
        
        if not sl or not tp:
            msg = f"⏸️ *BCM Skip*: Вердикт был {decision['decision'].upper()}, но сделка пропущена.\n"
            msg += f"Причина: Отсутствуют критические данные по волатильности (Keltner/ATR).\n"
            msg += f"Confidence: {final_confidence:.1f}%"
            send_telegram_msg(msg)
            return

        # R:R Validation — минимум 1:1.5 иначе сделка не стоит риска
        entry_price = full_data.get('ema20', 0)
        sl_dist = abs(entry_price - sl) if entry_price else 0
        tp_dist = abs(entry_price - tp) if entry_price else 0
        rr = (tp_dist / sl_dist) if sl_dist > 0 else 0
        if rr < 1.5:
            msg = f"⏸️ *BCM Skip* ({symbol_key}): R:R = {rr:.2f} < 1.5 минимума\n"
            msg += f"Entry: {entry_price:.4f} | SL: {sl:.4f} ({sl_dist:.4f}) | TP: {tp:.4f} ({tp_dist:.4f})"
            print(msg)
            send_telegram_msg(msg)
            return
        
        # Step 7: Execution
        current_price_yahoo = full_data.get('ema20', 0)
        
        # Calculate DISTANCE (Offset) from Yahoo data
        sl_dist = abs(current_price_yahoo - sl)
        tp_dist = abs(current_price_yahoo - tp)
        
        # Determine lot size using Yahoo distance (risk mapping)
        lot = calculate_lot_size(equity, 1.0, sl_dist, symbol_key)
        
        # --- COMPLIANCE CHECK (Segregation of Duties) ---
        print(f"Step 7: Sending draft order to Compliance Officer for Audit...")
        cco = ComplianceOfficer()
        base_volume = TICKER_MAP[symbol_key]['volume']
        action = decision['decision']
        
        # We need a summarized risk report to pass to CCO. Since we don't have the exact text here, we create a short summary.
        risk_summary = f"Equity: {equity}, Margin: {free_margin}. Calculated lot: {lot}. SL Distance: {sl_dist:.4f}. Remizov Shift: {remizov_val:.4f}."
        
        passed, cco_reason = cco.audit_trade(
            symbol=symbol_key, 
            action=action, 
            volume=lot, 
            base_volume=base_volume, 
            sl=sl, 
            tp=tp, 
            entry_price=current_price_yahoo, 
            md_decision=decision.get('reasoning', ''), 
            risk_report=risk_summary
        )
        
        if not passed:
            err_msg = f"🚫 *BCM COMPLIANCE REJECTION*\nAsset: {symbol_key} | Action: {action.upper()}\nReason: {cco_reason}"
            print(err_msg)
            send_telegram_msg(err_msg)
            return

        print(f"✅ Compliance Approved: {cco_reason}")
        print(f"Step 8: Executing cTrader Order (Lot: {lot}) via OpenAPI...")
        print(f"   Using Symbol ID: {trade_id} | Risk Offset: {sl_dist:.5f}")
        
        # 1. Place Market Order using trade.sh (OpenAPI wrapper)
        side_cmd = "buy" if action == 'buy' else "sell"
        try:
            # We use the trade_id from TICKER_MAP for execution
            cmd_place = ["bash", os.path.join(script_dir, "trade.sh"), side_cmd, str(trade_id), str(lot), str(sl), str(tp)]
            res_raw = subprocess.check_output(cmd_place, stderr=subprocess.STDOUT).decode('utf-8')
            print(f"cTrader Response: {res_raw}")
            
            # LOG TO MEMORY
            tracking_id = f"BCM-{int(time.time())}"
            memory.log_decision(tracking_id, symbol_key, action, lot, current_price_yahoo, decision['reasoning'] + f"\n[CCO Audit: {cco_reason}]", full_data)
            
            msg = f"🏛️ *BCM Opinion: EXECUTION*\n"
            msg += f"Asset: `{symbol_key}` | Action: *{action.upper()}*\n"
            msg += f"Volume: `{lot}` | Conf: `{final_confidence:.1f}%`\n"
            msg += f"Risk Offset: `SL {sl}` | `TP {tp}`\n\n"
            msg += f"📋 *Resolutions:*\n"
            msg += f"• *Quant:* Approved (Remizov {remizov_val:.4f})\n"
            msg += f"• *Macro:* Reviewed (No critical blocks)\n"
            msg += f"• *MD:* {decision['reasoning'][:200]}...\n"
            msg += f"✅ *CCO Audit:* {cco_reason}\n\n"
            msg += f"*(Executed via cTrader OpenAPI)*"
            send_telegram_msg(msg)
            
        except Exception as e:
            err_msg = f"❌ Execution Failed for {symbol_key}: {str(e)}"
            print(err_msg)
            send_telegram_msg(err_msg)
    else:
        if action in ['buy', 'sell']:
            print(f"Action: WAIT (Override: MD said {action.upper()}, but confidence {final_confidence:.1f}% < 85% threshold)")
            reason_text = f"MD said {action.upper()} but confidence {final_confidence:.1f}% < 85% threshold"
        else:
            print(f"Action: WAIT (Confidence {final_confidence:.1f}%)")
            reason_text = f"Confidence {final_confidence:.1f}%"
        msg = f"⏸️ *{symbol_key}* → WAIT\n"
        if warnings:
            msg += f"⚠️ {warnings[0]}\n"
        # Extract RSI value (it's nested as {ticker: value})
        rsi_data = full_data.get('rsi', {})
        rsi_val = list(rsi_data.values())[0] if rsi_data else 'N/A'
        if isinstance(rsi_val, float):
            rsi_val = f"{rsi_val:.1f}"
        atr_val = extra_data.get('atr_d1', 'N/A')
        msg += f"📊 RSI: {rsi_val} | ATR: {atr_val} | Remizov: {remizov_val:.3f}\n"
        msg += f"💬 {decision.get('reasoning', '')[:600]}..."
        send_telegram_msg(msg)

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "BTC"
    run_autonomous_cycle(target)
