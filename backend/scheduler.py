"""
backend/scheduler.py — APScheduler 3.x + PostgreSQLJobStore

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

try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
    from apscheduler.triggers.cron import CronTrigger
    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.interval import IntervalTrigger
except ImportError:
    AsyncIOScheduler = None  # type: ignore
    SQLAlchemyJobStore = None  # type: ignore
    CronTrigger = None  # type: ignore
    DateTrigger = None  # type: ignore
    IntervalTrigger = None  # type: ignore


logger = logging.getLogger("hermes.scheduler")

from backend.database import DB_PATH

# ─── Scheduler singleton ────────────────────────────────────────────────────────
if "PYTEST_CURRENT_TEST" in os.environ or not os.environ.get("DATABASE_URL"):
    _DB_URL = "sqlite:///:memory:"
else:
    _DB_URL = os.environ.get(
        "SCHEDULER_DB_URL",
        os.environ.get("DATABASE_URL")
    )

if _DB_URL.startswith("postgres://"):
    _DB_URL = _DB_URL.replace("postgres://", "postgresql://", 1)

if SQLAlchemyJobStore is not None and AsyncIOScheduler is not None:
    _jobstore = SQLAlchemyJobStore(url=_DB_URL, tablename="apscheduler_jobs")
    scheduler = AsyncIOScheduler(
        jobstores={"default": _jobstore},
        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 14400},
        timezone="Asia/Jerusalem",
    )
else:
    _jobstore = None
    scheduler = None

# Fire-count is cosmetic and session-local (acceptable to reset on restart)
_fire_counts: Dict[str, int] = {}

# Supplementary in-memory metadata dict rebuilt on startup from job kwargs
_timer_meta: Dict[str, Dict[str, Any]] = {}

# Skill distillation is kept as a plain asyncio.Task
_RUNNING_TASKS: Dict[str, asyncio.Task] = {}
RUNNING_TASKS: Dict[str, asyncio.Task] = _RUNNING_TASKS


def _is_redundant_desk_orchestrator_job(
    label: Optional[str] = None,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
    task_type: Optional[str] = None,
    job_id: Optional[str] = None,
) -> bool:
    from backend.plugins import hook
    return bool(hook(
        "is_redundant_desk_orchestrator_job",
        label=label,
        agent_id=agent_id,
        prompt=prompt,
        task_type=task_type,
        job_id=job_id,
        default=False,
    ))


def _drop_scheduled_job(job_id: str, session_id: Optional[str] = None) -> None:
    job = scheduler.get_job(job_id) if scheduler is not None else None
    if job:
        job.remove()
    _timer_meta.pop(job_id, None)
    _fire_counts.pop(job_id, None)
    try:
        from backend.database import delete_session_title
        for sid in (f"task_{job_id}", job_id, session_id):
            if sid:
                delete_session_title(sid)
    except Exception as e:
        logger.error(f"Error cleaning session metadata while dropping job {job_id}: {e}")

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
    try:
        logger.info(f"One-shot timer fired: '{label}' ({duration}s)")
        from backend.activity_logger import log_activity
        from backend.websocket_manager import manager
        from backend.database import save_message
        task_session_id = f"task_{job_id}"
        if job_id in _timer_meta:
            _timer_meta[job_id]["status"] = "completed"
        _register_scheduled_session(job_id, label, "one-shot", agent_id, prompt, status="completed", extra={"duration": duration})

        completion_msg = f"⏰ Timer complete: '{label}' ({duration}s)"
        is_agent = (agent_id and agent_id != "jarvis") or prompt
        if is_agent:
            task_prompt = prompt or f"Execute scheduled task: {label}"
            asyncio.create_task(_trigger_agent_task(agent_id or "jarvis", task_prompt, chat_id, task_session_id=task_session_id, job_id=job_id, label=label))
        else:
            log_activity("idle", "Scheduler", f"✅ Timer complete: '{label}'")
            save_message(task_session_id, "assistant", completion_msg)
            await _send_telegram_alert(
                chat_id,
                f"🏛️ **ATTENTION**\n\nTimer complete:\n"
                f"• Event: **{label}**\n• Duration: {duration} sec\n• Status: ✅ Completed",
            )
            await manager.broadcast({
                "type": "chat_message",
                "role": "assistant",
                "content": completion_msg,
                "chat_id": task_session_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        await _broadcast_ws({"type": "timer_completed", "timer": {"id": job_id, "label": label, "status": "completed"}, "session_id": task_session_id})
    except asyncio.CancelledError:
        logger.info(f"One-shot timer '{label}' ({job_id}) cancelled.")
    except Exception as e:
        logger.error(f"Error in one-shot timer '{label}' ({job_id}): {e}")


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
    try:
        logger.info(f"Alarm fired: '{label}'")
        from backend.activity_logger import log_activity
        from backend.websocket_manager import manager
        from backend.database import save_message
        task_session_id = f"task_{job_id}"
        if job_id in _timer_meta:
            _timer_meta[job_id]["status"] = "completed"
        _register_scheduled_session(job_id, label, "alarm", agent_id, prompt, status="completed", extra={"target_time": target_time_str})

        completion_msg = f"⏰ Alarm fired: '{label}' ({target_time_str})"
        is_agent = (agent_id and agent_id != "jarvis") or prompt
        if is_agent:
            task_prompt = prompt or f"Execute scheduled task: {label}"
            asyncio.create_task(_trigger_agent_task(agent_id or "jarvis", task_prompt, chat_id, task_session_id=task_session_id, job_id=job_id, label=label))
        else:
            log_activity("idle", "Scheduler", f"🔔 Alarm triggered: '{label}'")
            save_message(task_session_id, "assistant", completion_msg)
            await _send_telegram_alert(
                chat_id,
                f"⏰ **ALARM**\n\n"
                f"• Event: **{label}**\n• Trigger time: {target_time_str}\n• Status: ✅ Completed",
            )
            await manager.broadcast({
                "type": "chat_message",
                "role": "assistant",
                "content": completion_msg,
                "chat_id": task_session_id,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        await _broadcast_ws({"type": "alarm_fired", "alarm": {"id": job_id, "label": label, "status": "completed"}, "session_id": task_session_id})
    except asyncio.CancelledError:
        logger.info(f"Alarm '{label}' ({job_id}) cancelled.")
    except Exception as e:
        logger.error(f"Error in alarm '{label}' ({job_id}): {e}")


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
    try:
        if _is_redundant_desk_orchestrator_job(
            label=label, agent_id=agent_id, prompt=prompt, task_type="recurring", job_id=job_id
        ):
            logger.info(
                "Skipping redundant desk orchestrator reminder '%s' (%s); session scheduler already covers the desk.",
                label, job_id,
            )
            _drop_scheduled_job(job_id)
            return

        _fire_counts[job_id] = _fire_counts.get(job_id, 0) + 1
        count = _fire_counts[job_id]
        logger.info(f"Recurring reminder fired #{count}: '{label}'")
        from backend.activity_logger import log_activity
        task_session_id = f"task_{job_id}"
        _register_scheduled_session(job_id, label, "recurring", agent_id, prompt, status="running", extra={"interval_hours": interval_hours, "fire_count": count})

        is_agent = (agent_id and agent_id != "jarvis") or prompt
        if is_agent:
            task_prompt = prompt or f"Execute scheduled task: {label}"
            asyncio.create_task(_trigger_agent_task(agent_id or "jarvis", task_prompt, chat_id, task_session_id=task_session_id, job_id=job_id, label=label))
        else:
            hours_str = (
                f"{int(interval_hours)} h" if interval_hours >= 1
                else f"{int(interval_hours * 60)} min"
            )
            log_activity("idle", "Scheduler", f"🔔 Recurring reminder #{count} triggered: '{label}'")
            await _send_telegram_alert(
                chat_id,
                f"🔔 **REMINDER** (#{count})\n\n• {label}\n"
                f"• Repeat every: {hours_str}\n\n_Next trigger in {hours_str}._",
            )
        job = scheduler.get_job(job_id)
        next_run = getattr(job, "next_run_time", None) if job else None
        now_tz = datetime.now(scheduler.timezone)
        if not next_run or next_run <= now_tz:
            if job and hasattr(job, "trigger") and hasattr(job.trigger, "get_next_fire_time"):
                next_run = job.trigger.get_next_fire_time(now_tz, now_tz)
        time_left = max(0, int((next_run - now_tz).total_seconds())) if next_run else int(interval_hours * 3600)
        await _broadcast_ws({
            "type": "reminder_fired",
            "reminder": {
                "id": job_id, "label": label, "interval_hours": interval_hours,
                "fire_count": count, "status": "running", "time_left": time_left, "type": "recurring",
            },
            "session_id": task_session_id,
        })
    except asyncio.CancelledError:
        logger.info(f"Recurring reminder '{label}' ({job_id}) cancelled.")
    except Exception as e:
        logger.error(f"Error in recurring reminder '{label}' ({job_id}): {e}")


async def _job_cron(
    *,
    job_id: str,
    label: str,
    cron_expr: str,
    chat_id: str,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
    created_at: Optional[str] = None,
    task_type: Optional[str] = None,
    **kwargs,
) -> None:
    try:
        if _is_redundant_desk_orchestrator_job(
            label=label, agent_id=agent_id, prompt=prompt, task_type="cron", job_id=job_id
        ):
            logger.info(
                "Skipping redundant desk orchestrator cron '%s' (%s); session scheduler already covers the desk.",
                label, job_id,
            )
            _drop_scheduled_job(job_id)
            return

        # Ensure this cron trigger runs only once per minute across multiple workers
        try:
            from backend.database import _get_backend
            db = _get_backend()
            current_minute = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
            lock_key = f"cron_lock_{job_id}"
            
            # We need rowcount, so we connect manually
            with db.connect() as conn:
                cur = conn.cursor()
                try:
                    cur.execute(db.translate_placeholder("INSERT OR IGNORE INTO app_settings (key, value) VALUES (?, '')"), (lock_key,))
                    conn.commit()
                except Exception:
                    conn.rollback()  # Clear aborted transaction state
                cur.execute(db.translate_placeholder("UPDATE app_settings SET value = ? WHERE key = ? AND value != ?"), (current_minute, lock_key, current_minute))
                conn.commit()
                if cur.rowcount == 0:
                    logger.info(f"Cron task '{label}' already triggered by another worker this minute. Skipping.")
                    return
        except Exception as e:
            logger.error(f"Failed to acquire cron lock for '{label}': {e}")

        _fire_counts[job_id] = _fire_counts.get(job_id, 0) + 1
        count = _fire_counts[job_id]
        logger.info(f"Cron task fired #{count}: '{label}' ({cron_expr})")
        from backend.activity_logger import log_activity
        task_session_id = f"task_{job_id}"
        _register_scheduled_session(job_id, label, "cron", agent_id, prompt, status="running", extra={"cron_expr": cron_expr, "fire_count": count})

        is_agent = (agent_id and agent_id != "jarvis") or prompt
        if is_agent:
            task_prompt = prompt or f"Execute scheduled task: {label}"
            asyncio.create_task(_trigger_agent_task(agent_id or "jarvis", task_prompt, chat_id, task_session_id=task_session_id, job_id=job_id, label=label))
        else:
            log_activity("idle", "Scheduler", f"⚙️ Cron task #{count} triggered: '{label}' ({cron_expr})")
            await _send_telegram_alert(
                chat_id,
                f"⚙️ **CRON TASK** (#{count})\n\n• {label}\n"
                f"• Schedule: `{cron_expr}`",
            )
        job = scheduler.get_job(job_id)
        next_run = getattr(job, "next_run_time", None) if job else None
        now_tz = datetime.now(scheduler.timezone)
        if not next_run or next_run <= now_tz:
            if job and hasattr(job, "trigger") and hasattr(job.trigger, "get_next_fire_time"):
                next_run = job.trigger.get_next_fire_time(now_tz, now_tz)
        time_left = max(0, int((next_run - now_tz).total_seconds())) if next_run else 0
        await _broadcast_ws({
            "type": "reminder_fired",
            "reminder": {
                "id": job_id, "label": label, "cron_expr": cron_expr,
                "fire_count": count, "status": "running", "time_left": time_left, "type": "cron",
            },
            "session_id": task_session_id,
        })
    except asyncio.CancelledError:
        logger.info(f"Cron task '{label}' ({job_id}) cancelled.")
    except Exception as e:
        logger.error(f"Error in cron task '{label}' ({job_id}): {e}")


def _existing_named_job(label: str, task_type: str):
    """Return a live APScheduler job with the same label and type, if any."""
    if scheduler is None or not label:
        return None
    try:
        jobs = scheduler.get_jobs()
    except Exception:
        return None
    for job in jobs:
        kwargs = getattr(job, "kwargs", None) or {}
        meta = _timer_meta.get(job.id, {})
        job_label = kwargs.get("label") or job.name
        job_type = meta.get("type") or kwargs.get("task_type") or _infer_type(job)
        if job_label == label and job_type == task_type:
            return job
    return None


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
    _timer_meta[timer_id] = {
        "type": "one-shot",
        "created_at": created_at,
        "duration": duration_seconds,
        "status": "running",
        "agent_id": agent_id,
        "prompt": prompt,
        "label": label,
    }
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
    _timer_meta[alarm_id] = {
        "type": "alarm",
        "created_at": created_at,
        "target_time": target_time_str,
        "status": "running",
        "agent_id": agent_id,
        "prompt": prompt,
        "label": label,
    }
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
    if _is_redundant_desk_orchestrator_job(
        label=label, agent_id=agent_id, prompt=prompt, task_type="recurring"
    ):
        raise ValueError(
            "This reminder duplicates a schedule owned by an installed plugin."
        )
    existing = _existing_named_job(label, "recurring")
    if existing:
        logger.info("Reusing existing recurring reminder %s for label '%s'", existing.id, label)
        return existing.id
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
    _timer_meta[reminder_id] = {
        "type": "recurring",
        "created_at": created_at,
        "interval_hours": interval_hours,
        "status": "running",
        "agent_id": agent_id,
        "prompt": prompt,
        "label": label,
    }

    _register_scheduled_session(reminder_id, label, "recurring", agent_id, prompt, status="running", extra={"interval_hours": interval_hours})

    from backend.activity_logger import log_activity
    log_activity("idle", "Scheduler", f"🔔 Recurring reminder started every {interval_hours}h: '{label}'")
    logger.info(f"Recurring reminder scheduled: '{label}' every {interval_hours}h (id={reminder_id})")
    return reminder_id


def add_cron_reminder(
    label: str,
    cron_expr: str,
    chat_id: str,
    agent_id: Optional[str] = None,
    prompt: Optional[str] = None,
) -> str:
    if _is_redundant_desk_orchestrator_job(
        label=label, agent_id=agent_id, prompt=prompt, task_type="cron"
    ):
        raise ValueError(
            "This reminder duplicates a schedule owned by an installed plugin."
        )
    existing = _existing_named_job(label, "cron")
    if existing:
        logger.info("Reusing existing cron reminder %s for label '%s'", existing.id, label)
        return existing.id
    reminder_id = str(uuid.uuid4())
    created_at = datetime.now(scheduler.timezone).strftime("%Y-%m-%d %H:%M:%S")
    cron_expr = cron_expr.strip()
    try:
        trigger = CronTrigger.from_crontab(cron_expr, timezone=scheduler.timezone)
    except Exception as e:
        raise ValueError(f"Invalid cron expression '{cron_expr}': {e}")

    scheduler.add_job(
        _job_cron,
        trigger=trigger,
        kwargs={"job_id": reminder_id, "label": label, "cron_expr": cron_expr,
                "chat_id": chat_id, "agent_id": agent_id, "prompt": prompt,
                "created_at": created_at, "task_type": "cron"},
        id=reminder_id, name=label, replace_existing=True,
    )
    _timer_meta[reminder_id] = {
        "type": "cron",
        "created_at": created_at,
        "cron_expr": cron_expr,
        "status": "running",
        "agent_id": agent_id,
        "prompt": prompt,
        "label": label,
    }

    _register_scheduled_session(reminder_id, label, "cron", agent_id, prompt, status="running", extra={"cron_expr": cron_expr})

    from backend.activity_logger import log_activity
    log_activity("idle", "Scheduler", f"⚙️ Cron task scheduled '{label}' ({cron_expr})")
    logger.info(f"Cron task scheduled: '{label}' ({cron_expr}) (id={reminder_id})")
    return reminder_id


add_cron_task = add_cron_reminder


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
    cron_expr: Optional[str] = None,
) -> bool:
    job = scheduler.get_job(item_id)
    if job is None and item_id not in _timer_meta:
        return False

    chat_id = (job.kwargs.get("chat_id", "dashboard") if job else "dashboard")
    created_at = _timer_meta.get(item_id, {}).get("created_at") or (job.kwargs.get("created_at") if job else None) or datetime.now(scheduler.timezone).strftime("%Y-%m-%d %H:%M:%S")

    # Step 1: Prepare and validate new trigger BEFORE modifying or removing the existing job
    trigger = None
    target_func = _job_cron if task_type == "cron" else (_job_recurring if task_type == "recurring" else (_job_alarm if task_type == "alarm" else _job_one_shot))
    target_kwargs = {
        "job_id": item_id,
        "label": label,
        "chat_id": chat_id,
        "agent_id": agent_id,
        "prompt": prompt,
        "created_at": created_at,
        "task_type": task_type,
    }
    meta_update = {"type": task_type, "created_at": created_at, "status": "running", "agent_id": agent_id, "prompt": prompt, "label": label}

    if task_type == "one-shot":
        if duration_seconds is None:
            raise ValueError("duration_seconds is required for one-shot timer")
        run_at = datetime.now(scheduler.timezone) + timedelta(seconds=duration_seconds)
        trigger = DateTrigger(run_date=run_at)
        target_kwargs["duration"] = duration_seconds
        meta_update["duration"] = duration_seconds

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
        trigger = DateTrigger(run_date=target_dt)
        target_kwargs["target_time_str"] = target_time_str
        meta_update["target_time"] = target_time_str

    elif task_type == "recurring":
        if interval_hours is None:
            raise ValueError("interval_hours is required for recurring timer")
        trigger = IntervalTrigger(hours=interval_hours)
        target_kwargs["interval_hours"] = interval_hours
        meta_update["interval_hours"] = interval_hours

    elif task_type == "cron":
        if not cron_expr:
            raise ValueError("cron_expr is required for cron task")
        cron_expr_clean = cron_expr.strip()
        
        # Support optional trailing timezone (e.g. "0 9 * * mon-fri Europe/London")
        parts = cron_expr_clean.split()
        tz_override = scheduler.timezone
        raw_cron = cron_expr_clean
        if len(parts) == 6:
            raw_cron = " ".join(parts[:5])
            try:
                import pytz
                tz_override = pytz.timezone(parts[5])
            except Exception:
                tz_override = scheduler.timezone

        try:
            trigger = CronTrigger.from_crontab(raw_cron, timezone=tz_override)
        except Exception as e:
            raise ValueError(f"Invalid cron expression '{cron_expr_clean}': {e}")

        from backend.plugins import hook
        private_cron = hook("resolve_cron_job", item_id, agent_id, label)
        if private_cron:
            target_func, extra_kwargs = private_cron
            target_kwargs.update(extra_kwargs)

        target_kwargs["cron_expr"] = cron_expr_clean
        meta_update["cron_expr"] = cron_expr_clean
    else:
        raise ValueError(f"Invalid task type: '{task_type}'")

    # Step 2: Now safely replace the job in APScheduler
    if job is not None:
        try:
            job.remove()
        except Exception:
            pass

    scheduler.add_job(
        target_func,
        trigger=trigger,
        kwargs=target_kwargs,
        id=item_id,
        name=label,
        replace_existing=True,
    )
    _timer_meta[item_id] = meta_update

    extra = {}
    if duration_seconds is not None:
        extra["duration"] = duration_seconds
    if time_str is not None:
        extra["target_time"] = time_str
    if interval_hours is not None:
        extra["interval_hours"] = interval_hours
    if cron_expr is not None:
        extra["cron_expr"] = cron_expr

    _register_scheduled_session(
        job_id=item_id,
        label=label,
        task_type=task_type,
        agent_id=agent_id or "system",
        prompt=prompt,
        status=_timer_meta.get(item_id, {}).get("status", "running"),
        extra=extra,
    )

    logger.info(f"Updated task {item_id}: label='{label}', type={task_type}")
    return True


def pause_timer(item_id: str) -> bool:
    clean_id = item_id.replace("task_", "") if item_id.startswith("task_") else item_id
    job = scheduler.get_job(clean_id) or scheduler.get_job(item_id)
    if job is None and clean_id not in _timer_meta:
        from backend.database import _execute
        session_id = f"task_{clean_id}"
        rows = _execute("SELECT schedule_info FROM session_metadata WHERE session_id = ? OR job_id = ?", (session_id, clean_id))
        if not rows or not rows[0][0]:
            return False

    paused_time_left = None
    if job is not None:
        next_run = getattr(job, "next_run_time", None)
        if next_run:
            from datetime import datetime
            now_tz = datetime.now(scheduler.timezone)
            paused_time_left = max(0, int((next_run - now_tz).total_seconds()))
        job.pause()
        
    if clean_id not in _timer_meta:
        _timer_meta[clean_id] = {"type": _infer_type(job) if job else "scheduled", "created_at": ""}
    _timer_meta[clean_id]["status"] = "paused"
    if paused_time_left is not None:
        _timer_meta[clean_id]["paused_time_left"] = paused_time_left
        
    try:
        from backend.database import _execute
        import json
        session_id = f"task_{clean_id}"
        rows = _execute("SELECT schedule_info FROM session_metadata WHERE session_id = ? OR job_id = ?", (session_id, clean_id))
        if rows and rows[0][0]:
            info_val = rows[0][0]
            info = json.loads(info_val) if isinstance(info_val, str) else info_val
            info["status"] = "paused"
            if paused_time_left is not None:
                info["paused_time_left"] = paused_time_left
            _execute("UPDATE session_metadata SET schedule_info = ? WHERE session_id = ? OR job_id = ?", (json.dumps(info), session_id, clean_id))
    except Exception as err:
        logger.error(f"Failed to update session_metadata for paused timer {item_id}: {err}")
    logger.info(f"Timer {item_id} paused")
    return True


def resume_timer(item_id: str) -> bool:
    clean_id = item_id.replace("task_", "") if item_id.startswith("task_") else item_id
    job = scheduler.get_job(clean_id) or scheduler.get_job(item_id)
    if job is None and clean_id not in _timer_meta:
        from backend.database import _execute
        session_id = f"task_{clean_id}"
        rows = _execute("SELECT schedule_info FROM session_metadata WHERE session_id = ? OR job_id = ?", (session_id, clean_id))
        if not rows or not rows[0][0]:
            return False

    paused_time_left = _timer_meta.get(clean_id, {}).get("paused_time_left")
    
    if job is not None:
        job.resume()
        if paused_time_left is not None:
            from datetime import datetime, timedelta
            now_tz = datetime.now(scheduler.timezone)
            new_next_run = now_tz + timedelta(seconds=paused_time_left)
            job.modify(next_run_time=new_next_run)
            
    if clean_id not in _timer_meta:
        _timer_meta[clean_id] = {"type": _infer_type(job) if job else "scheduled", "created_at": ""}
    _timer_meta[clean_id]["status"] = "running"
    if "paused_time_left" in _timer_meta[clean_id]:
        del _timer_meta[clean_id]["paused_time_left"]
        
    try:
        from backend.database import _execute
        import json
        session_id = f"task_{clean_id}"
        rows = _execute("SELECT schedule_info FROM session_metadata WHERE session_id = ? OR job_id = ?", (session_id, clean_id))
        if rows and rows[0][0]:
            info_val = rows[0][0]
            info = json.loads(info_val) if isinstance(info_val, str) else info_val
            info["status"] = "running"
            if "paused_time_left" in info:
                del info["paused_time_left"]
            _execute("UPDATE session_metadata SET schedule_info = ? WHERE session_id = ? OR job_id = ?", (json.dumps(info), session_id, clean_id))
    except Exception as err:
        logger.error(f"Failed to update session_metadata for resumed timer {item_id}: {err}")
    logger.info(f"Timer {item_id} resumed")
    return True


def restart_timer(item_id: str) -> bool:
    clean_id = item_id.replace("task_", "") if item_id.startswith("task_") else item_id
    job = scheduler.get_job(clean_id) or scheduler.get_job(item_id)
    
    meta = _timer_meta.get(clean_id, {})
    task_type = meta.get("type") or (_infer_type(job) if job else "scheduled")
    kwargs = (job.kwargs if job else {}) or {}
    label = kwargs.get("label", (job.name if job else clean_id) or clean_id)
    agent_id = kwargs.get("agent_id")
    prompt = kwargs.get("prompt")
    duration_seconds = kwargs.get("duration") or meta.get("duration") or 60
    time_str = kwargs.get("target_time_str") or meta.get("target_time")
    interval_hours = kwargs.get("interval_hours") or meta.get("interval_hours") or 1.0
    cron_expr = kwargs.get("cron_expr") or meta.get("cron_expr")

    return update_timer(
        item_id=clean_id,
        label=label,
        task_type=task_type,
        agent_id=agent_id,
        prompt=prompt,
        duration_seconds=duration_seconds,
        time_str=time_str,
        interval_hours=interval_hours,
        cron_expr=cron_expr,
    )


def trigger_timer_now(item_id: str) -> bool:
    clean_id = item_id.replace("task_", "") if item_id.startswith("task_") else item_id
    job = scheduler.get_job(clean_id) or scheduler.get_job(item_id)
    
    agent_id = "jarvis"
    prompt = None
    chat_id = "dashboard"
    label = clean_id
    task_type = "scheduled"

    if job is not None:
        kwargs = job.kwargs or {}
        agent_id = kwargs.get("agent_id") or "jarvis"
        prompt = kwargs.get("prompt")
        chat_id = kwargs.get("chat_id", "dashboard")
        label = kwargs.get("label", clean_id)
        task_type = _infer_type(job)
    else:
        # Fallback to database lookup in session_metadata table
        try:
            from backend.database import _execute
            import json
            session_id = f"task_{clean_id}"
            rows = _execute(
                "SELECT title, agent_id, schedule_type, schedule_info FROM session_metadata WHERE session_id = ? OR job_id = ?",
                (session_id, clean_id)
            )
            if rows:
                title_db, agent_id_db, type_db, info_str = rows[0]
                agent_id = agent_id_db or "jarvis"
                label = title_db or clean_id
                task_type = type_db or "scheduled"
                if info_str:
                    try:
                        info_dict = json.loads(info_str) if isinstance(info_str, str) else info_str
                        prompt = info_dict.get("prompt")
                        if info_dict.get("label"):
                            label = info_dict.get("label")
                        if info_dict.get("agent_id"):
                            agent_id = info_dict.get("agent_id")
                    except Exception:
                        pass
        except Exception as err:
            logger.error(f"Error restoring metadata for timer {item_id}: {err}")

    if not prompt:
        # Fallback 2: retrieve prompt from messages table if this was an existing task session
        try:
            from backend.database import _execute
            session_id = f"task_{clean_id}"
            msg_rows = _execute(
                "SELECT content FROM messages WHERE session_id = ? AND role = 'user' ORDER BY id ASC LIMIT 1",
                (session_id,)
            )
            if msg_rows and msg_rows[0][0]:
                raw_msg = msg_rows[0][0]
                if raw_msg.startswith("[Scheduled Run"):
                    parts = raw_msg.split("] ", 1)
                    prompt = parts[1] if len(parts) > 1 else raw_msg
                else:
                    prompt = raw_msg
        except Exception as err:
            logger.error(f"Error fetching fallback prompt from messages table for {item_id}: {err}")

    if not prompt and label and label != clean_id:
        prompt = label

    if not prompt:
        logger.warning(f"Cannot trigger task {item_id}: job not found in memory or database, or prompt is empty.")
        return False

    task_session_id = f"task_{clean_id}"
    _register_scheduled_session(clean_id, label, task_type, agent_id, prompt, status="running")
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_trigger_agent_task(
            agent_id=agent_id,
            prompt=prompt,
            chat_id=chat_id,
            task_session_id=task_session_id,
            job_id=clean_id,
            label=label,
        ))
    except RuntimeError:
        asyncio.run(_trigger_agent_task(
            agent_id=agent_id,
            prompt=prompt,
            chat_id=chat_id,
            task_session_id=task_session_id,
            job_id=clean_id,
            label=label,
        ))
    logger.info(f"Manually triggered task {clean_id} (agent={agent_id}, session_id={task_session_id})")
    return True



def _infer_type(job) -> str:
    func = getattr(job, "func", None)
    name = getattr(func, "__name__", "")
    if "cron" in name:
        return "cron"
    if "recurring" in name:
        return "recurring"
    if "alarm" in name:
        return "alarm"
    return "one-shot"


def get_all_timers() -> List[Dict[str, Any]]:
    jobs = scheduler.get_jobs()
    now_tz = datetime.now(scheduler.timezone)
    result = []
    seen_ids = set()

    # Pre-fetch session_metadata table for fallback prompt/agent_id lookup
    db_info_map = {}
    try:
        from backend.database import _execute
        import json
        rows = _execute("SELECT session_id, title, agent_id, schedule_type, schedule_info FROM session_metadata WHERE is_scheduled = 1")
        for r in rows:
            session_id, title, db_agent, schedule_type, schedule_info_raw = r
            j_id = session_id.replace("task_", "") if session_id and session_id.startswith("task_") else (r[0] or "")
            if j_id and schedule_info_raw:
                try:
                    info = json.loads(schedule_info_raw) if isinstance(schedule_info_raw, str) else schedule_info_raw
                    db_info_map[j_id] = {
                        "prompt": info.get("prompt"),
                        "agent_id": info.get("agent_id") or db_agent,
                        "label": info.get("label") or title,
                        "status": info.get("status"),
                        "created_at": info.get("created_at"),
                        "interval_hours": info.get("interval_hours"),
                        "cron_expr": info.get("cron_expr"),
                        "duration": info.get("duration"),
                        "target_time": info.get("target_time"),
                        "task_type": schedule_type or info.get("task_type"),
                        "paused_time_left": info.get("paused_time_left"),
                    }
                except Exception:
                    pass
    except Exception as e:
        logger.error(f"Error building db_info_map in get_all_timers: {e}")

    for job in jobs:
        if job.id == "skill_distillation":
            continue
        seen_ids.add(job.id)
        kwargs = job.kwargs or {}
        job_id = job.id
        db_fallback = db_info_map.get(job_id, {})
        label = kwargs.get("label") or db_fallback.get("label") or job.name or job_id
        meta = _timer_meta.get(job_id, {})
        job_type = meta.get("type") or kwargs.get("task_type") or db_fallback.get("task_type") or _infer_type(job)
        created_at = meta.get("created_at") or kwargs.get("created_at") or db_fallback.get("created_at") or ""
        next_run = getattr(job, "next_run_time", None)
        status = meta.get("status") or db_fallback.get("status")
        if not status:
            status = "paused" if next_run is None else "running"

        if status != "paused" and job_type in ("recurring", "cron") and (not next_run or next_run <= now_tz):
            if hasattr(job, "trigger") and hasattr(job.trigger, "get_next_fire_time"):
                prev_time = next_run if next_run else getattr(job.trigger, "start_date", now_tz)
                next_run = job.trigger.get_next_fire_time(prev_time, now_tz)

        if status == "paused":
            time_left = meta.get("paused_time_left") or db_fallback.get("paused_time_left") or 0
        else:
            time_left = max(0, int((next_run - now_tz).total_seconds())) if next_run else 0

        agent_id = kwargs.get("agent_id") or meta.get("agent_id") or db_fallback.get("agent_id") or "jarvis"
        prompt = kwargs.get("prompt") or meta.get("prompt") or db_fallback.get("prompt") or ""

        entry: Dict[str, Any] = {
            "id": job_id,
            "label": label,
            "status": status,
            "time_left": time_left,
            "type": job_type,
            "created_at": created_at,
            "agent_id": agent_id,
            "prompt": prompt,
        }
        if job_type == "cron":
            entry["cron_expr"] = kwargs.get("cron_expr") or meta.get("cron_expr") or db_fallback.get("cron_expr")
            entry["fire_count"] = _fire_counts.get(job_id, 0)
        elif job_type == "recurring":
            entry["interval_hours"] = kwargs.get("interval_hours") or meta.get("interval_hours") or db_fallback.get("interval_hours")
            entry["fire_count"] = _fire_counts.get(job_id, 0)
        elif job_type == "alarm":
            entry["target_time"] = kwargs.get("target_time_str") or meta.get("target_time") or db_fallback.get("target_time")
        elif job_type == "one-shot":
            entry["duration"] = kwargs.get("duration") or meta.get("duration") or db_fallback.get("duration")

        result.append(entry)

    # Also query completed/paused items from session_metadata DB table
    for j_id, info in db_info_map.items():
        if not j_id or j_id in seen_ids or j_id == "skill_distillation":
            continue

        seen_ids.add(j_id)
        meta = _timer_meta.get(j_id, {})
        label = info.get("label") or j_id
        if label.startswith("⏰ "):
            label = label[2:]
        elif label.startswith("🔔 "):
            label = label[2:]

        status = meta.get("status") or info.get("status") or "completed"
        job_type = info.get("task_type") or meta.get("type") or "one-shot"
        created_at = meta.get("created_at") or info.get("created_at") or ""
        agent_id = meta.get("agent_id") or info.get("agent_id") or "jarvis"
        prompt = meta.get("prompt") or info.get("prompt") or ""

        entry: Dict[str, Any] = {
            "id": j_id,
            "label": label,
            "status": status,
            "time_left": info.get("paused_time_left") or meta.get("paused_time_left") or 0 if status == "paused" else 0,
            "type": job_type,
            "created_at": created_at,
            "agent_id": agent_id,
            "prompt": prompt,
        }
        if job_type == "cron":
            entry["cron_expr"] = info.get("cron_expr") or meta.get("cron_expr")
            entry["fire_count"] = _fire_counts.get(j_id, 0)
        elif job_type == "recurring":
            entry["interval_hours"] = info.get("interval_hours") or meta.get("interval_hours")
            entry["fire_count"] = _fire_counts.get(j_id, 0)
        elif job_type == "alarm":
            entry["target_time"] = info.get("target_time") or meta.get("target_time")
        elif job_type == "one-shot":
            entry["duration"] = info.get("duration") or meta.get("duration")

        result.append(entry)

    result.sort(key=lambda x: (x.get("status") == "completed", x.get("time_left", 0)))
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
    if job_id and agent_id:
        try:
            _register_scheduled_session(job_id, label or job_id, "recurring", agent_id, prompt)
        except Exception:
            pass

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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        response_text = await agent_instance.respond(
            prompt, session_id=session_id, override_agent_id=agent_id
        )

        if not response_text or not response_text.strip():
            response_text = "The scheduled automation task completed successfully."

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
    except asyncio.CancelledError:
        logger.info(f"Scheduled agent task '{job_id or label}' cancelled.")
    except Exception as exc:
        logger.error(f"Error executing scheduled agent task: {exc}")


async def _send_telegram_alert(chat_id: str, text: str) -> None:
    """Send a Telegram message. Also imported by price_monitor.py."""
    if not chat_id or chat_id == "dashboard" or not (chat_id.lstrip('-').isdigit() or chat_id.startswith('@')):
        return
    try:
        from backend.bot import telegram_app
        if telegram_app:
            try:
                await telegram_app.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
            except Exception as pe:
                if "can't parse entities" in str(pe).lower() or "entity" in str(pe).lower() or "bad request" in str(pe).lower():
                    logger.warning(f"Telegram Markdown parse failed in scheduler: {pe}. Retrying with plain text.")
                    await telegram_app.bot.send_message(chat_id=chat_id, text=text)
                else:
                    raise pe
    except Exception as exc:
        exc_str = str(exc)
        exc_type = type(exc).__name__
        if "NetworkError" in exc_type or "ConnectError" in exc_type or "TimedOut" in exc_type or "No address associated with hostname" in exc_str:
            logger.warning(f"Telegram alert transient network issue: {exc}")
        else:
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
    try:
        # Initial sleep delay so FastAPI startup & Uvicorn HTTP server bind instantly without blocking
        await asyncio.sleep(10)
        while True:
            try:
                from backend.database import purge_invalid_distilled_skills
                purged = await asyncio.to_thread(purge_invalid_distilled_skills)
                if purged:
                    logger.info(f"Skill distillation loop: purged {purged} contaminated distilled skills.")
                from backend.skill_loop import get_skill_distiller
                distiller = get_skill_distiller()
                distilled = await asyncio.to_thread(distiller.process_undistilled_logs, min_steps=3, limit=5)
                if distilled:
                    logger.info(f"Skill distillation loop: created {len(distilled)} new skills.")
                    await _broadcast_ws({"type": "skills_distilled", "skills": distilled})
            except asyncio.CancelledError:
                raise
            except Exception as err:
                logger.error(f"Skill distillation loop error: {err}")
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        logger.info("Skill distillation loop cancelled.")


def start_skill_distillation_loop(interval_seconds: int = 900) -> Optional[asyncio.Task]:
    key = "skill_distillation_loop"
    if key not in _RUNNING_TASKS or _RUNNING_TASKS[key].done():
        task = asyncio.create_task(_run_skill_distillation_loop(interval_seconds=interval_seconds))
        _RUNNING_TASKS[key] = task
        return task
    return _RUNNING_TASKS[key]


async def _run_rss_poller_loop(interval_seconds: int = 300) -> None:
    logger.info(f"Starting autonomous RSS poller loop with interval={interval_seconds}s...")
    from backend.rss_service import fetch_all_active_rss_nodes
    try:
        while True:
            try:
                results = await asyncio.to_thread(fetch_all_active_rss_nodes)
                logger.debug(f"RSS poller sync executed: {len(results)} nodes processed.")
            except asyncio.CancelledError:
                raise
            except Exception as err:
                logger.error(f"RSS poller loop error: {err}")
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        logger.info("RSS poller loop cancelled.")


def start_rss_poller_loop(interval_seconds: int = 300) -> Optional[asyncio.Task]:
    key = "rss_poller_loop"
    if key not in _RUNNING_TASKS or _RUNNING_TASKS[key].done():
        task = asyncio.create_task(_run_rss_poller_loop(interval_seconds=interval_seconds))
        _RUNNING_TASKS[key] = task
        return task
    return _RUNNING_TASKS[key]


def shutdown_scheduler(wait: bool = False) -> None:
    """Cleanly stop background loops and shutdown APScheduler."""
    for key, task in list(_RUNNING_TASKS.items()):
        if task and not task.done():
            task.cancel()
    if scheduler.running:
        try:
            scheduler.shutdown(wait=wait)
        except Exception as e:
            logger.warning(f"Error shutting down APScheduler: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# COMPATIBILITY SHIMS — no-ops now, kept so main.py imports don't break
# ═══════════════════════════════════════════════════════════════════════════════

def restore_state() -> None:
    """Populate _timer_meta and restore scheduled jobs from PostgreSQL session_metadata DB table."""
    try:
        from backend.database import _execute
        rows = _execute("SELECT session_id, title, agent_id, job_id, schedule_type, schedule_info FROM session_metadata WHERE is_scheduled = 1")
        restored_count = 0
        for r in rows:
            session_id, title, agent_id, job_id, schedule_type, schedule_info_raw = r
            if not job_id or job_id == "skill_distillation":
                continue
            
            info = {}
            if schedule_info_raw:
                try:
                    info = json.loads(schedule_info_raw)
                except Exception:
                    pass
            
            label = info.get("label") or title or job_id
            if label.startswith("⏰ "):
                label = label[2:]
            elif label.startswith("🔔 "):
                label = label[2:]
                
            task_type = schedule_type or info.get("task_type") or "recurring"
            prompt = info.get("prompt")
            if _is_redundant_desk_orchestrator_job(
                label=label, agent_id=agent_id, prompt=prompt, task_type=task_type, job_id=job_id
            ):
                logger.info(
                    "Skipping restore of redundant desk orchestrator job '%s' (%s)",
                    label, job_id,
                )
                _drop_scheduled_job(job_id, session_id=session_id)
                continue
            status = info.get("status") or "running"
            chat_id = info.get("chat_id", "dashboard")
            created_at = info.get("created_at") or datetime.now(scheduler.timezone).strftime("%Y-%m-%d %H:%M:%S")

            cron_expr_raw = info.get("cron_expr")
            cron_healed = False
            if task_type == "cron":
                if not cron_expr_raw or cron_expr_raw.strip() in ("* * * * *", "* * * * * *"):
                    cron_healed = True
                    from backend.plugins import hook
                    healed = hook("heal_cron_expr", job_id)
                    cron_expr_raw = healed or "0 * * * *"

            _timer_meta[job_id] = {
                "type": task_type,
                "created_at": created_at,
                "interval_hours": info.get("interval_hours", 1.0),
                "cron_expr": cron_expr_raw,
                "duration": info.get("duration"),
                "target_time": info.get("target_time"),
                "status": status,
                "paused_time_left": info.get("paused_time_left"),
            }

            if cron_healed and task_type == "cron":
                try:
                    _register_scheduled_session(
                        job_id, label, "cron", agent_id or "system", prompt or f"Run task {label}",
                        status=status, extra={"cron_expr": cron_expr_raw, "fire_count": info.get("fire_count", 0)}
                    )
                except Exception as _he:
                    logger.warning(f"Could not persist healed cron metadata for {job_id}: {_he}")

            if status == "completed":
                continue

            existing_job = scheduler.get_job(job_id)
            if existing_job:
                if status == "paused":
                    existing_job.pause()
                elif status == "running" or status == "scheduled":
                    existing_job.resume()
            else:
                if task_type == "cron":
                    # Support optional trailing timezone (e.g. "0 9 * * mon-fri Europe/London")
                    cron_parts = cron_expr_raw.strip().split()
                    cron_tz = scheduler.timezone
                    cron_expr = cron_expr_raw
                    if len(cron_parts) == 6:
                        cron_expr = " ".join(cron_parts[:5])
                        try:
                            import pytz
                            cron_tz = pytz.timezone(cron_parts[5])
                        except Exception:
                            cron_tz = scheduler.timezone
                    try:
                        trigger = CronTrigger.from_crontab(cron_expr, timezone=cron_tz)
                        target_func = _job_cron
                        target_kwargs = {
                            "job_id": job_id, "label": label, "cron_expr": cron_expr_raw,
                            "chat_id": chat_id, "agent_id": agent_id, "prompt": prompt,
                            "created_at": created_at, "task_type": "cron"
                        }
                        from backend.plugins import hook
                        private_cron = hook("resolve_cron_job", job_id, agent_id, label)
                        if private_cron:
                            target_func, extra_kwargs = private_cron
                            target_kwargs.update(extra_kwargs)

                        job = scheduler.add_job(
                            target_func,
                            trigger=trigger,
                            kwargs=target_kwargs,
                            id=job_id, name=label, replace_existing=True,
                        )
                        if status == "paused":
                            job.pause()
                        restored_count += 1
                    except Exception as err:
                        logger.error(f"Failed restoring cron job {job_id} ({cron_expr}): {err}")
                elif task_type == "recurring":
                    interval_hours = float(info.get("interval_hours") or 1.0)
                    job = scheduler.add_job(
                        _job_recurring,
                        trigger=IntervalTrigger(hours=interval_hours),
                        kwargs={"job_id": job_id, "label": label, "interval_hours": interval_hours,
                                "chat_id": chat_id, "agent_id": agent_id, "prompt": prompt,
                                "created_at": created_at, "task_type": "recurring"},
                        id=job_id, name=label, replace_existing=True,
                    )
                    if status == "paused":
                        job.pause()
                    restored_count += 1
                elif task_type == "one-shot":
                    duration = int(info.get("duration") or 60)
                    run_at = datetime.now(scheduler.timezone) + timedelta(seconds=duration)
                    job = scheduler.add_job(
                        _job_one_shot,
                        trigger=DateTrigger(run_date=run_at),
                        kwargs={"job_id": job_id, "label": label, "duration": duration,
                                "chat_id": chat_id, "agent_id": agent_id, "prompt": prompt,
                                "created_at": created_at, "task_type": "one-shot"},
                        id=job_id, name=label, replace_existing=True,
                    )
                    if status == "paused":
                        job.pause()
                    restored_count += 1
                elif task_type == "alarm":
                    target_time_str = info.get("target_time") or created_at
                    from zoneinfo import ZoneInfo
                    tz = ZoneInfo("Asia/Jerusalem")
                    now_tz = datetime.now(tz)
                    target_dt = now_tz + timedelta(minutes=5)
                    job = scheduler.add_job(
                        _job_alarm,
                        trigger=DateTrigger(run_date=target_dt),
                        kwargs={"job_id": job_id, "label": label, "chat_id": chat_id,
                                "target_time_str": target_time_str, "agent_id": agent_id, "prompt": prompt,
                                "created_at": created_at, "task_type": "alarm"},
                        id=job_id, name=label, replace_existing=True,
                    )
                    if status == "paused":
                        job.pause()
                    restored_count += 1

        logger.info(f"Scheduler: restored {restored_count} tasks from session_metadata DB table.")
    except Exception as e:
        logger.error(f"Error in restore_state from DB: {e}")


async def _start_restored_tasks() -> None:
    """No-op: APScheduler auto-starts restored jobs."""
    pass



def _job_watcher_sync():
    """Background job to run watcher's memory synchronization."""
    try:
        from backend.plugins import hook
        hook("watcher_sync")
    except Exception as e:
        logger.warning(f"Error running watcher sync: {e}")

def start_watcher_loop(interval_seconds: int = 300):
    job_id = "watcher_sync_loop"
    try:
        if scheduler.get_job(job_id):
            scheduler.modify_job(job_id, func=_job_watcher_sync, kwargs={}, max_instances=2)
        else:
            scheduler.add_job(
                _job_watcher_sync, 'interval', seconds=interval_seconds,
                kwargs={}, id=job_id, name="Watcher Memory Sync", replace_existing=True,
                coalesce=True, max_instances=2, misfire_grace_time=300
            )
        logger.info(f"Started Watcher Sync loop (interval: {interval_seconds}s)")
    except Exception as e:
        logger.warning(f"Watcher Sync loop job {job_id} could not be added/modified: {e}")

def _load_private_plugins(scheduler_obj=None, restore_items=None) -> bool:
    from backend.plugins import init_all
    return init_all(scheduler_obj, restore_items)

