import os
import logging
import io
import re
import asyncio
import tempfile
from functools import wraps
from telegram import BotCommand, Update
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
ACTIVE_CHAT_TASKS = {}
TELEGRAM_TEXT_LIMIT = 3900

MODE_PRESETS = {
    "fast": {"ollama_think": False, "fast_mode": True, "max_tokens": 768, "tool_max_tokens": 1024},
    "balanced": {"ollama_think": False, "fast_mode": False, "max_tokens": 2048, "tool_max_tokens": 2048},
    "deep": {"ollama_think": True, "fast_mode": False, "max_tokens": 4096, "tool_max_tokens": 4096},
}


def _split_telegram_text(text: str, limit: int = TELEGRAM_TEXT_LIMIT):
    """Split long replies on paragraph/line boundaries within Telegram's limit."""
    remaining = (text or "").strip()
    if not remaining:
        return ["Ответ модели пуст."]
    chunks = []
    while len(remaining) > limit:
        split_at = max(remaining.rfind("\n\n", 0, limit), remaining.rfind("\n", 0, limit), remaining.rfind(" ", 0, limit))
        if split_at < limit // 3:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    if remaining:
        chunks.append(remaining)
    return chunks


async def _reply_text(update: Update, text: str, footer: str = ""):
    if not update.message:
        return
    payload = (text or "").strip()
    if footer:
        payload = f"{payload}\n\n{footer}" if payload else footer
    for chunk in _split_telegram_text(payload):
        await update.message.reply_text(chunk)

