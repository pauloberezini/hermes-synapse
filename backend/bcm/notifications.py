import os
import requests
import time
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("jarvis.bcm.notifications")

class NotificationProvider(ABC):
    @abstractmethod
    def send(self, message: str):
        pass

class ConsoleNotificationProvider(NotificationProvider):
    def send(self, message: str):
        print(f"[CONSOLE NOTIFICATION] {message}")
        logger.info(message)

class TelegramNotificationProvider(NotificationProvider):
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, message: str):
        if not self.bot_token or not self.chat_id:
            logger.warning("TelegramNotificationProvider initialized without token or chat_id.")
            return

        from datetime import datetime, timezone, timedelta
        israel_tz = timezone(timedelta(hours=3))
        now = datetime.now(israel_tz)
        il_time = now.strftime("%d/%m %H:%M IDT")
        
        formatted_message = f"[{il_time}] {message}"
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {"chat_id": self.chat_id, "text": formatted_message, "parse_mode": "Markdown"}
        
        for attempt in range(3):
            try:
                response = requests.post(url, json=payload, timeout=10)
                if response.status_code == 200:
                    return
                else:
                    logger.warning(f"Telegram send failed: {response.status_code} - {response.text}")
            except Exception as e:
                logger.warning(f"Telegram Attempt {attempt+1} failed: {e}")
                time.sleep(2)

class AppriseNotificationProvider(NotificationProvider):
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: str):
        if not self.webhook_url:
            return
        
        try:
            # Simple webhook post to an Apprise stateles endpoint or similar Webhook
            requests.post(self.webhook_url, json={"body": message}, timeout=10)
        except Exception as e:
            logger.warning(f"Apprise webhook failed: {e}")

def get_notifier() -> NotificationProvider:
    provider = os.environ.get("NOTIFICATION_PROVIDER", "telegram").lower()
    
    if provider == "apprise":
        webhook = os.environ.get("NOTIFICATION_URL")
        if webhook:
            return AppriseNotificationProvider(webhook)
        else:
            logger.warning("Apprise selected but NOTIFICATION_URL not set. Falling back to console.")
            return ConsoleNotificationProvider()
            
    elif provider == "console":
        return ConsoleNotificationProvider()
        
    else:
        # Default to Telegram if tokens exist, otherwise console
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        
        if bot_token and chat_id:
            return TelegramNotificationProvider(bot_token, chat_id)
        else:
            return ConsoleNotificationProvider()
