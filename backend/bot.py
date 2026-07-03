import os
import logging
import io
import re
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

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a greeting when /start is run."""
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

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Clears history context."""
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

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Processes any text message, runs agent loop, sends response, and broadcasts to dashboard."""
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    user_text = update.message.text
    
    # Broadcast user's message to dashboard UI immediately
    await manager.broadcast({
        "type": "chat_message",
        "role": "user",
        "content": user_text,
        "chat_id": chat_id
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