# ponytail: Admin security decorator to block unauthorized users before calling agent/changing state. Supports multiple comma-separated IDs.
def admin_only(func):
    """Decorator to restrict handler access only to the authorized admin(s)."""
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        admin_id_str = os.getenv("TELEGRAM_ADMIN_ID") or os.getenv("TELEGRAM_CHAT_ID")
        if not admin_id_str:
            logger.error("TELEGRAM_ADMIN_ID or TELEGRAM_CHAT_ID must be configured in environment.")
            if update.message:
                await update.message.reply_text("Telegram-доступ не настроен. Обращение отклонено.")
            return
        
        # Split by comma and strip whitespace to support multiple admin IDs
        admin_ids = [aid.strip() for aid in admin_id_str.split(",") if aid.strip()]
        
        user = update.effective_user
        if not user or str(user.id) not in admin_ids:
            user_info = f"@{user.username}" if user and user.username else f"ID {user.id if user else 'Unknown'}"
            logger.warning(f"Unauthorized message attempt from {user_info}")
            if update.message:
                await update.message.reply_text("Доступ запрещён.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapper

def _is_allowed_chat(update: Update) -> bool:
    """Return True only for the configured private Telegram chat."""
    allowed_chat_ids = {
        value.strip()
        for value in os.getenv("TELEGRAM_CHAT_ID", "").split(",")
        if value.strip()
    }
    if not allowed_chat_ids:
        return True
    if not update.effective_chat:
        return False
    return str(update.effective_chat.id) in allowed_chat_ids

@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a greeting when /start is run."""
    if not _is_allowed_chat(update):
        logger.warning("Ignoring /start from unauthorized chat_id=%s", update.effective_chat.id if update.effective_chat else None)
        return

    chat_id = update.effective_chat.id
    username = update.effective_user.username or "creator"
    greeting = (
        f"Привет, @{username}. Я Vexa. Управляю локальной моделью, задачами и "
        "сервисами Hermes. Используй /help, чтобы открыть список команд."
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
    active = ACTIVE_CHAT_TASKS.get(chat_id)
    if active and not active.done():
        await _reply_text(update, "Сначала останови текущую генерацию командой /cancel.")
        return
    agent_instance.clear_history(str(chat_id))
    
    msg = "Контекст текущего Telegram-чата очищен."
    await update.message.reply_text(msg)
    
    await manager.broadcast({
        "type": "chat_message",
        "role": "system",
        "content": "History cleared by user.",
        "chat_id": chat_id
    })

@admin_only
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply with real host, model and runtime diagnostics."""
    if not _is_allowed_chat(update):
        logger.warning("Ignoring /status from unauthorized chat_id=%s", update.effective_chat.id if update.effective_chat else None)
        return

    chat_id = update.effective_chat.id
    history_len = len(agent_instance.get_history(str(chat_id)))
    from backend.tools import get_system_stats
    import json
    stats = json.loads(get_system_stats())
    host = stats.get("host") or {}
    cpu = host.get("cpu") or {}
    memory = host.get("memory") or {}
    gpus = host.get("gpus") or []
    containers = host.get("containers") or []
    unhealthy = [item.get("name") for item in containers if item.get("state") != "running" or item.get("health") == "unhealthy"]
    from backend.control_plane import get_control_state, list_tasks
    control_state = get_control_state()
    pending_approvals = len(list_tasks(limit=100, status="awaiting_approval"))
    think_enabled = str(agent_instance.ollama_think).lower() in {"true", "1", "yes", "on", "high", "medium", "low"}
    mode = "deep" if think_enabled else ("fast" if agent_instance.fast_mode else "balanced")
    gpu_summary = ", ".join(
        f"GPU {gpu.get('index')}: {gpu.get('memory_usage_percent', '—')}% VRAM, {gpu.get('temperature_celsius', '—')}°C"
        for gpu in gpus
    ) or "не обнаружены"
    status_text = (
        "Vexa / статус системы\n\n"
        f"Сервер: {host.get('hostname', 'нет данных')} · {stats.get('status', 'unknown')}\n"
        f"CPU: {cpu.get('usage_percent', '—')}% · load {cpu.get('load_1m', '—')}\n"
        f"RAM: {memory.get('usage_percent', '—')}%\n"
        f"GPU: {gpu_summary}\n"
        f"Docker: {len(containers) - len(unhealthy)}/{len(containers)} в норме"
        + (f" · проблемы: {', '.join(unhealthy)}" if unhealthy else "") + "\n\n"
        f"Control Plane: {'STOPPED' if control_state['kill_switch'] else 'ACTIVE'} · approval: {pending_approvals}\n"
        f"Модель: {agent_instance.model}\n"
        f"Режим: {mode} · think={agent_instance.ollama_think}\n"
        f"Лимит: {agent_instance.max_tokens} токенов · контекст: {agent_instance.ollama_num_ctx}\n"
        f"История чата: {history_len} сообщений"
    )
    await _reply_text(update, status_text)


@admin_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        return
    await _reply_text(update, (
        "Управление Vexa\n\n"
        "/status — сервер, GPU, Docker и модель\n"
        "/mode — текущий режим генерации\n"
        "/mode fast|balanced|deep — переключить режим\n"
        "/timers — активные таймеры и напоминания\n"
        "/stop <id> — остановить таймер или будильник\n"
        "/approvals — действия, ожидающие подтверждения\n"
        "/approve <task_id> — подтвердить этап действия\n"
        "/reject <task_id> — отклонить действие\n"
        "/halt — аварийно остановить Control Plane\n"
        "/resume — возобновить Control Plane\n"
        "/cancel — отменить текущую генерацию\n"
        "/clear — очистить контекст Telegram-чата\n"
        "/help — эта справка\n\n"
        "Обычный текст или голосовое сообщение отправляются локальной модели."
    ))


@admin_only
async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        return
    if not context.args:
        think_enabled = str(agent_instance.ollama_think).lower() in {"true", "1", "yes", "on", "high", "medium", "low"}
        current = "deep" if think_enabled else ("fast" if agent_instance.fast_mode else "balanced")
        await _reply_text(update, f"Текущий режим: {current}. Доступно: fast, balanced, deep.")
        return
    mode = context.args[0].strip().lower()
    if mode not in MODE_PRESETS:
        await _reply_text(update, "Неизвестный режим. Используй: /mode fast, /mode balanced или /mode deep.")
        return
    if any(not task.done() for task in ACTIVE_CHAT_TASKS.values()):
        await _reply_text(update, "Сначала дождись ответа или выполни /cancel, затем меняй режим.")
        return
    agent_instance.update_runtime_config(**MODE_PRESETS[mode])
    from backend.database import save_app_settings
    save_app_settings(agent_instance.get_runtime_config())
    await manager.broadcast({"type": "config_update", **agent_instance.get_runtime_config()})
    descriptions = {
        "fast": "без reasoning, короткие ответы",
        "balanced": "без reasoning, полный практический ответ",
        "deep": "reasoning включён, максимальный бюджет",
    }
    await _reply_text(update, f"Режим переключён: {mode} — {descriptions[mode]}.")


@admin_only
async def timers_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        return
    from backend.scheduler import get_all_timers
    items = get_all_timers()
    if not items:
        await _reply_text(update, "Активных таймеров, будильников и напоминаний нет.")
        return
    lines = ["Активные задачи:"]
    for item in items:
        remaining = item.get("time_left")
        suffix = f" · осталось {int(remaining)} с" if isinstance(remaining, (int, float)) else ""
        lines.append(f"{item.get('id')} · {item.get('label', item.get('type', 'задача'))} · {item.get('status', 'unknown')}{suffix}")
    await _reply_text(update, "\n".join(lines))


@admin_only
async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        return
    if not context.args:
        await _reply_text(update, "Укажи ID: /stop <id>. Список доступен через /timers.")
        return
    from backend.scheduler import cancel_recurring_reminder, cancel_timer_or_alarm
    item_id = context.args[0].strip()
    stopped = cancel_timer_or_alarm(item_id) or cancel_recurring_reminder(item_id)
    await _reply_text(update, f"Задача {item_id} остановлена." if stopped else f"Задача {item_id} не найдена.")


@admin_only
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update) or not update.effective_chat:
        return
    task = ACTIVE_CHAT_TASKS.get(update.effective_chat.id)
    if not task or task.done():
        await _reply_text(update, "Активной генерации нет.")
        return
    task.cancel()
    await _reply_text(update, "Останавливаю текущую генерацию.")


