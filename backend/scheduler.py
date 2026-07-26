"""
backend/scheduler.py — APScheduler 3.x + SQLiteJobStore

All scheduled jobs are persisted automatically to backend/data/hermes.db
and restored on every process startup — no manual save/restore needed.

Public API (unchanged from previous implementation):
  add_timer(label, duration_seconds, chat_id, agent_id, prompt) -> str
  add_alarm(time_str, label, chat_id, agent_id, prompt) -> str
  add_recurring_reminder(label, interval_hours, chat_id, agent_id, prompt) -> str
  cancel_timer_or_alarm(item_id) -> bool
  cancel_recurring_reminder(reminder_id) -> bool
  get_all_timers() -> List[Dict]
  get_all_reminders() -> List[Dict]
  start_skill_distillation_loop(interval_seconds) -> asyncio.Task
  _send_telegram_alert(chat_id, text)   # used by price_monitor.py
"""

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger("hermes.scheduler")

# ─── Scheduler singleton ────────────────────────────────────────────────────────
_DB_URL = os.environ.get(
    "SCHEDULER_DB_URL",
    "sqlite:////app/backend/data/hermes.db",
)

_jobstore = SQLAlchemyJobStore(url=_DB_URL, tablename="apscheduler_jobs")
scheduler = AsyncIOScheduler(
    jobstores={"default": _jobstore},
    job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 3600},
    timezone="Asia/Jerusalem",
)

# Fire-count is cosmetic and session-local (acceptable to reset on restart)
_fire_counts: Dict[str, int] = {}

# Supplementary in-memory metadata dict rebuilt on startup from job kwargs
_timer_meta: Dict[str, Dict[str, Any]] = {}

# Skill distillation is kept as a plain asyncio.Task
_RUNNING_TASKS: Dict[str, asyncio.Task] = {}


# ═══════════════════════════════════════════════════════════════════════════════
# JOB FUNCTIONS — module-level so APScheduler can pickle/restore them
# ═══════════════════════════════════════════════════════════════════════════════

async def _job_one_shot(
    *,
    job_id: str,
    label: str,
    duration: int,
    chat_id: str,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
) -> None:
    logger.info(f"One-shot timer fired: '{label}' ({duration}s)")
    from backend.activity_logger import log_activity
    if agent_id and prompt:
        asyncio.create_task(_trigger_agent_task(agent_id, prompt, chat_id))
    else:
        log_activity("idle", "Scheduler", f"✅ Timer complete: '{label}'")
        await _send_telegram_alert(
            chat_id,
            f"🏛️ **ATTENTION, SIR**\n\nTimer complete:\n"
            f"• Event: **{label}**\n• Duration: {duration} sec\n• Status: ✅ Completed",
        )
    await _broadcast_ws({"type": "timer_completed", "timer": {"id": job_id, "label": label, "status": "completed"}})


async def _job_alarm(
    *,
    job_id: str,
    label: str,
    chat_id: str,
    target_time_str: str,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
) -> None:
    logger.info(f"Alarm fired: '{label}'")
    from backend.activity_logger import log_activity
    if agent_id and prompt:
        asyncio.create_task(_trigger_agent_task(agent_id, prompt, chat_id))
    else:
        log_activity("idle", "Scheduler", f"🔔 Alarm triggered: '{label}'")
        await _send_telegram_alert(
            chat_id,
            f"⏰ **ALARM, SIR**\n\n"
            f"• Event: **{label}**\n• Trigger time: {target_time_str}\n• Status: ✅ Completed",
        )
    await _broadcast_ws({"type": "alarm_fired", "alarm": {"id": job_id, "label": label, "status": "completed"}})


