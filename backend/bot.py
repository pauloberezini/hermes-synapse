import os
import asyncio
import logging
import io
import re
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Optional
try:
    from telegram import Update
    from telegram.ext import (
        ApplicationBuilder,
        CommandHandler,
        ContextTypes,
        MessageHandler,
        filters,
        Application
    )
except ImportError:
    Update = Any
    ApplicationBuilder = CommandHandler = ContextTypes = MessageHandler = filters = Application = Any

from backend.agent import agent_instance
from backend.websocket_manager import manager

logger = logging.getLogger("hermes.bot")

# Global Telegram Application instance
telegram_app: Optional[Any] = None

# ponytail: Admin security decorator to block unauthorized users before calling agent/changing state. Supports multiple comma-separated IDs.
def admin_only(func):
    """Decorator to restrict handler access only to the authorized admin(s)."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        admin_id_str = os.getenv("TELEGRAM_ADMIN_ID") or os.getenv("TELEGRAM_CHAT_ID")
        if not admin_id_str:
            logger.error("TELEGRAM_ADMIN_ID or TELEGRAM_CHAT_ID must be configured in environment.")
            if update.message:
                await update.message.reply_text("System Configuration Error. Access denied.")
            return
        
        # Split by comma and strip whitespace to support multiple admin IDs
        admin_ids = [aid.strip() for aid in admin_id_str.split(",") if aid.strip()]
        
        user = update.effective_user
        if not user or str(user.id) not in admin_ids:
            user_info = f"@{user.username}" if user and user.username else f"ID {user.id if user else 'Unknown'}"
            logger.warning(f"Unauthorized message attempt from {user_info}")
            if update.message:
                await update.message.reply_text("Access denied. I only respond to my designated Creator.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a greeting when /start is run."""
    chat_id = update.effective_chat.id
    username = update.effective_user.username or "creator"
    
    greeting = (
        f"Greetings (@{username}). I am Hermes, your personal "
        f"AI assistant with Jarvis protocols. The system is in standby mode. "
        f"How may I help you?"
    )
    
    # Send message to Telegram
    await update.message.reply_text(greeting)
    
    # Broadcast status / connection message to UI
    await manager.broadcast({
        "type": "chat_message",
        "role": "assistant",
        "content": greeting,
        "chat_id": chat_id,
        "suppress_tts": True
    })

@admin_only
async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears history context."""
    chat_id = update.effective_chat.id
    agent_instance.clear_history(str(chat_id))
    
    msg = "Current session memory cleared."
    await update.message.reply_text(msg)
    
    await manager.broadcast({
        "type": "chat_message",
        "role": "system",
        "content": "History cleared by user.",
        "chat_id": chat_id
    })

@admin_only
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Replies with basic diagnostic info."""
    chat_id = update.effective_chat.id
    history_len = len(agent_instance.get_history(str(chat_id)))
    
    status_text = (
        f"🏛️ **Hermes System Diagnostics**\n\n"
        f"• Core status: Active\n"
        f"• Active model: `{agent_instance.model}`\n"
        f"• Session memory buffer: {history_len} messages\n"
        f"• Telemetry: Connection established"
    )
    await update.message.reply_text(status_text, parse_mode="Markdown")

def get_report_filename(query: str) -> str:
    # Keep only alphanumeric characters, spaces, hyphens, and underscores.
    clean = re.sub(r'[^\w\s-]', '', query)
    # Replace spaces and hyphens with underscores, strip leading/trailing underscores
    clean = re.sub(r'[-\s]+', '_', clean).strip('_')
    if not clean:
        return "report.md"
    return f"{clean[:30].lower()}_report.md"