@admin_only
async def approvals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        return
    from backend.control_plane import get_control_state, list_tasks
    state = get_control_state()
    tasks = list_tasks(limit=20, status="awaiting_approval")
    lines = [
        f"Control Plane: {'STOPPED' if state['kill_switch'] else 'ACTIVE'}",
        f"Ожидают подтверждения: {len(tasks)}",
    ]
    for task in tasks:
        lines.append(
            f"{task['id']} · {task['risk_class']} · {task.get('tool_name') or task['goal']} "
            f"· {task['approval_count']}/{task['approvals_required']}"
        )
    if not tasks:
        lines.append("Очередь approval пуста.")
    await _reply_text(update, "\n".join(lines))


@admin_only
async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        return
    if not context.args:
        await _reply_text(update, "Укажи ID: /approve T-... Список: /approvals")
        return
    from backend.control_plane import approve_task, execute_governed_tool, get_task
    task_id = context.args[0].strip()
    try:
        task = approve_task(task_id, actor="owner:telegram")
    except KeyError:
        await _reply_text(update, f"Задача {task_id} не найдена.")
        return
    except ValueError as exc:
        await _reply_text(update, str(exc))
        return

    if task["status"] == "approved" and task.get("tool_name"):
        result = await asyncio.to_thread(
            execute_governed_tool,
            task["tool_name"],
            task.get("tool_arguments") or {},
            task.get("requester") or "telegram",
            approved_task_id=task_id,
        )
        task = get_task(task_id) or task
        await _reply_text(update, f"{task_id}: {task['status']}. Результат записан в Evidence Ledger.")
        return
    await _reply_text(
        update,
        f"{task_id}: подтверждение {task['approval_count']}/{task['approvals_required']}. "
        "Для R4 требуется второй явный /approve.",
    )


@admin_only
async def reject_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        return
    if not context.args:
        await _reply_text(update, "Укажи ID: /reject T-...")
        return
    from backend.control_plane import reject_task
    task_id = context.args[0].strip()
    try:
        task = reject_task(task_id, "Rejected from Telegram", actor="owner:telegram")
        await _reply_text(update, f"{task_id}: {task['status']}.")
    except KeyError:
        await _reply_text(update, f"Задача {task_id} не найдена.")
    except ValueError as exc:
        await _reply_text(update, str(exc))


@admin_only
async def halt_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        return
    from backend.control_plane import set_kill_switch
    state = set_kill_switch(True, "Emergency stop from Telegram", actor="owner:telegram")
    cancelled = 0
    for task in list(ACTIVE_CHAT_TASKS.values()):
        if not task.done():
            task.cancel()
            cancelled += 1
    await _reply_text(update, f"Control Plane остановлен. Отменено активных генераций: {cancelled}. {state['updated_at']}")


