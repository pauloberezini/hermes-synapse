import os
import logging
import io
import re
import asyncio
import tempfile
from functools import wraps
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
    Application
)
from backend.agent import agent_instance
from backend.websocket_manager import manager

logger = logging.getLogger("hermes.bot")

# Global Telegram Application instance
telegram_app: Application = None

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
                await update.message.reply_text("Access denied, Sir. I only respond to my designated Creator.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def _is_allowed_chat(update: Update) -> bool:
    """Return True only for the configured private Telegram chat."""
    allowed_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not allowed_chat_id:
        return True
    if not update.effective_chat:
        return False
    return str(update.effective_chat.id) == allowed_chat_id

@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a greeting when /start is run."""
    if not _is_allowed_chat(update):
        logger.warning("Ignoring /start from unauthorized chat_id=%s", update.effective_chat.id if update.effective_chat else None)
        return

    chat_id = update.effective_chat.id
    username = update.effective_user.username or "creator"
    
    greeting = (
        f"Greetings, Sir (@{username}). I am Hermes, your personal "
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
    if not _is_allowed_chat(update):
        logger.warning("Ignoring /clear from unauthorized chat_id=%s", update.effective_chat.id if update.effective_chat else None)
        return

    chat_id = update.effective_chat.id
    agent_instance.clear_history(str(chat_id))
    
    msg = "Current session memory cleared, Sir."
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
    if not _is_allowed_chat(update):
        logger.warning("Ignoring /status from unauthorized chat_id=%s", update.effective_chat.id if update.effective_chat else None)
        return

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

async def _process_user_text(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str):
    """Runs the agent loop for a text command from Telegram and mirrors it to the dashboard."""
    chat_id = update.effective_chat.id
    
    # Broadcast user's message to dashboard UI immediately
    await manager.broadcast({
        "type": "chat_message",
        "role": "user",
        "content": user_text,
        "chat_id": chat_id
    })
    
    async def keep_typing():
        while True:
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            except Exception:
                logger.debug("Telegram typing indicator failed", exc_info=True)
            await asyncio.sleep(4)

    typing_task = asyncio.create_task(keep_typing())
    try:
        response_text = await agent_instance.respond(user_text, session_id=str(chat_id))
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass
    
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
                intro = "Sir, I have prepared a detailed analytical report for you."
        else:
            intro = "Sir, I have prepared a detailed analytical report for you."
            
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
                        caption_text = f"🏛️ Sir, generated chart: {plot_file}"
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
                        caption_text = f"🏛️ Sir, generated chart: {plot_file}"
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
        "id": assistant_msg_id
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

@admin_only
async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes any text message, runs agent loop, sends response, and broadcasts to dashboard."""
    if not _is_allowed_chat(update):
        logger.warning("Ignoring message from unauthorized chat_id=%s", update.effective_chat.id if update.effective_chat else None)
        return

    if not update.message or not update.message.text:
        return

    await _process_user_text(update, context, update.message.text)


@admin_only
async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Downloads a Telegram voice/audio message, transcribes it locally, then handles it like text."""
    if not _is_allowed_chat(update):
        logger.warning("Ignoring voice message from unauthorized chat_id=%s", update.effective_chat.id if update.effective_chat else None)
        return

    if not update.message:
        return

    voice = update.message.voice
    audio = update.message.audio
    document = update.message.document
    telegram_file_ref = voice or audio or document
    if not telegram_file_ref:
        return

    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    suffix = ".oga" if voice else os.path.splitext(getattr(telegram_file_ref, "file_name", "") or "")[1] or ".audio"
    temp_path = None
    try:
        tg_file = await telegram_file_ref.get_file()
        with tempfile.NamedTemporaryFile(prefix="hermes_tg_voice_", suffix=suffix, delete=False) as tmp:
            temp_path = tmp.name

        await tg_file.download_to_drive(temp_path)

        from backend.voice import transcribe_audio_file
        result = await asyncio.to_thread(transcribe_audio_file, temp_path)
        user_text = (result.get("text") or "").strip()
        if not user_text:
            await update.message.reply_text("Sir, I could not detect speech in this voice message.")
            return

        await update.message.reply_text(f"🎙️ Распознано: {user_text}")
        await _process_user_text(update, context, user_text)
    except Exception as exc:
        logger.exception("Telegram voice transcription failed")
        await update.message.reply_text(f"Voice transcription is unavailable, Sir: {exc}")
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass

async def init_bot() -> Application:
    """Initializes the Telegram bot application, binds handlers, and starts polling."""
    global telegram_app
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Bot will not run.")
        return None
        
    logger.info("Initializing Telegram bot...")
    telegram_app = ApplicationBuilder().token(token).build()
    
    # Bind commands
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("clear", clear_command))
    telegram_app.add_handler(CommandHandler("status", status_command))
    
    # Bind message handlers
    telegram_app.add_handler(MessageHandler((filters.VOICE | filters.AUDIO) & ~filters.COMMAND, voice_handler))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # Initialize and start updater loop
    await telegram_app.initialize()
    await telegram_app.start()
    await telegram_app.updater.start_polling()
    logger.info("Telegram Bot active and polling.")
    return telegram_app

async def shutdown_bot():
    """Stops the Telegram bot polling and releases resources."""
    global telegram_app
    if telegram_app:
        logger.info("Stopping Telegram bot...")
        if telegram_app.updater and telegram_app.updater.running:
            await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()
        logger.info("Telegram Bot shut down.")