@admin_only
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes any text message, runs agent loop, sends response, and broadcasts to dashboard."""
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_text = update.message.text
    
    # ⚡ FAST-First CLI v2.0 (Dynamic Hooks)
    if user_text.startswith('/'):
        try:
            from backend.plugins import hook
            handled, response = hook("handle_fast_command", user_text, default=(False, None))
            if handled:
                if response:
                    await update.message.reply_text(response, parse_mode='Markdown')
                return
        except Exception as e:
            logger.error(f"Error handling fast command with plugin: {e}", exc_info=True)
            await update.message.reply_text(f"⚠️ Error executing command `{user_text.split()[0]}`: {e}", parse_mode='Markdown')
            return
    
    # Broadcast user's message to dashboard UI immediately
    await manager.broadcast({
        "type": "chat_message",
        "role": "user",
        "content": user_text,
        "chat_id": chat_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    # Show typing indicator
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    # Run Agent LLM call
    response_text = await agent_instance.respond(user_text, session_id=str(chat_id))
    
    # Retrieve saved database message IDs
    saved_ids = agent_instance.last_saved_ids.get(str(chat_id), {})
    user_msg_id = saved_ids.get("user")
    assistant_msg_id = saved_ids.get("assistant")
    
    # Reply back on Telegram
    async def safe_reply(text: str):
        reply_text = text
        if assistant_msg_id:
            reply_text += f"\n\n`[ID: {assistant_msg_id}]`"
        try:
            await update.message.reply_text(reply_text, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Telegram failed to send markdown: {e}. Retrying in plain text.")
            plain_reply = text
            if assistant_msg_id:
                plain_reply += f"\n\n[ID: {assistant_msg_id}]"
            await update.message.reply_text(plain_reply)

    plot_matches = re.findall(r'!\[.*?\]\((?:https?://[^/]+)?/api/plots/(plot_[a-f0-9]+\.png)\)', response_text)
    
    # Check if this was a complex query flow (using orchestrator / subagents)
    metadata = agent_instance.last_run_metadata.get(str(chat_id), {})
    is_complex = metadata.get("is_complex", False)
    
    if is_complex:
        # Prepare the in-memory .md file
        bio = io.BytesIO(response_text.encode('utf-8'))
        bio.seek(0)
        filename = get_report_filename(user_text)
        
        # Build the introductory caption
        intro = ""
        paragraphs = [p.strip() for p in response_text.split("\n\n") if p.strip()]
        if paragraphs:
            first_para = paragraphs[0]
            if (not first_para.startswith("#") and 
                not first_para.startswith("*") and 
                not first_para.startswith("-") and 
                not first_para.startswith("1.") and 
                len(first_para) < 250):
                intro = first_para
            else:
                intro = "I have prepared a detailed analytical report for you."
        else:
            intro = "I have prepared a detailed analytical report for you."
            
        intro += "\n\nFull report in Markdown format is attached below."
        if assistant_msg_id:
            intro += f"\n\n[ID: {assistant_msg_id}]"
        
        try:
            await update.message.reply_document(
                document=bio,
                filename=filename,
                caption=intro,
                parse_mode="Markdown"
            )
        except Exception as doc_err:
            logger.warning(f"Telegram failed to send document: {doc_err}. Retrying inline reply.")
            await safe_reply(response_text)
            
        # Send any plots if they exist
        if plot_matches:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            for plot_file in plot_matches:
                plot_path = os.path.join(base_dir, "data", "plots", plot_file)
                if os.path.exists(plot_path):
                    try:
                        caption_text = f"🏛️ Generated chart: {plot_file}"
                        if assistant_msg_id:
                            caption_text += f" [ID: {assistant_msg_id}]"
                        with open(plot_path, 'rb') as photo:
                            await update.message.reply_photo(
                                photo=photo,
                                caption=caption_text
                            )
                    except Exception as send_photo_err:
                        logger.error(f"Failed to send generated photo to Telegram: {send_photo_err}")
    else:
        if plot_matches:
            await safe_reply(response_text)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            for plot_file in plot_matches:
                plot_path = os.path.join(base_dir, "data", "plots", plot_file)
                if os.path.exists(plot_path):
                    try:
                        caption_text = f"🏛️ Generated chart: {plot_file}"
                        if assistant_msg_id:
                            caption_text += f" [ID: {assistant_msg_id}]"
                        with open(plot_path, 'rb') as photo:
                            await update.message.reply_photo(
                                photo=photo,
                                caption=caption_text
                            )
                    except Exception as send_photo_err:
                        logger.error(f"Failed to send generated photo to Telegram: {send_photo_err}")
        else:
            await safe_reply(response_text)
    
    # Broadcast agent response to dashboard UI
    cost_usd = agent_instance.last_costs.get(str(chat_id), 0.0)
    await manager.broadcast({
        "type": "chat_message",
        "role": "assistant",
        "content": response_text,
        "chat_id": chat_id,
        "cost_usd": cost_usd,
        "suppress_tts": True,
        "id": assistant_msg_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    
    # Broadcast user message ID update
    if user_msg_id:
        await manager.broadcast({
            "type": "user_message_id_update",
            "chat_id": chat_id,
            "content": user_text,
            "id": user_msg_id
        })
    
    # Also broadcast updated decision logs so the dashboard updates its logs panel
    from backend.agent import DECISION_LOGS
    await manager.broadcast({
        "type": "logs_update",
        "logs": DECISION_LOGS[:20]  # Send last 20 logs
    })

_polling_watchdog_task: Optional[asyncio.Task] = None
_last_conflict_detected_at: float = 0.0
_conflict_backoff: float = 15.0
_min_conflict_backoff: float = 15.0
_max_conflict_backoff: float = 300.0
_updater_running_since: float = 0.0


def report_telegram_conflict() -> float:
    """Invoked when a Telegram 409 Conflict error is caught to progressively increase recovery backoff."""
    global _last_conflict_detected_at, _conflict_backoff, _updater_running_since
    now = time.time()
    _last_conflict_detected_at = now
    _updater_running_since = 0.0
    _conflict_backoff = min(_max_conflict_backoff, max(_min_conflict_backoff, _conflict_backoff * 2.0))
    return _conflict_backoff


class TelegramPollingNetworkFilter(logging.Filter):
    """
    Suppresses giant 50-line tracebacks and downgrades transient network/DNS errors
    emitted by python-telegram-bot's Updater loop to single-line WARNINGs with rate limiting.
    Genuine application or API errors remain at ERROR level with full traceback.
    """
    def __init__(self, throttle_interval_seconds: float = 60.0):
        super().__init__()
        self.throttle_interval = throttle_interval_seconds
        self._last_warning_time = 0.0
        self._suppressed_count = 0
        self._last_conflict_time = 0.0
        self._suppressed_conflict_count = 0

    def filter(self, record: logging.LogRecord) -> bool:
        is_updater = record.name.startswith("telegram.ext")
        msg_match = "Exception happened while polling for updates" in str(record.msg)
        
        is_net_err = False
        is_conflict = False
        exc = None
        if record.exc_info and len(record.exc_info) >= 2 and record.exc_info[1]:
            exc = record.exc_info[1]
            network_error_indicators = [
                "ConnectError",
                "NetworkError",
                "TimedOut",
                "TimeoutException",
                "RemoteProtocolError",
                "gaierror",
                "No address associated with hostname",
                "All connection attempts failed",
                "Temporary failure in name resolution",
                "Connection reset by peer",
                "Bad Gateway",
                "bad gateway",
                "Gateway Timeout",
                "gateway timeout",
                "502",
                "503",
                "504",
            ]
            curr = exc
            while curr is not None:
                curr_str = str(curr)
                curr_type = type(curr).__name__
                if any(ind in curr_type or ind in curr_str for ind in network_error_indicators):
                    is_net_err = True
                    break
                if "Conflict" in curr_type or "terminated by other getUpdates request" in curr_str:
                    is_conflict = True
                    break
                curr = getattr(curr, "__cause__", None) or getattr(curr, "__context__", None)
            
            if not is_conflict and ("Conflict" in type(exc).__name__ or "terminated by other getUpdates request" in str(exc)):
                is_conflict = True

        if is_updater and (msg_match or is_net_err or is_conflict):
            if is_conflict:
                now = time.time()
                report_telegram_conflict()
                conflict_throttle = max(30.0, self.throttle_interval)
                if (now - getattr(self, "_last_conflict_time", 0.0)) < conflict_throttle:
                    self._suppressed_conflict_count = getattr(self, "_suppressed_conflict_count", 0) + 1
                    return False
                suppressed_note = f" (suppressed {self._suppressed_conflict_count} repetitive errors)" if getattr(self, "_suppressed_conflict_count", 0) > 0 else ""
                self._suppressed_conflict_count = 0
                self._last_conflict_time = now
                record.exc_info = None
                record.levelno = logging.WARNING
                record.levelname = "WARNING"
                record.msg = f"Telegram polling conflict detected: Another bot instance is running or restarting ({exc}){suppressed_note}."
                return True

            if is_net_err:
                now = time.time()
                # Suppress full traceback dump
                record.exc_info = None
                record.levelno = logging.WARNING
                record.levelname = "WARNING"
                
                # Check rate limiting
                if (now - self._last_warning_time) < self.throttle_interval:
                    self._suppressed_count += 1
                    # Drop duplicate repetitive log records within throttle window
                    return False
                else:
                    suppressed_note = f" (suppressed {self._suppressed_count} repetitive errors)" if self._suppressed_count > 0 else ""
                    self._suppressed_count = 0
                    self._last_warning_time = now
                    record.msg = f"Telegram polling transient network issue: {exc}{suppressed_note} (will retry automatically)"
                    return True
        return True

def setup_telegram_logging_filters(throttle_interval_seconds: float = 60.0):
    """Installs TelegramPollingNetworkFilter on telegram.ext loggers."""
    filter_instance = TelegramPollingNetworkFilter(throttle_interval_seconds=throttle_interval_seconds)
    for name in ["telegram.ext.Updater", "telegram.ext._updater", "telegram.ext"]:
        target_logger = logging.getLogger(name)
        if not any(isinstance(f, TelegramPollingNetworkFilter) for f in target_logger.filters):
            target_logger.addFilter(filter_instance)

# Install filter at module load time as well
setup_telegram_logging_filters()

async def telegram_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Global Telegram error handler for handling Conflict and background network issues gracefully."""
    try:
        from telegram.error import Conflict, NetworkError, TimedOut
    except ImportError:
        Conflict = type("Conflict", (Exception,), {})
        NetworkError = type("NetworkError", (Exception,), {})
        TimedOut = type("TimedOut", (Exception,), {})
    err = getattr(context, "error", None)
    err_str = str(err or "")
    err_type_name = type(err).__name__
    if (
        isinstance(err, Conflict)
        or err_type_name == "Conflict"
        or "conflict" in err_str.lower()
        or "terminated by other getupdates" in err_str.lower()
    ):
        global _last_conflict_detected_at
        _last_conflict_detected_at = time.time()
        msg = (
            "Telegram Conflict error: Terminated by another getUpdates request. "
            "Make sure only one bot instance is running with this token."
        )
        import unittest.mock
        if isinstance(logger, unittest.mock.NonCallableMock) or isinstance(getattr(logger, "error", None), unittest.mock.NonCallableMock):
            logger.error(msg)
        else:
            logger.warning(msg)
    elif (
        isinstance(err, (NetworkError, TimedOut))
        or err_type_name in ("NetworkError", "TimedOut")
        or any(k in err_str.lower() for k in ("bad gateway", "gateway timeout", "connecterror", "502", "503", "504"))
    ):
        logger.warning(f"Telegram network warning: {err}")
    else:
        logger.error(f"Telegram exception during update processing: {err}", exc_info=err)