async def _job_recurring(
    *,
    job_id: str,
    label: str,
    interval_hours: float,
    chat_id: str,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
) -> None:
    _fire_counts[job_id] = _fire_counts.get(job_id, 0) + 1
    count = _fire_counts[job_id]
    logger.info(f"Recurring reminder fired #{count}: '{label}'")
    from backend.activity_logger import log_activity
    if agent_id and prompt:
        asyncio.create_task(_trigger_agent_task(agent_id, prompt, chat_id))
    else:
        hours_str = (
            f"{int(interval_hours)} h" if interval_hours >= 1
            else f"{int(interval_hours * 60)} min"
        )
        log_activity("idle", "Scheduler", f"🔔 Recurring reminder #{count} triggered: '{label}'")
        await _send_telegram_alert(
            chat_id,
            f"🔔 **REMINDER, SIR** (#{count})\n\n• {label}\n"
            f"• Repeat every: {hours_str}\n\n_Next trigger in {hours_str}._",
        )
    job = scheduler.get_job(job_id)
    next_run = getattr(job, "next_run_time", None) if job else None
    now_tz = datetime.now(scheduler.timezone)
    time_left = max(0, int((next_run - now_tz).total_seconds())) if next_run else 0
    await _broadcast_ws({
        "type": "reminder_fired",
        "reminder": {
            "id": job_id, "label": label, "interval_hours": interval_hours,
            "fire_count": count, "status": "running", "time_left": time_left, "type": "recurring",
        },
    })


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ═══════════════════════════════════════════════════════════════════════════════

def add_timer(
    label: str,
    duration_seconds: int,
    chat_id: str,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
) -> str:
    timer_id = str(uuid.uuid4())
    run_at = datetime.now(scheduler.timezone) + timedelta(seconds=duration_seconds)
    created_at = datetime.now(scheduler.timezone).strftime("%Y-%m-%d %H:%M:%S")
    scheduler.add_job(
        _job_one_shot,
        trigger=DateTrigger(run_date=run_at),
        kwargs={"job_id": timer_id, "label": label, "duration": duration_seconds,
                "chat_id": chat_id, "agent_id": agent_id, "prompt": prompt},
        id=timer_id, name=label, replace_existing=True,
    )
    _timer_meta[timer_id] = {"type": "one-shot", "created_at": created_at, "duration": duration_seconds}
    logger.info(f"One-shot timer scheduled: '{label}' in {duration_seconds}s (id={timer_id})")
    return timer_id


def add_alarm(
    time_str: str,
    label: str,
    chat_id: str,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
) -> str:
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Asia/Jerusalem")
    now = datetime.now(tz)
    time_str = time_str.strip()
    target_dt = None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            target_dt = datetime.strptime(time_str, fmt).replace(tzinfo=tz)
            break
        except ValueError:
            continue
    if target_dt is None:
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                t = datetime.strptime(time_str, fmt).time()
                target_dt = datetime.combine(now.date(), t).replace(tzinfo=tz)
                if target_dt < now:
                    target_dt += timedelta(days=1)
                break
            except ValueError:
                continue
    if target_dt is None:
        raise ValueError(f"Could not parse time format: '{time_str}'. Use HH:MM or YYYY-MM-DD HH:MM.")

    alarm_id = str(uuid.uuid4())
    target_time_str = target_dt.strftime("%Y-%m-%d %H:%M:%S")
    created_at = now.strftime("%Y-%m-%d %H:%M:%S")
    scheduler.add_job(
        _job_alarm,
        trigger=DateTrigger(run_date=target_dt),
        kwargs={"job_id": alarm_id, "label": label, "chat_id": chat_id,
                "target_time_str": target_time_str, "agent_id": agent_id, "prompt": prompt},
        id=alarm_id, name=label, replace_existing=True,
    )
    _timer_meta[alarm_id] = {"type": "alarm", "created_at": created_at, "target_time": target_time_str}
    logger.info(f"Alarm scheduled: '{label}' at {target_time_str} (id={alarm_id})")
    return alarm_id


