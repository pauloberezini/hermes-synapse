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
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.database import DB_PATH

logger = logging.getLogger("hermes.scheduler")

# ─── Scheduler singleton ────────────────────────────────────────────────────────
if "PYTEST_CURRENT_TEST" in os.environ:
    _DB_URL = "sqlite:///:memory:"
else:
    _DB_URL = os.environ.get(
        "SCHEDULER_DB_URL",
        f"sqlite:///{DB_PATH}",
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
RUNNING_TASKS: Dict[str, asyncio.Task] = _RUNNING_TASKS

# Backward compatibility exports for unit tests
ACTIVE_TIMERS: List[Any] = []
ACTIVE_REMINDERS: List[Any] = []
ACTIVE_ALARMS: List[Any] = []


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
    created_at: Optional[str] = None,
    task_type: Optional[str] = None,
    **kwargs,
) -> None:
    logger.info(f"One-shot timer fired: '{label}' ({duration}s)")
    from backend.activity_logger import log_activity
    task_session_id = f"task_{job_id}"
    _timer_meta[job_id]["status"] = "completed"
    _register_scheduled_session(job_id, label, "one-shot", agent_id, prompt, status="completed", extra={"duration": duration})

    if agent_id and prompt:
        asyncio.create_task(_trigger_agent_task(agent_id, prompt, chat_id, task_session_id=task_session_id, job_id=job_id, label=label))
    else:
        log_activity("idle", "Scheduler", f"✅ Timer complete: '{label}'")
        await _send_telegram_alert(
            chat_id,
            f"🏛️ **ATTENTION, SIR**\n\nTimer complete:\n"
            f"• Event: **{label}**\n• Duration: {duration} sec\n• Status: ✅ Completed",
        )
    await _broadcast_ws({"type": "timer_completed", "timer": {"id": job_id, "label": label, "status": "completed"}, "session_id": task_session_id})


async def _job_alarm(
    *,
    job_id: str,
    label: str,
    chat_id: str,
    target_time_str: str,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
    created_at: Optional[str] = None,
    task_type: Optional[str] = None,
    **kwargs,
) -> None:
    logger.info(f"Alarm fired: '{label}'")
    from backend.activity_logger import log_activity
    task_session_id = f"task_{job_id}"
    _timer_meta[job_id]["status"] = "completed"
    _register_scheduled_session(job_id, label, "alarm", agent_id, prompt, status="completed", extra={"target_time": target_time_str})

    if agent_id and prompt:
        asyncio.create_task(_trigger_agent_task(agent_id, prompt, chat_id, task_session_id=task_session_id, job_id=job_id, label=label))
    else:
        log_activity("idle", "Scheduler", f"🔔 Alarm triggered: '{label}'")
        await _send_telegram_alert(
            chat_id,
            f"⏰ **ALARM, SIR**\n\n"
            f"• Event: **{label}**\n• Trigger time: {target_time_str}\n• Status: ✅ Completed",
        )
    await _broadcast_ws({"type": "alarm_fired", "alarm": {"id": job_id, "label": label, "status": "completed"}, "session_id": task_session_id})


async def _job_recurring(
    *,
    job_id: str,
    label: str,
    interval_hours: float,
    chat_id: str,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
    created_at: Optional[str] = None,
    task_type: Optional[str] = None,
    **kwargs,
) -> None:
    _fire_counts[job_id] = _fire_counts.get(job_id, 0) + 1
    count = _fire_counts[job_id]
    logger.info(f"Recurring reminder fired #{count}: '{label}'")
    from backend.activity_logger import log_activity
    task_session_id = f"task_{job_id}"
    _register_scheduled_session(job_id, label, "recurring", agent_id, prompt, status="running", extra={"interval_hours": interval_hours, "fire_count": count})

    if agent_id and prompt:
        asyncio.create_task(_trigger_agent_task(agent_id, prompt, chat_id, task_session_id=task_session_id, job_id=job_id, label=label))
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