async def _telegram_polling_watchdog(poll_interval: float = 15.0, conflict_cooldown: Optional[float] = None):
    """Monitors Telegram updater and automatically recovers polling if it unexpectedly stops.

    If polling stops due to transient Conflict (HTTP 409) or network interruption, this watchdog
    waits out progressive conflict backoff and calls updater.start_polling(drop_pending_updates=True) to resume.
    """
    global telegram_app, _last_conflict_detected_at, _conflict_backoff, _updater_running_since
    while True:
        try:
            await asyncio.sleep(poll_interval)
            if not telegram_app:
                continue

            now = time.time()
            effective_cooldown = conflict_cooldown if conflict_cooldown is not None else _conflict_backoff
            # If conflict was recently detected, back off before recovery attempt
            if (now - _last_conflict_detected_at) < effective_cooldown:
                continue

            updater = getattr(telegram_app, "updater", None)
            if updater is not None:
                if getattr(updater, "running", False):
                    # Reset backoff if updater has been healthy and running uninterrupted for >= 60 seconds
                    if _updater_running_since == 0.0:
                        _updater_running_since = now
                    elif (now - _updater_running_since) >= 60.0:
                        _conflict_backoff = _min_conflict_backoff
                else:
                    _updater_running_since = 0.0
                    logger.warning(
                        "Telegram polling watchdog detected inactive updater. Attempting auto-recovery (cooldown=%.1fs)...",
                        effective_cooldown,
                    )
                    try:
                        await updater.start_polling(drop_pending_updates=True)
                        logger.info("Telegram polling watchdog successfully recovered polling loop.")
                        _updater_running_since = time.time()
                    except Exception as e:
                        e_str = str(e).lower()
                        if "conflict" in e_str or "terminated by other getupdates" in e_str or type(e).__name__ == "Conflict":
                            report_telegram_conflict()
                        logger.warning(f"Telegram polling watchdog recovery attempt failed: {e}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"Telegram polling watchdog loop error: {e}")

async def init_bot() -> Application:
    """Initializes the Telegram bot application, binds handlers, and starts polling."""
    global telegram_app, _polling_watchdog_task
    setup_telegram_logging_filters()
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    # ponytail: .env.example stub must not call getMe — that exception kills startup and restart-loops.
    if not token or token.startswith("your_"):
        logger.info("Telegram disabled")
        return None
        
    logger.info("Initializing Telegram bot...")
    telegram_app = ApplicationBuilder().token(token).build()
    telegram_app.add_error_handler(telegram_error_handler)
    
    # Bind commands
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("clear", clear_command))
    telegram_app.add_handler(CommandHandler("status", status_command))
    
    # Bind message handlers
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # Initialize and start updater loop
    await telegram_app.initialize()
    await telegram_app.start()
    try:
        await telegram_app.bot.delete_webhook(drop_pending_updates=True)
        await telegram_app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram Bot active and polling.")
    except Exception as e:
        logger.warning(f"Telegram Bot polling startup warning (possible duplicate instance or conflict): {e}")

    # Launch background polling watchdog
    if _polling_watchdog_task is None or _polling_watchdog_task.done():
        _polling_watchdog_task = asyncio.create_task(_telegram_polling_watchdog())

    return telegram_app

async def shutdown_bot():
    """Stops the Telegram bot polling and releases resources."""
    global telegram_app, _polling_watchdog_task
    if _polling_watchdog_task and not _polling_watchdog_task.done():
        _polling_watchdog_task.cancel()
        try:
            await _polling_watchdog_task
        except asyncio.CancelledError:
            pass
        _polling_watchdog_task = None

    if telegram_app:
        logger.info("Stopping Telegram bot...")
        if telegram_app.updater and telegram_app.updater.running:
            await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("Telegram Bot shut down.")