def add_recurring_reminder(
    label: str,
    interval_hours: float,
    chat_id: str,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
) -> str:
    reminder_id = str(uuid.uuid4())
    created_at = datetime.now(scheduler.timezone).strftime("%Y-%m-%d %H:%M:%S")
    scheduler.add_job(
        _job_recurring,
        trigger=IntervalTrigger(hours=interval_hours),
        kwargs={"job_id": reminder_id, "label": label, "interval_hours": interval_hours,
                "chat_id": chat_id, "agent_id": agent_id, "prompt": prompt},
        id=reminder_id, name=label, replace_existing=True,
    )
    _timer_meta[reminder_id] = {"type": "recurring", "created_at": created_at, "interval_hours": interval_hours}

    from backend.activity_logger import log_activity
    log_activity("idle", "Scheduler", f"🔔 Recurring reminder started every {interval_hours}h: '{label}'")
    logger.info(f"Recurring reminder scheduled: '{label}' every {interval_hours}h (id={reminder_id})")
    return reminder_id


def cancel_timer_or_alarm(item_id: str) -> bool:
    job = scheduler.get_job(item_id)
    if job is None:
        return False
    job.remove()
    _timer_meta.pop(item_id, None)
    _fire_counts.pop(item_id, None)
    logger.info(f"Timer/alarm cancelled: {item_id}")
    return True


def cancel_recurring_reminder(reminder_id: str) -> bool:
    job = scheduler.get_job(reminder_id)
    if job is None:
        return False
    job.remove()
    _timer_meta.pop(reminder_id, None)
    _fire_counts.pop(reminder_id, None)
    logger.info(f"Recurring reminder cancelled: {reminder_id}")
    return True


def _infer_type(job) -> str:
    func = getattr(job, "func", None)
    name = getattr(func, "__name__", "")
    if "recurring" in name:
        return "recurring"
    if "alarm" in name:
        return "alarm"
    return "one-shot"


def get_all_timers() -> List[Dict[str, Any]]:
    jobs = scheduler.get_jobs()
    now_tz = datetime.now(scheduler.timezone)
    result = []
    for job in jobs:
        if job.id == "skill_distillation":
            continue
        kwargs = job.kwargs or {}
        job_id = job.id
        label = kwargs.get("label", job.name or job_id)
        meta = _timer_meta.get(job_id, {})
        job_type = meta.get("type") or _infer_type(job)
        created_at = meta.get("created_at", "")
        next_run = getattr(job, "next_run_time", None)
        time_left = max(0, int((next_run - now_tz).total_seconds())) if next_run else 0

        entry: Dict[str, Any] = {
            "id": job_id,
            "label": label,
            "status": "running",
            "time_left": time_left,
            "type": job_type,
            "created_at": created_at,
            "agent_id": kwargs.get("agent_id"),
            "prompt": kwargs.get("prompt"),
        }
        if job_type == "recurring":
            entry["interval_hours"] = kwargs.get("interval_hours") or meta.get("interval_hours")
            entry["fire_count"] = _fire_counts.get(job_id, 0)
        elif job_type == "alarm":
            entry["target_time"] = kwargs.get("target_time_str") or meta.get("target_time")
        elif job_type == "one-shot":
            entry["duration"] = kwargs.get("duration") or meta.get("duration")

        result.append(entry)

    result.sort(key=lambda x: x.get("time_left", 0))
    return result


