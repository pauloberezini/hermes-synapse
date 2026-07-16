import os
import json
import asyncio
import logging
import time
from typing import List, Dict, Any, Optional
from backend.market_data import get_provider, CRYPTO_MAP

logger = logging.getLogger("hermes.price_monitor")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ALERTS_PATH = os.path.join(BASE_DIR, "data", "price_alerts.json")

class PriceMonitor:
    def __init__(self):
        self.alerts: List[Dict[str, Any]] = []
        self.load_alerts()
        self.monitor_task: Optional[asyncio.Task] = None
        self.provider = get_provider()

    def load_alerts(self):
        if os.path.exists(ALERTS_PATH):
            try:
                with open(ALERTS_PATH, "r") as f:
                    self.alerts = json.load(f)
                logger.info(f"Loaded {len(self.alerts)} active price alerts.")
            except Exception as e:
                logger.error(f"Failed to load price alerts: {e}")
                self.alerts = []
        else:
            self.alerts = []

    def save_alerts(self):
        try:
            os.makedirs(os.path.dirname(ALERTS_PATH), exist_ok=True)
            with open(ALERTS_PATH, "w") as f:
                json.dump(self.alerts, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save price alerts: {e}")

    def add_alert(self, symbol: str, target_price: float, condition: str, chat_id: str) -> Dict[str, Any]:
        alert_id = f"alert_{int(time.time())}_{symbol}"
        # Normalize symbol
        normalized_symbol = symbol.lower().strip()
        is_crypto = normalized_symbol in CRYPTO_MAP or normalized_symbol in CRYPTO_MAP.values()
        if is_crypto:
            coin_id = CRYPTO_MAP.get(normalized_symbol, normalized_symbol)
            display_name = coin_id.upper()
        else:
            coin_id = normalized_symbol.upper()  # Stock ticker
            display_name = coin_id

        alert = {
            "id": alert_id,
            "symbol": coin_id,
            "display_name": display_name,
            "is_crypto": is_crypto,
            "target_price": target_price,
            "condition": condition.lower().strip(), # "above" or "below"
            "chat_id": chat_id,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        self.alerts.append(alert)
        self.save_alerts()
        logger.info(f"Added price alert: {alert}")
        return alert

    def cancel_alert(self, alert_id: str) -> bool:
        for a in self.alerts:
            if a["id"] == alert_id:
                self.alerts.remove(a)
                self.save_alerts()
                logger.info(f"Cancelled price alert: {alert_id}")
                return True
        return False

    def get_alerts(self) -> List[Dict[str, Any]]:
        return self.alerts

    async def get_market_price(self, symbol: str) -> Optional[float]:
        normalized = symbol.lower().strip()
        is_crypto = normalized in CRYPTO_MAP or normalized in CRYPTO_MAP.values()
        if is_crypto:
            coin_id = CRYPTO_MAP.get(normalized, normalized)
            return await self.provider.get_price(coin_id, is_crypto=True)
        return await self.provider.get_price(symbol.upper().strip(), is_crypto=False)

    async def check_alerts_once(self):
        if not self.alerts:
            return

        logger.info(f"Checking {len(self.alerts)} active price alerts...")
        from backend.activity_logger import log_activity
        log_activity(
            activity_type="idle",
            source="PriceMonitor",
            message=f"Сканирование рынка: проверка {len(self.alerts)} активных оповещений цен котировок (затраты: $0.00)"
        )
        # Group unique symbols to fetch them efficiently
        unique_cryptos = set()
        unique_stocks = set()
        for a in self.alerts:
            if a["is_crypto"]:
                unique_cryptos.add(a["symbol"])
            else:
                unique_stocks.add(a["symbol"])

        current_prices = {}
        for coin_id in unique_cryptos:
            p = await self.provider.get_price(coin_id, is_crypto=True)
            if p is not None:
                current_prices[coin_id] = p

        for ticker in unique_stocks:
            p = await self.provider.get_price(ticker, is_crypto=False)
            if p is not None:
                current_prices[ticker] = p

        triggered = []
        for a in list(self.alerts):
            symbol = a["symbol"]
            if symbol not in current_prices:
                continue

            current_price = current_prices[symbol]
            target_price = a["target_price"]
            condition = a["condition"]

            is_triggered = False
            if condition == "above" and current_price >= target_price:
                is_triggered = True
            elif condition == "below" and current_price <= target_price:
                is_triggered = True

            if is_triggered:
                triggered.append((a, current_price))
                self.alerts.remove(a)

        if triggered:
            self.save_alerts()
            for alert, price in triggered:
                await self.trigger_alert(alert, price)

    async def trigger_alert(self, alert: Dict[str, Any], current_price: float):
        logger.info(f"Price alert triggered! {alert} Current price: {current_price}")
        from backend.activity_logger import log_activity
        cond_ru = "выше" if alert["condition"] == "above" else "ниже"
        log_activity(
            activity_type="idle",
            source="PriceMonitor",
            message=f"🔔 Оповещение сработало! Цена {alert['display_name']} стала ${current_price:.2f} (цель: {cond_ru} ${alert['target_price']:.2f})"
        )
        
        # Format text and send Telegram notification
        cond_str = "поднялась выше" if alert["condition"] == "above" else "опустилась ниже"
        msg = (
            f"📈 **ОПОВЕЩЕНИЕ О ЦЕНЕ, СЭР**\n\n"
            f"Рыночная цена **{alert['display_name']}** {cond_str} целевого значения!\n"
            f"• Целевая цена: **${alert['target_price']:,.2f}**\n"
            f"• Текущая цена: **${current_price:,.2f}**\n"
            f"• Статус: 🔔 Сработало"
        )
        
        try:
            from backend.scheduler import _send_telegram_alert
            await _send_telegram_alert(alert["chat_id"], msg)
        except Exception as e:
            logger.error(f"Failed to send Telegram alert: {e}")

        # Broadcast update to frontend WS
        try:
            from backend.websocket_manager import manager
            await manager.broadcast({
                "type": "price_alert_triggered",
                "alert": alert,
                "current_price": current_price
            })
        except Exception as e:
            logger.error(f"Failed to broadcast alert WS: {e}")

    async def run_loop(self):
        logger.info("Price alert monitoring loop started.")
        while True:
            try:
                await self.check_alerts_once()
            except Exception as e:
                logger.error(f"Error in price alert check loop: {e}")
            await asyncio.sleep(60) # Tick every 60 seconds

    def start(self):
        if not self.monitor_task or self.monitor_task.done():
            self.monitor_task = asyncio.create_task(self.run_loop())
            logger.info("Price monitor background task started.")

    def stop(self):
        if self.monitor_task and not self.monitor_task.done():
            self.monitor_task.cancel()
            logger.info("Price monitor background task stopped.")

price_monitor = PriceMonitor()