def _register_scheduled_session(
    job_id: str,
    label: str,
    task_type: str,
    agent_id: Optional[str],
    prompt: Optional[str],
    status: str = "running",
    extra: Optional[Dict] = None
):
    import json
    from backend.database import save_scheduled_session_metadata
    session_id = f"task_{job_id}"
    title = label if (label.startswith("⏰") or label.startswith("🔔")) else f"⏰ {label}"
    info_dict = {
        "job_id": job_id,
        "label": label,
        "task_type": task_type,
        "prompt": prompt,
        "status": status,
        "agent_id": agent_id or "jarvis",
    }
    if extra:
        info_dict.update(extra)
    save_scheduled_session_metadata(
        session_id=session_id,
        title=title,
        agent_id=agent_id or "jarvis",
        job_id=job_id,
        schedule_type=task_type,
        schedule_info=json.dumps(info_dict)
    )


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
                "chat_id": chat_id, "agent_id": agent_id, "prompt": prompt,
                "created_at": created_at, "task_type": "one-shot"},
        id=timer_id, name=label, replace_existing=True,
    )
    _timer_meta[timer_id] = {"type": "one-shot", "created_at": created_at, "duration": duration_seconds, "status": "running"}
    _register_scheduled_session(timer_id, label, "one-shot", agent_id, prompt, status="running", extra={"duration": duration_seconds})
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
                "target_time_str": target_time_str, "agent_id": agent_id, "prompt": prompt,
                "created_at": created_at, "task_type": "alarm"},
        id=alarm_id, name=label, replace_existing=True,
    )
    _timer_meta[alarm_id] = {"type": "alarm", "created_at": created_at, "target_time": target_time_str, "status": "running"}
    _register_scheduled_session(alarm_id, label, "alarm", agent_id, prompt, status="running", extra={"target_time": target_time_str})
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
                "chat_id": chat_id, "agent_id": agent_id, "prompt": prompt,
                "created_at": created_at, "task_type": "recurring"},
        id=reminder_id, name=label, replace_existing=True,
    )
    _timer_meta[reminder_id] = {"type": "recurring", "created_at": created_at, "interval_hours": interval_hours, "status": "running"}
    _register_scheduled_session(reminder_id, label, "recurring", agent_id, prompt, status="running", extra={"interval_hours": interval_hours})

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
    try:
        from backend.database import delete_session_title
        delete_session_title(f"task_{item_id}")
        delete_session_title(item_id)
    except Exception as e:
        logger.error(f"Error cleaning session metadata on cancel: {e}")
    logger.info(f"Timer/alarm cancelled: {item_id}")
    return True


def cancel_recurring_reminder(reminder_id: str) -> bool:
    job = scheduler.get_job(reminder_id)
    if job is None:
        return False
    job.remove()
    _timer_meta.pop(reminder_id, None)
    _fire_counts.pop(reminder_id, None)
    try:
        from backend.database import delete_session_title
        delete_session_title(f"task_{reminder_id}")
        delete_session_title(reminder_id)
    except Exception as e:
        logger.error(f"Error cleaning session metadata on cancel: {e}")
    logger.info(f"Recurring reminder cancelled: {reminder_id}")
    return True


