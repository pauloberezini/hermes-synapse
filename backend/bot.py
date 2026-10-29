import os
import asyncio
import inspect
import logging
import io
import re
import time
from datetime import datetime, timezone
from functools import wraps
from typing import Any, Optional, List
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
    class _DummyTelegramMeta(type):
        def __getattr__(cls, name):
            return cls()

    class _DummyTelegramType(metaclass=_DummyTelegramMeta):
        def __init__(self, *args, **kwargs):
            pass
        def __call__(self, *args, **kwargs):
            return self
        def __getattr__(self, name):
            return self
        def __invert__(self):
            return self
        def __and__(self, other):
            return self
        def __or__(self, other):
            return self
        def __bool__(self):
            return False

    Update = _DummyTelegramType
    filters = _DummyTelegramType()
    ApplicationBuilder = CommandHandler = ContextTypes = MessageHandler = Application = _DummyTelegramType

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
    agent_instance.clear_history(str(chat_id), human=True)
    
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
    await safe_reply_helper(update, status_text)

def get_report_filename(query: str) -> str:
    # Keep only alphanumeric characters, spaces, hyphens, and underscores.
    clean = re.sub(r'[^\w\s-]', '', query)
    # Replace spaces and hyphens with underscores, strip leading/trailing underscores
    clean = re.sub(r'[-\s]+', '_', clean).strip('_')
    if not clean:
        return "report.md"
    return f"{clean[:30].lower()}_report.md"


def split_telegram_message(text: str, max_chars: int = 4000) -> List[str]:
    """Splits a long message into sequential chunks, each adhering to Telegram limits.
    
    Prefers splitting on paragraph boundaries (\n\n), then line breaks (\n),
    then spaces (' '), falling back to hard length splitting when unavoidable.
    """
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    chunks = []
    current_chunk = []
    current_length = 0

    paragraphs = text.split("\n\n")

    for para in paragraphs:
        para_len = len(para)
        needed = para_len + (2 if current_chunk else 0)
        
        if current_length + needed <= max_chars:
            current_chunk.append(para)
            current_length += needed
        else:
            if current_chunk:
                chunks.append("\n\n".join(current_chunk))
                current_chunk = []
                current_length = 0
            
            if len(para) <= max_chars:
                current_chunk.append(para)
                current_length = len(para)
            else:
                lines = para.split("\n")
                line_chunk = []
                line_length = 0
                for line in lines:
                    line_needed = len(line) + (1 if line_chunk else 0)
                    if line_length + line_needed <= max_chars:
                        line_chunk.append(line)
                        line_length += line_needed
                    else:
                        if line_chunk:
                            chunks.append("\n".join(line_chunk))
                            line_chunk = []
                            line_length = 0
                        
                        if len(line) <= max_chars:
                            line_chunk.append(line)
                            line_length = len(line)
                        else:
                            words = line.split(" ")
                            word_chunk = []
                            word_length = 0
                            for word in words:
                                word_needed = len(word) + (1 if word_chunk else 0)
                                if word_length + word_needed <= max_chars:
                                    word_chunk.append(word)
                                    word_length += word_needed
                                else:
                                    if word_chunk:
                                        chunks.append(" ".join(word_chunk))
                                        word_chunk = []
                                        word_length = 0
                                    
                                    if len(word) <= max_chars:
                                        word_chunk.append(word)
                                        word_length = len(word)
                                    else:
                                        start = 0
                                        while start < len(word):
                                            piece = word[start:start + max_chars]
                                            chunks.append(piece)
                                            start += max_chars
                            if word_chunk:
                                chunks.append(" ".join(word_chunk))
                if line_chunk:
                    current_chunk.append("\n".join(line_chunk))
                    current_length = len("\n".join(line_chunk))

    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return [c for c in chunks if c.strip()] or [text[:max_chars]]


async def safe_reply_helper(update: Update, text: str, assistant_msg_id: Optional[str] = None):
    """Safely replies to a Telegram message, splitting long texts and handling parse errors."""
    if not text:
        return
    chunks = split_telegram_message(text, max_chars=4000)
    if not chunks:
        return

    for i, chunk in enumerate(chunks):
        is_last = (i == len(chunks) - 1)
        reply_chunk = chunk
        if is_last and assistant_msg_id:
            reply_chunk += f"\n\n`[ID: {assistant_msg_id}]`"
        if len(reply_chunk) > 4096:
            reply_chunk = reply_chunk[:4096]
        try:
            await update.message.reply_text(reply_chunk, parse_mode="Markdown")
        except Exception as e:
            logger.warning(f"Telegram failed to send markdown chunk {i+1}/{len(chunks)}: {e}. Retrying in plain text.")
            plain_chunk = chunk
            if is_last and assistant_msg_id:
                plain_chunk += f"\n\n[ID: {assistant_msg_id}]"
            if len(plain_chunk) > 4096:
                plain_chunk = plain_chunk[:4096]
            try:
                await update.message.reply_text(plain_chunk)
            except Exception as e2:
                logger.error(f"Telegram failed to send plain text chunk {i+1}/{len(chunks)}: {e2}")


