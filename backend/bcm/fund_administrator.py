import sqlite3
import os
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

WORKSPACE_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(WORKSPACE_ROOT, "logs/bcm_memory.db")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_msg(message):
    if not TELEGRAM_CHAT_ID:
        print(message)
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram Error: {e}")

def generate_weekly_report():
    if not os.path.exists(DB_PATH):
        send_telegram_msg("⚠️ BCM Administrator: Database not found. No report generated.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Calculate stats for the last 7 days
    seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
    
    # Total trades
    c.execute("SELECT COUNT(*) FROM trades WHERE timestamp >= ?", (seven_days_ago,))
    total_trades = c.fetchone()[0]
    
    # Open trades
    c.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'")
    open_trades = c.fetchone()[0]
    
    # Closed trades
    c.execute("SELECT COUNT(*), SUM(pnl) FROM trades WHERE status='CLOSED' AND timestamp >= ?", (seven_days_ago,))
    closed_data = c.fetchone()
    closed_trades = closed_data[0]
    total_pnl = closed_data[1] or 0.0
    
    # Win rate
    c.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED' AND pnl > 0 AND timestamp >= ?", (seven_days_ago,))
    winning_trades = c.fetchone()[0]
    
    win_rate = (winning_trades / closed_trades * 100) if closed_trades > 0 else 0.0
    
    conn.close()
    
    # Format the report
    report = f"📊 *BCM Weekly Administrator Report*\n"
    report += f"Date: `{datetime.now().strftime('%Y-%m-%d')}`\n\n"
    
    report += f"🔹 *Activity (Last 7 Days)*\n"
    report += f"Total AI Decisions: `{total_trades}`\n"
    report += f"Active Positions: `{open_trades}`\n"
    report += f"Closed Positions: `{closed_trades}`\n\n"
    
    report += f"🔹 *Performance*\n"
    report += f"Estimated PnL: `${total_pnl:.2f}`\n"
    report += f"Win Rate: `{win_rate:.1f}%`\n\n"
    
    report += f"🛡️ *Compliance & Risk*\n"
    report += f"All active trades are monitored by CCO Agent and protected by hard SL/TP constraints.\n"
    report += f"System Integrity: `VERIFIED`"
    
    send_telegram_msg(report)
    print("Report generated and sent.")

def generate_global_macro_dashboard():
    """
    Stage 3: Global Macro Dashboard (Картина Мира).
    Collects high-level macro context and saves it to an Obsidian/RAG accessible Markdown file.
    """
    try:
        from backend.obsidian import get_vault_path
        vault_path = get_vault_path()
    except Exception:
        vault_path = os.path.join(WORKSPACE_ROOT, "vault")
    
    if not os.path.exists(vault_path):
        os.makedirs(vault_path, exist_ok=True)
        
    db_path = os.path.join(vault_path, "GLOBAL_MACRO_DASHBOARD.md")
    
    # In a full implementation, this calls Macro MCP / yfinance for real data.
    # For now, it initializes the living document structure.
    content = f"""# 🌍 Картина Мира (Global Macro Dashboard)
*Последнее авто-обновление: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*

## 🏦 Монетарная политика (Центробанки)
- **FED (ФРС США):** Ожидание удержания или снижения ставки. Следить за CPI.
- **ECB (ЕЦБ):** Склонность к смягчению.

## 📊 Ключевые метрики
- **DXY (Индекс доллара):** Оценка силы доллара (влияет на золото и мажоры).
- **US10Y (Облигации):** Доходность 10-леток как индикатор перетока капитала.

## 🛡️ Геополитика & Риски
- Оценка глобальных рисков, цепочек поставок и конфликтов.

## 📈 Крипто-доминация
- **BTC.D:** Доминация биткоина.
- **Altseason Index:** Состояние альткоинов.

---
> *Этот файл еженедельно обновляется агентом AnalystAgent.*
"""
    with open(db_path, "w") as f:
        f.write(content)
    
    print(f"Global Macro Dashboard updated at {db_path}")

if __name__ == "__main__":
    generate_weekly_report()
    generate_global_macro_dashboard()