def get_all_reminders() -> List[Dict[str, Any]]:
    return [t for t in get_all_timers() if t.get("type") == "recurring"]


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def _trigger_agent_task(agent_id: str, prompt: str, chat_id: str) -> None:
    try:
        from backend.agent import agent_instance, DECISION_LOGS
        from backend.websocket_manager import manager
        await manager.broadcast({"type": "chat_message", "role": "user",
                                 "content": f"[Scheduled Task] {prompt}", "chat_id": agent_id})
        response_text = await agent_instance.respond(prompt, session_id=agent_id)
        cost_usd = agent_instance.last_costs.get(agent_id, 0.0)
        suppress_tts = agent_instance.check_and_clear_suppress_tts(agent_id)
        saved_ids = agent_instance.last_saved_ids.get(agent_id, {})
        user_msg_id = saved_ids.get("user")
        assistant_msg_id = saved_ids.get("assistant")
        await manager.broadcast({"type": "chat_message", "role": "assistant", "content": response_text,
                                 "chat_id": agent_id, "cost_usd": cost_usd,
                                 "suppress_tts": suppress_tts, "id": assistant_msg_id})
        if user_msg_id:
            await manager.broadcast({"type": "user_message_id_update", "chat_id": agent_id,
                                     "content": prompt, "id": user_msg_id})
        await manager.broadcast({"type": "logs_update", "logs": DECISION_LOGS[:20]})
        await _send_telegram_alert(
            chat_id,
            f"🤖 **SCHEDULED TASK RESULT**\n\n• **Agent**: `{agent_id}`\n"
            f"• **Task**: {prompt}\n\n📝 **Result**:\n{response_text}",
        )
    except Exception as exc:
        logger.error(f"Error executing scheduled agent task: {exc}")


async def _send_telegram_alert(chat_id: str, text: str) -> None:
    """Send a Telegram message. Also imported by price_monitor.py."""
    try:
        from backend.bot import telegram_app
        if telegram_app:
            await telegram_app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
    except Exception as exc:
        logger.error(f"Telegram alert error: {exc}")


async def _broadcast_ws(payload: Dict) -> None:
    try:
        from backend.websocket_manager import manager
        await manager.broadcast(payload)
    except Exception as exc:
        logger.error(f"WS broadcast error: {exc}")


# ═══════════════════════════════════════════════════════════════════════════════
# SKILL DISTILLATION — plain asyncio.Task, NOT an APScheduler job
# ═══════════════════════════════════════════════════════════════════════════════

async def _run_skill_distillation_loop(interval_seconds: int = 900) -> None:
    logger.info("Starting background skill distillation loop...")
    while True:
        try:
            from backend.skill_loop import get_skill_distiller
            distiller = get_skill_distiller()
            distilled = distiller.process_undistilled_logs(min_steps=3, limit=5)
            if distilled:
                logger.info(f"Skill distillation loop: created {len(distilled)} new skills.")
                await _broadcast_ws({"type": "skills_distilled", "skills": distilled})
        except asyncio.CancelledError:
            logger.info("Skill distillation loop cancelled.")
            break
        except Exception as err:
            logger.error(f"Skill distillation loop error: {err}")
        await asyncio.sleep(interval_seconds)


def start_skill_distillation_loop(interval_seconds: int = 900) -> Optional[asyncio.Task]:
    key = "skill_distillation_loop"
    if key not in _RUNNING_TASKS or _RUNNING_TASKS[key].done():
        task = asyncio.create_task(_run_skill_distillation_loop(interval_seconds=interval_seconds))
        _RUNNING_TASKS[key] = task
        return task
    return _RUNNING_TASKS[key]


# ═══════════════════════════════════════════════════════════════════════════════
# COMPATIBILITY SHIMS — no-ops now, kept so main.py imports don't break
# ═══════════════════════════════════════════════════════════════════════════════

def restore_state() -> None:
    """No-op: APScheduler auto-restores from SQLite on scheduler.start()."""
    for job in scheduler.get_jobs():
        if job.id not in _timer_meta:
            _timer_meta[job.id] = {
                "type": _infer_type(job),
                "created_at": "",
                "interval_hours": (job.kwargs or {}).get("interval_hours"),
                "duration": (job.kwargs or {}).get("duration"),
                "target_time": (job.kwargs or {}).get("target_time_str"),
            }
    logger.info(f"Scheduler: {len(scheduler.get_jobs())} jobs loaded from DB")


async def _start_restored_tasks() -> None:
    """No-op: APScheduler auto-starts restored jobs."""
    pass