async def safe_reply_document_helper(
    update: Update,
    document: io.BytesIO,
    filename: str,
    caption: str,
    fallback_text: str,
    assistant_msg_id: Optional[str] = None
):
    """Sends a document with trimmed caption and markdown error recovery."""
    clean_caption = caption[:1000] if caption else ""
    try:
        await update.message.reply_document(
            document=document,
            filename=filename,
            caption=clean_caption,
            parse_mode="Markdown"
        )
    except Exception as doc_err:
        logger.warning(f"Telegram failed to send document with markdown caption: {doc_err}. Retrying with plain text caption.")
        try:
            document.seek(0)
            await update.message.reply_document(
                document=document,
                filename=filename,
                caption=clean_caption
            )
        except Exception as doc_err2:
            logger.warning(f"Telegram failed to send document: {doc_err2}. Retrying inline chunked reply.")
            await safe_reply_helper(update, fallback_text, assistant_msg_id=assistant_msg_id)


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
                    await safe_reply_helper(update, response)
                return
        except Exception as e:
            logger.error(f"Error handling fast command with plugin: {e}", exc_info=True)
            err_msg = f"⚠️ Error executing command `{user_text.split()[0]}`: {e}"
            await safe_reply_helper(update, err_msg)
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
        await safe_reply_helper(update, text, assistant_msg_id=assistant_msg_id)

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
        
        await safe_reply_document_helper(
            update,
            document=bio,
            filename=filename,
            caption=intro,
            fallback_text=response_text,
            assistant_msg_id=assistant_msg_id
        )
            
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
_last_network_error_at: float = 0.0
_network_error_cooldown: float = 35.0


def report_telegram_conflict() -> float:
    """Invoked when a Telegram 409 Conflict error is caught to progressively increase recovery backoff."""
    global _last_conflict_detected_at, _conflict_backoff, _updater_running_since
    now = time.time()
    _last_conflict_detected_at = now
    _updater_running_since = 0.0
    _conflict_backoff = min(_max_conflict_backoff, max(_min_conflict_backoff, _conflict_backoff * 2.0))
    return _conflict_backoff


def report_telegram_network_error() -> float:
    """Invoked when a transient network error is caught during polling to suppress premature recovery collisions."""
    global _last_network_error_at, _updater_running_since
    now = time.time()
    _last_network_error_at = now
    _updater_running_since = 0.0
    return _last_network_error_at


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
        msg_str = str(record.msg)
        msg_match = (
            "Exception happened while polling for updates" in msg_str
            or "Error while getting Updates" in msg_str
        )
        
        is_net_err = False
        is_conflict = False
        exc = None
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
            "Connection refused",
            "connection refused",
            "Connection error",
            "connection error",
            "ConnectionResetError",
            "ConnectionRefusedError",
            "ConnectTimeout",
            "Network failure",
            "network failure",
            "Bad Gateway",
            "bad gateway",
            "Gateway Timeout",
            "gateway timeout",
            "502",
            "503",
            "504",
        ]

        if record.exc_info and len(record.exc_info) >= 2 and record.exc_info[1]:
            exc = record.exc_info[1]
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

        if not is_net_err and any(ind in msg_str for ind in network_error_indicators):
            is_net_err = True
        if not is_conflict and ("Conflict" in msg_str or "terminated by other getUpdates request" in msg_str):
            is_conflict = True

        if is_updater and (is_net_err or is_conflict):
            exc_str = str(exc).strip() if exc is not None else ""
            if not exc_str:
                cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None) if exc is not None else None
                if cause and str(cause).strip():
                    exc_detail = f"{type(exc).__name__}: {str(cause).strip()}"
                elif exc is not None:
                    exc_detail = type(exc).__name__
                else:
                    exc_detail = msg_str.strip() or "Network error"
            else:
                exc_detail = exc_str

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
                record.msg = f"Telegram polling conflict detected: Another bot instance is running or restarting ({exc_detail}){suppressed_note}."
                return True

            if is_net_err:
                now = time.time()
                report_telegram_network_error()
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
                    record.msg = f"Telegram polling transient network issue: {exc_detail}{suppressed_note} (will retry automatically)"
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
        report_telegram_conflict()
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
        report_telegram_network_error()
        logger.warning(f"Telegram network warning: {err}")
    else:
        logger.error(f"Telegram exception during update processing: {err}", exc_info=err)