def update_timer(
    item_id: str,
    label: str,
    task_type: str,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
    duration_seconds: Optional[int] = None,
    time_str: Optional[str] = None,
    interval_hours: Optional[float] = None,
) -> bool:
    job = scheduler.get_job(item_id)
    if job is None:
        return False

    chat_id = job.kwargs.get("chat_id", "dashboard")
    created_at = _timer_meta.get(item_id, {}).get("created_at") or job.kwargs.get("created_at") or datetime.now(scheduler.timezone).strftime("%Y-%m-%d %H:%M:%S")

    job.remove()
    _timer_meta.pop(item_id, None)

    if task_type == "one-shot":
        if duration_seconds is None:
            raise ValueError("duration_seconds is required for one-shot timer")
        run_at = datetime.now(scheduler.timezone) + timedelta(seconds=duration_seconds)
        scheduler.add_job(
            _job_one_shot,
            trigger=DateTrigger(run_date=run_at),
            kwargs={"job_id": item_id, "label": label, "duration": duration_seconds,
                    "chat_id": chat_id, "agent_id": agent_id, "prompt": prompt,
                    "created_at": created_at, "task_type": "one-shot"},
            id=item_id, name=label, replace_existing=True,
        )
        _timer_meta[item_id] = {"type": "one-shot", "created_at": created_at, "duration": duration_seconds, "status": "running"}
    elif task_type == "alarm":
        if not time_str:
            raise ValueError("time_str is required for alarm timer")
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Asia/Jerusalem")
        now = datetime.now(tz)
        time_str_clean = time_str.strip()
        target_dt = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                target_dt = datetime.strptime(time_str_clean, fmt).replace(tzinfo=tz)
                break
            except ValueError:
                continue
        if target_dt is None:
            for fmt in ("%H:%M:%S", "%H:%M"):
                try:
                    t = datetime.strptime(time_str_clean, fmt).time()
                    target_dt = datetime.combine(now.date(), t).replace(tzinfo=tz)
                    if target_dt < now:
                        target_dt += timedelta(days=1)
                    break
                except ValueError:
                    continue
        if target_dt is None:
            raise ValueError(f"Could not parse time format: '{time_str}'. Use HH:MM or YYYY-MM-DD HH:MM.")

        target_time_str = target_dt.strftime("%Y-%m-%d %H:%M:%S")
        scheduler.add_job(
            _job_alarm,
            trigger=DateTrigger(run_date=target_dt),
            kwargs={"job_id": item_id, "label": label, "chat_id": chat_id,
                    "target_time_str": target_time_str, "agent_id": agent_id, "prompt": prompt,
                    "created_at": created_at, "task_type": "alarm"},
            id=item_id, name=label, replace_existing=True,
        )
        _timer_meta[item_id] = {"type": "alarm", "created_at": created_at, "target_time": target_time_str, "status": "running"}
    elif task_type == "recurring":
        if interval_hours is None:
            raise ValueError("interval_hours is required for recurring timer")
        scheduler.add_job(
            _job_recurring,
            trigger=IntervalTrigger(hours=interval_hours),
            kwargs={"job_id": item_id, "label": label, "interval_hours": interval_hours,
                    "chat_id": chat_id, "agent_id": agent_id, "prompt": prompt,
                    "created_at": created_at, "task_type": "recurring"},
            id=item_id, name=label, replace_existing=True,
        )
        _timer_meta[item_id] = {"type": "recurring", "created_at": created_at, "interval_hours": interval_hours, "status": "running"}
    else:
        raise ValueError(f"Invalid task type: '{task_type}'")

    logger.info(f"Updated task {item_id}: label='{label}', type={task_type}")
    return True


def pause_timer(item_id: str) -> bool:
    job = scheduler.get_job(item_id)
    if job is None:
        return False
    job.pause()
    if item_id not in _timer_meta:
        _timer_meta[item_id] = {"type": _infer_type(job), "created_at": ""}
    _timer_meta[item_id]["status"] = "paused"
    logger.info(f"Timer {item_id} paused")
    return True


def resume_timer(item_id: str) -> bool:
    job = scheduler.get_job(item_id)
    if job is None:
        return False
    job.resume()
    if item_id not in _timer_meta:
        _timer_meta[item_id] = {"type": _infer_type(job), "created_at": ""}
    _timer_meta[item_id]["status"] = "running"
    logger.info(f"Timer {item_id} resumed")
    return True


def restart_timer(item_id: str) -> bool:
    job = scheduler.get_job(item_id)
    if job is None:
        return False
    
    meta = _timer_meta.get(item_id, {})
    task_type = meta.get("type") or _infer_type(job)
    kwargs = job.kwargs or {}
    label = kwargs.get("label", job.name or item_id)
    agent_id = kwargs.get("agent_id")
    prompt = kwargs.get("prompt")
    duration_seconds = kwargs.get("duration") or meta.get("duration") or 60
    time_str = kwargs.get("target_time_str") or meta.get("target_time")
    interval_hours = kwargs.get("interval_hours") or meta.get("interval_hours") or 1.0

    return update_timer(
        item_id=item_id,
        label=label,
        task_type=task_type,
        agent_id=agent_id,
        prompt=prompt,
        duration_seconds=duration_seconds,
        time_str=time_str,
        interval_hours=interval_hours,
    )