@admin_only
async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_allowed_chat(update):
        return
    from backend.control_plane import set_kill_switch
    state = set_kill_switch(False, "Resumed from Telegram", actor="owner:telegram")
    await _reply_text(update, f"Control Plane возобновлён. {state['updated_at']}")

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
        footer = f"[ID: {assistant_msg_id}]" if assistant_msg_id else ""
        await _reply_text(update, text, footer)

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
                intro = "Vexa подготовила подробный аналитический отчёт."
        else:
            intro = "Vexa подготовила подробный аналитический отчёт."
            
        intro += "\n\nПолная версия приложена в Markdown."
        if assistant_msg_id:
            intro += f"\n\n[ID: {assistant_msg_id}]"
        
        try:
            await update.message.reply_document(
                document=bio,
                filename=filename,
                caption=intro,
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
                        caption_text = f"График: {plot_file}"
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
                        caption_text = f"График: {plot_file}"
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

    await _run_user_request(update, context, update.message.text)


async def _run_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user_text: str):
    """Allow one cancellable model generation per Telegram chat."""
    if not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    current = asyncio.current_task()
    active = ACTIVE_CHAT_TASKS.get(chat_id)
    if active and active is not current and not active.done():
        await _reply_text(update, "Предыдущий запрос ещё выполняется. Используй /cancel, чтобы остановить его.")
        return
    ACTIVE_CHAT_TASKS[chat_id] = current
    try:
        await _process_user_text(update, context, user_text)
    except asyncio.CancelledError:
        logger.info("Telegram generation cancelled for chat_id=%s", chat_id)
        await manager.broadcast({
            "type": "chat_message",
            "role": "system",
            "content": "Генерация отменена из Telegram.",
            "chat_id": chat_id,
            "suppress_tts": True,
        })
    except Exception:
        logger.exception("Telegram request failed for chat_id=%s", chat_id)
        await _reply_text(update, "Не удалось обработать запрос. Состояние сервисов можно проверить через /status.")
    finally:
        if ACTIVE_CHAT_TASKS.get(chat_id) is current:
            ACTIVE_CHAT_TASKS.pop(chat_id, None)


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
            await update.message.reply_text("Не удалось распознать речь в голосовом сообщении.")
            return

        await update.message.reply_text(f"🎙️ Распознано: {user_text}")
        await _run_user_request(update, context, user_text)
    except Exception:
        logger.exception("Telegram voice transcription failed")
        await update.message.reply_text("Распознавание голосовых сообщений временно недоступно.")
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass

async def telegram_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    error = context.error
    exc_info = (type(error), error, error.__traceback__) if isinstance(error, BaseException) else False
    logger.error("Unhandled Telegram update error: %s", type(error).__name__, exc_info=exc_info)
    if isinstance(update, Update) and update.message:
        try:
            await update.message.reply_text("Внутренняя ошибка Telegram-обработчика. Проверь /status и повтори запрос.")
        except Exception:
            logger.debug("Could not report Telegram handler error to user", exc_info=True)


async def init_bot() -> Application:
    """Initializes the Telegram bot application, binds handlers, and starts polling."""
    global telegram_app
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        logger.error("TELEGRAM_BOT_TOKEN is not set. Bot will not run.")
        return None
        
    logger.info("Initializing Telegram bot...")
    telegram_app = (
        ApplicationBuilder()
        .token(token)
        .concurrent_updates(8)
        .connection_pool_size(16)
        .pool_timeout(10.0)
        .build()
    )
    
    # Bind commands
    telegram_app.add_handler(CommandHandler("start", start_command))
    telegram_app.add_handler(CommandHandler("clear", clear_command))
    telegram_app.add_handler(CommandHandler("status", status_command))
    telegram_app.add_handler(CommandHandler("help", help_command))
    telegram_app.add_handler(CommandHandler("mode", mode_command))
    telegram_app.add_handler(CommandHandler("timers", timers_command))
    telegram_app.add_handler(CommandHandler("stop", stop_command))
    telegram_app.add_handler(CommandHandler("cancel", cancel_command))
    telegram_app.add_handler(CommandHandler("approvals", approvals_command))
    telegram_app.add_handler(CommandHandler("approve", approve_command))
    telegram_app.add_handler(CommandHandler("reject", reject_command))
    telegram_app.add_handler(CommandHandler("halt", halt_command))
    telegram_app.add_handler(CommandHandler("resume", resume_command))
    
    # Bind message handlers
    telegram_app.add_handler(MessageHandler((filters.VOICE | filters.AUDIO) & ~filters.COMMAND, voice_handler))
    telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    telegram_app.add_error_handler(telegram_error_handler)
    
    # Initialize and start updater loop
    await telegram_app.initialize()
    try:
        await telegram_app.bot.set_my_commands([
            BotCommand("status", "Сервер, GPU, Docker и модель"),
            BotCommand("mode", "Режим fast / balanced / deep"),
            BotCommand("timers", "Активные таймеры и напоминания"),
            BotCommand("stop", "Остановить таймер по ID"),
            BotCommand("approvals", "Очередь подтверждений Control Plane"),
            BotCommand("approve", "Подтвердить действие по ID"),
            BotCommand("reject", "Отклонить действие по ID"),
            BotCommand("halt", "Аварийно остановить действия"),
            BotCommand("resume", "Возобновить Control Plane"),
            BotCommand("cancel", "Отменить текущую генерацию"),
            BotCommand("clear", "Очистить контекст этого чата"),
            BotCommand("help", "Список команд"),
        ])
    except Exception:
        logger.warning("Could not publish Telegram command menu", exc_info=True)
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
