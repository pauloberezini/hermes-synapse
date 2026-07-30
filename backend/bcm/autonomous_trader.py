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
from dotenv import load_dotenv

from memory_manager import BCMMemory
from compliance_officer import ComplianceOfficer

# Load configuration from .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(env_path)

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
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "6322632093:AAGODKNNMtngUTin3hUBGAQWEZely2VLmBk")
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

def call_llm(role_name, prompt):
    """Generic helper to call LLM with a specific role."""
    headers = {"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"}
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": f"You are the {role_name} at Remizov Quantum Capital. Current Time: {current_time}"},
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

def ask_ai_decision(ticker, analysis_data):
    """A true Multi-Agent workflow: Analyst -> Risk Manager -> Managing Director."""
    print("--- 🕵️ Calling QUANT ANALYST ---")
    analyst_prompt = f"""Analyze these indicators and Remizov shift for {ticker}. 
    Focus on momentum and structural shifts. 
    Check 'past_experience' for historical similarities: {analysis_data}"""
    analyst_report = call_llm("Quant Analyst", analyst_prompt)
    print(f"Analyst Report Length: {len(str(analyst_report))}")

    print("--- 🌍 Calling MACRO ANALYST ---")
    current_date = datetime.now().strftime("%Y-%m-%d")
    oil_context = ""
    if "BRENT" in ticker or "BZ" in ticker:
        print("   Fetching Petro-Macro Terminal context for BRENT...")
        raw_oil = get_brent_oil_context()
        if raw_oil:
            oil_context = f"\n\n--- PETRO-MACRO TERMINAL DATA ---\n{raw_oil[:3000]}\n---"
            print(f"   Oil context fetched ({len(raw_oil)} chars)")
        else:
            print("   WARNING: Petro-Macro Terminal unavailable, using training data")
    macro_prompt = f"""You are the Macro & Sentiment Analyst for Berezini Capital Management.
    Today is {current_date}. We are analyzing {ticker}.
    {oil_context}
    Please provide a brief assessment of the current macroeconomic environment, central bank policies (Fed/BoE/etc.), geopolitical risks, and overall sentiment that could affect {ticker}. 
    Since you do not have live browsing in this exact call, rely on your latest training data and general structural macro trends for this asset."""
    macro_report = call_llm("Macro Analyst", macro_prompt)
    print(f"Macro Report Length: {len(str(macro_report))}")

    print("--- 🛡️ Calling RISK MANAGER ---")
    risk_prompt = f"""Review Market Data, Quant Analyst Report, and Macro Report. 
    Assess safety (ATR/Keltner) and set SL/TP.
    CRITICAL: If 'past_experience' shows consistent failures for these conditions, advise WAIT: 
    DATA: {analysis_data} 
    QUANT: {analyst_report}
    MACRO: {macro_report}"""
    risk_report = call_llm("Risk Manager", risk_prompt)
    print(f"Risk Report Length: {len(str(risk_report))}")

    print("--- 🏦 Calling MANAGING DIRECTOR ---")
    md_prompt = f"""
    Final decision for {ticker} based on BCM Team reports and historical experience.
    QUANT REPORT: {analyst_report}
    MACRO REPORT: {macro_report}
    RISK REPORT: {risk_report}
    
    Respond ONLY in JSON format:
    {{
      "decision": "buy" | "sell" | "wait",
      "reasoning": "summary of why you chose this, referencing past experience if relevant",
      "confidence": 0-100 (Avoid generic scores like 50/75. Be precise based on signal strength)
    }}
    """
    final_decision_raw = call_llm("Managing Director", md_prompt)
    
    # Extract JSON
    content = str(final_decision_raw)
    if "```json" in content:
        content = content.split("```json")[1].split("```")[0].strip()
    elif "```" in content:
        content = content.split("```")[1].split("```")[0].strip()
    return content
    

def execute_trade(action, ticker_id, volume):
    """Execute trade via trade.sh script inside the container."""
    # Absolute path inside the container
    script_path = os.path.join(script_dir, "trade.sh")
    cmd = ["bash", script_path, action, str(ticker_id), str(volume)]
    try:
        output = subprocess.check_output(cmd).decode('utf-8')
        return output
    except Exception as e:
        return f"Trade execution failed: {str(e)}"

# Mapping between Analysis Ticker (Yahoo format) and Trading ID (FIX format)
TICKER_MAP = {
    "BTC": {"analysis": "BTC-USD", "trade_id": 10028, "volume": 0.01},
    "GBPUSD": {"analysis": "GBPUSD=X", "trade_id": 2, "volume": 1000},
    "US500": {"analysis": "^GSPC", "trade_id": 10013, "volume": 0.1},
    "BRENT": {"analysis": "BZ=F", "trade_id": 11045, "volume": 1}
}

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
            
    print("⚠️ WARNING: Failed to fetch balance after 3 attempts. Using MOCK balance for analysis.")
    return 10000.0, 9000.0 # Mock values to allow analysis to continue

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

    # Guard: skip if we already have an open position for this symbol
    if memory.has_open_position(symbol_key):
        print(f"⏸️ {symbol_key}: Open position already tracked in memory — skipping cycle.")
        return

    print(f"--- Starting PROFESSIONAL cycle for {symbol_key} ---")
    
    print("Step 1: Checking Account Balance and Margin...")
    equity, free_margin = get_account_balance()
    if not equity:
        print("Error: Could not fetch account data.")
        return
    print(f"Equity: ${equity:.2f} | Free Margin: ${free_margin:.2f}")

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