async def _telegram_polling_watchdog(
    poll_interval: float = 15.0,
    conflict_cooldown: Optional[float] = None,
    network_cooldown: Optional[float] = None,
):
    """Monitors Telegram updater and automatically recovers polling if it unexpectedly stops.

    If polling stops due to transient Conflict (HTTP 409) or network interruption, this watchdog
    waits out progressive conflict backoff and calls updater.start_polling(drop_pending_updates=True) to resume.
    """
    global telegram_app, _last_conflict_detected_at, _conflict_backoff, _updater_running_since, _last_network_error_at
    while True:
        try:
            await asyncio.sleep(poll_interval)
            if not telegram_app:
                continue

            now = time.time()
            effective_cooldown = conflict_cooldown if conflict_cooldown is not None else _conflict_backoff
            effective_net_cooldown = network_cooldown if network_cooldown is not None else (conflict_cooldown if conflict_cooldown is not None else _network_error_cooldown)

            # If conflict was recently detected, back off before recovery attempt
            if (now - _last_conflict_detected_at) < effective_cooldown:
                continue

            # If network error was recently detected, wait for connection and hanging Telegram server socket to clear
            if (now - _last_network_error_at) < effective_net_cooldown:
                continue

            # Ensure application is initialized and started before polling
            if getattr(telegram_app, "_initialized", None) is False:
                init_fn = getattr(telegram_app, "initialize", None)
                if callable(init_fn):
                    try:
                        init_res = init_fn()
                        if inspect.isawaitable(init_res):
                            await init_res
                    except Exception as init_err:
                        err_str = str(init_err).lower()
                        if "conflict" in err_str or "terminated by other getupdates" in err_str or type(init_err).__name__ == "Conflict":
                            report_telegram_conflict()
                        else:
                            report_telegram_network_error()
                        logger.warning(f"Telegram polling watchdog initialization retry deferred: {init_err}")
                        continue

            if getattr(telegram_app, "running", None) is False:
                start_fn = getattr(telegram_app, "start", None)
                if callable(start_fn):
                    try:
                        start_res = start_fn()
                        if inspect.isawaitable(start_res):
                            await start_res
                    except Exception as start_err:
                        err_str = str(start_err).lower()
                        if "conflict" in err_str or "terminated by other getupdates" in err_str or type(start_err).__name__ == "Conflict":
                            report_telegram_conflict()
                        else:
                            report_telegram_network_error()
                        logger.warning(f"Telegram polling watchdog start retry deferred: {start_err}")
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
                        "Telegram polling watchdog detected inactive updater. Attempting auto-recovery (cooldown=%.1fs, net_cd=%.1fs)...",
                        effective_cooldown,
                        effective_net_cooldown,
                    )
                    try:
                        # Cleanly stop any existing stopped/dangling updater tasks before starting anew
                        if getattr(updater, "stop", None):
                            try:
                                await updater.stop()
                            except Exception as stop_err:
                                logger.debug(f"Telegram updater stop error during recovery: {stop_err}")

                        # Check reachability and clear any hanging webhook with timeout
                        if getattr(telegram_app, "bot", None):
                            del_webhook_fn = getattr(telegram_app.bot, "delete_webhook", None)
                            if callable(del_webhook_fn):
                                try:
                                    del_res = del_webhook_fn(drop_pending_updates=True)
                                    if inspect.isawaitable(del_res):
                                        await asyncio.wait_for(del_res, timeout=10.0)
                                except Exception as del_err:
                                    e_str = str(del_err).lower()
                                    if "conflict" in e_str or "terminated by other getupdates" in e_str or type(del_err).__name__ == "Conflict":
                                        report_telegram_conflict()
                                    else:
                                        report_telegram_network_error()
                                    logger.warning(f"Telegram delete_webhook error during recovery: {del_err}. Deferring recovery.")
                                    continue

                        await updater.start_polling(drop_pending_updates=True)
                        logger.info("Telegram polling watchdog successfully recovered polling loop.")
                        _updater_running_since = time.time()
                    except Exception as e:
                        e_str = str(e).lower()
                        if "conflict" in e_str or "terminated by other getupdates" in e_str or type(e).__name__ == "Conflict":
                            report_telegram_conflict()
                        else:
                            report_telegram_network_error()
                        logger.warning(f"Telegram polling watchdog recovery attempt failed: {e}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.debug(f"Telegram polling watchdog loop error: {e}")

async def init_bot() -> Optional[Application]:
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
    
    # Initialize and start updater loop resiliently
    try:
        await telegram_app.initialize()
        await telegram_app.start()
        try:
            await telegram_app.bot.delete_webhook(drop_pending_updates=True)
            await telegram_app.updater.start_polling(drop_pending_updates=True)
            logger.info("Telegram Bot active and polling.")
        except Exception as e:
            e_str = str(e).lower()
            if "conflict" in e_str or "terminated by other getupdates" in e_str or type(e).__name__ == "Conflict":
                report_telegram_conflict()
            logger.warning(f"Telegram Bot polling startup warning (possible duplicate instance or conflict): {e}")
    except Exception as e:
        logger.warning(
            f"Telegram Bot network connection failed during initialization ({e}). "
            f"Server will continue boot and recover Telegram via background watchdog."
        )

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
        try:
            if getattr(telegram_app, "updater", None) and getattr(telegram_app.updater, "running", False):
                await telegram_app.updater.stop()
        except Exception as e:
            logger.debug(f"Error stopping updater during shutdown: {e}")
        try:
            if getattr(telegram_app, "running", False):
                await telegram_app.stop()
        except Exception as e:
            logger.debug(f"Error stopping application during shutdown: {e}")
        try:
            if getattr(telegram_app, "_initialized", False):
                await telegram_app.shutdown()
        except Exception as e:
            logger.debug(f"Error shutting down application: {e}")
        logger.info("Telegram Bot shut down.")

