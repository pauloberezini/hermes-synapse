import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import pytz

# Israel time helper (UTC+3 IDT)
ISRAEL_TZ = timezone(timedelta(hours=3))
def il_now():
    return datetime.now(ISRAEL_TZ).strftime("%d/%m %H:%M IDT")

# Each session fires 1 hour after its local market open
# ponytail: hourly cron resolution means +1h is the smallest unit; NY uses 10 (30min early) vs 10:30 actual open
SESSIONS = {
    "London":       {"tz": "Europe/London",    "open": 8},   # 08:00 → analyze at 09:00 (11:00 IDT)
    "New York":     {"tz": "America/New_York", "open": 9},   # 09:30 → analyze at 10:00 (17:00 IDT)
    "Tokyo/Sydney": {"tz": "Asia/Tokyo",       "open": 9},   # 09:00 → analyze at 10:00 (04:00 IDT)
}
SYMBOLS = ["BTC", "GBPUSD", "EURUSD", "US500", "BRENT", "USOIL", "GOLD"]

# Path to the venv python to ensure dependencies are available
VENV_PYTHON = "/opt/hermes/.venv/bin/python3"
if not os.path.exists(VENV_PYTHON):
    VENV_PYTHON = sys.executable  # Fallback to current interpreter

LOG_DIR = "/opt/data/skills/pepperstone-trader/logs"
TRADER_SCRIPT = "/opt/data/skills/pepperstone-trader/scripts/autonomous_trader.py"


def check_and_run():
    for session_name, cfg in SESSIONS.items():
        tz = pytz.timezone(cfg["tz"])
        local_time = datetime.now(tz)

        # WEEKEND CHECK: 5 is Saturday, 6 is Sunday
        if local_time.weekday() >= 5:
            continue

        # Fire exactly 1 hour after session open
        target_hour = cfg["open"] + 1
        if local_time.hour == target_hour:
            print(f"🎯 **Session Trigger: {session_name}** (open {cfg['open']}:00 → analysis at {target_hour}:00 local) [{il_now()}]")
            print(f"🔄 Checking: {', '.join(SYMBOLS)}")
            run_analysis(session_name)
            return  # Only trigger once per invocation


def run_one_symbol(symbol, reason):
    """Run the autonomous trader for a single symbol. Returns (symbol, verdict, reasoning, error_output)."""
    cmd = [VENV_PYTHON, TRADER_SCRIPT, symbol]
    try:
        result = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode("utf-8")

        verdict = "UNKNOWN"
        reasoning = ""
        for line in result.split("\n"):
            if line.startswith("Verdict:"):
                verdict = line.replace("Verdict:", "").strip()
            if line.startswith("MD Reasoning:"):
                reasoning = line.replace("MD Reasoning:", "").strip()

        # Log full success output
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(f"{LOG_DIR}/session_analysis.log", "a") as f:
            f.write(f"\n[{datetime.now()}] {reason} session analysis for {symbol}:\n{result}\n")

        return symbol, verdict, reasoning, None

    except subprocess.CalledProcessError as e:
        error_output = e.output.decode("utf-8")
        # Log full traceback
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(f"{LOG_DIR}/session_analysis.log", "a") as f:
            f.write(
                f"\n[{datetime.now()}] ❌ FAILED: {reason} session analysis for {symbol} (Exit {e.returncode}):\n{error_output}\n"
            )
        return symbol, None, None, error_output

    except Exception as e:
        return symbol, None, None, str(e)


def run_analysis(reason):
    """Run all symbols in parallel and collect results."""
    summary_lines = []

    # Run all 4 symbols concurrently — reduces wall-clock time from ~10min to ~3min
    with ThreadPoolExecutor(max_workers=len(SYMBOLS)) as executor:
        futures = {executor.submit(run_one_symbol, sym, reason): sym for sym in SYMBOLS}

        for future in as_completed(futures):
            symbol, verdict, reasoning, error = future.result()

            if error is not None:
                exit_hint = "(Exit 1)" if "returned non-zero" in error else ""
                summary_lines.append(f"❌ **{symbol}**: Analysis failed {exit_hint}".strip())
                print(f"Error running analysis for {symbol}: {error[:200]}")
            elif verdict and verdict != "UNKNOWN":
                summary_lines.append(f"🔹 **{symbol}**: {verdict} ({reasoning[:120]})")
            else:
                summary_lines.append(f"🔸 **{symbol}**: No clear verdict (check logs)")

    if summary_lines:
        # Sort to keep consistent order in output
        order = {sym: i for i, sym in enumerate(SYMBOLS)}
        summary_lines.sort(key=lambda l: next((order[s] for s in SYMBOLS if s in l), 99))
        print(f"\n📊 **Market Status ({reason} Session)** [{il_now()}]")
        print("\n".join(summary_lines))


if __name__ == "__main__":
    check_and_run()