def trigger_timer_now(item_id: str) -> bool:
    job = scheduler.get_job(item_id)
    if job is None:
        return False
    kwargs = job.kwargs or {}
    agent_id = kwargs.get("agent_id") or "jarvis"
    prompt = kwargs.get("prompt")
    chat_id = kwargs.get("chat_id", "dashboard")
    if not prompt:
        raise ValueError("Task has no prompt to execute.")
    asyncio.create_task(_trigger_agent_task(agent_id, prompt, chat_id))
    logger.info(f"Manually triggered task {item_id} (agent={agent_id})")
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
        job_type = meta.get("type") or kwargs.get("task_type") or _infer_type(job)
        created_at = meta.get("created_at") or kwargs.get("created_at", "")
        next_run = getattr(job, "next_run_time", None)
        time_left = max(0, int((next_run - now_tz).total_seconds())) if next_run else 0

        status = meta.get("status", "paused" if next_run is None else "running")

        entry: Dict[str, Any] = {
            "id": job_id,
            "label": label,
            "status": status,
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

async def _trigger_agent_task(
    agent_id: str,
    prompt: str,
    chat_id: str,
    task_session_id: Optional[str] = None,
    job_id: Optional[str] = None,
    label: Optional[str] = None,
) -> None:
    session_id = task_session_id or (f"task_{job_id}" if job_id else agent_id)
    try:
        from backend.agent import agent_instance, DECISION_LOGS
        from backend.websocket_manager import manager
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        user_prompt_display = f"[Scheduled Run - {now_str}] {prompt}"

        await manager.broadcast({
            "type": "chat_message",
            "role": "user",
            "content": user_prompt_display,
            "chat_id": session_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })

        response_text = await agent_instance.respond(prompt, session_id=session_id)
        cost_usd = agent_instance.last_costs.get(session_id, 0.0)
        suppress_tts = agent_instance.check_and_clear_suppress_tts(session_id)
        saved_ids = agent_instance.last_saved_ids.get(session_id, {})
        user_msg_id = saved_ids.get("user")
        assistant_msg_id = saved_ids.get("assistant")

        await manager.broadcast({
            "type": "chat_message",
            "role": "assistant",
            "content": response_text,
            "chat_id": session_id,
            "cost_usd": cost_usd,
            "suppress_tts": suppress_tts,
            "id": assistant_msg_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        if user_msg_id:
            await manager.broadcast({
                "type": "user_message_id_update",
                "chat_id": session_id,
                "content": user_prompt_display,
                "id": user_msg_id
            })
        await manager.broadcast({"type": "logs_update", "logs": DECISION_LOGS[:20]})
        await manager.broadcast({"type": "scheduled_task_executed", "session_id": session_id, "job_id": job_id})
        await _send_telegram_alert(
            chat_id,
            f"🤖 **SCHEDULED TASK RESULT**\n\n• **Agent**: `{agent_id}`\n"
            f"• **Task**: {prompt}\n\n📝 **Result**:\n{response_text}",
        )
    except Exception as exc:
        logger.error(f"Error executing scheduled agent task: {exc}")


async def _send_telegram_alert(chat_id: str, text: str) -> None:
    """Send a Telegram message. Also imported by price_monitor.py."""
    if not chat_id or chat_id == "dashboard" or not (chat_id.lstrip('-').isdigit() or chat_id.startswith('@')):
        return
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
    """Populate _timer_meta for jobs restored from SQLite DB by APScheduler."""
    for job in scheduler.get_jobs():
        if job.id == "skill_distillation":
            continue
        kwargs = job.kwargs or {}
        task_type = kwargs.get("task_type") or _infer_type(job)
        status = "paused" if getattr(job, "next_run_time", None) is None else "running"
        _timer_meta[job.id] = {
            "type": task_type,
            "created_at": kwargs.get("created_at", ""),
            "interval_hours": kwargs.get("interval_hours"),
            "duration": kwargs.get("duration"),
            "target_time": kwargs.get("target_time_str"),
            "status": status,
        }
        label = kwargs.get("label", job.name or job.id)
        agent_id = kwargs.get("agent_id")
        prompt = kwargs.get("prompt")
        _register_scheduled_session(job.id, label, task_type, agent_id, prompt, status=status)
    logger.info(f"Scheduler: {len(scheduler.get_jobs())} jobs loaded from DB")


async def _start_restored_tasks() -> None:
    """No-op: APScheduler auto-starts restored jobs."""
    pass
