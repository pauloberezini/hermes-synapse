import time
import uuid
import asyncio
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("hermes.scheduler")

ACTIVE_TIMERS:    List['TimerTask']         = []
ACTIVE_REMINDERS: List['RecurringReminder'] = []
ACTIVE_ALARMS:    List['AlarmTask']         = []
RUNNING_TASKS:    Dict[str, asyncio.Task]   = {}


async def shutdown_scheduler_tasks() -> None:
    """Cancel scheduler jobs and wait until their cleanup handlers finish."""
    global RUNNING_TASKS
    tasks = list(RUNNING_TASKS.values())
    RUNNING_TASKS = {}
    current_loop = asyncio.get_running_loop()
    pending: List[asyncio.Task] = []
    for task in tasks:
        if task.done() or task.get_loop().is_closed():
            continue
        task.cancel()
        if task.get_loop() is current_loop:
            pending.append(task)
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


# ═══════════════════════════════════════════════════════════════════════════════
# ONE-SHOT TIMER
# ═══════════════════════════════════════════════════════════════════════════════

class TimerTask:
    def __init__(self, timer_id: str, label: str, duration_seconds: int, chat_id: str, agent_id: Optional[str] = None, prompt: Optional[str] = None):
        self.id           = timer_id
        self.label        = label
        self.duration     = duration_seconds
        self.chat_id      = chat_id
        self.agent_id     = agent_id
        self.prompt       = prompt
        self.start_time   = time.time()
        self.status       = "running"
        self.created_at   = time.strftime("%Y-%m-%d %H:%M:%S")

    def get_time_left(self) -> int:
        if self.status != "running":
            return 0
        return max(0, int(self.duration - (time.time() - self.start_time)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":         self.id,
            "label":      self.label,
            "duration":   self.duration,
            "time_left":  self.get_time_left(),
            "status":     self.status,
            "created_at": self.created_at,
            "type":       "one-shot",
            "agent_id":   self.agent_id,
            "prompt":     self.prompt,
        }

async def _trigger_agent_task(agent_id: str, prompt: str, chat_id: str):
    try:
        from backend.agent import agent_instance
        from backend.websocket_manager import manager
        
        # 1. Broadcast user message
        await manager.broadcast({
            "type": "chat_message",
            "role": "user",
            "content": f"[Scheduled Task] {prompt}",
            "chat_id": agent_id
        })
        
        # 2. Call agent
        response_text = await agent_instance.respond(prompt, session_id=agent_id)
        cost_usd = agent_instance.last_costs.get(agent_id, 0.0)
        suppress_tts = agent_instance.check_and_clear_suppress_tts(agent_id)
        saved_ids = agent_instance.last_saved_ids.get(agent_id, {})
        user_msg_id = saved_ids.get("user")
        assistant_msg_id = saved_ids.get("assistant")
        
        # 3. Broadcast assistant response
        await manager.broadcast({
            "type": "chat_message",
            "role": "assistant",
            "content": response_text,
            "chat_id": agent_id,
            "cost_usd": cost_usd,
            "suppress_tts": suppress_tts,
            "id": assistant_msg_id
        })
        
        # Update user message ID
        if user_msg_id:
            await manager.broadcast({
                "type": "user_message_id_update",
                "chat_id": agent_id,
                "content": prompt,
                "id": user_msg_id
            })
            
        # Update logs
        from backend.agent import DECISION_LOGS
        await manager.broadcast({
            "type": "logs_update",
            "logs": DECISION_LOGS[:20]
        })

        # Send Telegram notification with result
        await _send_telegram_alert(
            chat_id,
            f"🤖 **SCHEDULED TASK RESULT**\n\n"
            f"• **Agent**: `{agent_id}`\n"
            f"• **Task**: {prompt}\n\n"
            f"📝 **Result**:\n{response_text}"
        )
    except Exception as e:
        logger.error(f"Error executing scheduled agent task: {e}")


async def run_timer(task: TimerTask):
    logger.info(f"Timer {task.id} started — {task.duration}s: '{task.label}'")
    from backend.activity_logger import log_activity
    log_activity(
        activity_type="idle",
        source="Scheduler",
        message=f"⏲️ Timer started for {task.duration} sec: '{task.label}'"
    )
    try:
        await asyncio.sleep(task.duration)
        task.status = "completed"
        logger.info(f"Timer {task.id} completed.")

        if task.agent_id and task.prompt:
            # Just do the work and send the result, do not trigger normal alarm signals
            asyncio.create_task(_trigger_agent_task(task.agent_id, task.prompt, task.chat_id))
        else:
            log_activity(
                activity_type="idle",
                source="Scheduler",
                message=f"✅ Timer complete: '{task.label}'"
            )
            await _send_telegram_alert(
                task.chat_id,
                f"🏛️ **ATTENTION, SIR**\n\n"
                f"Timer complete:\n"
                f"• Event: **{task.label}**\n"
                f"• Duration: {task.duration} sec\n"
                f"• Status: ✅ Completed"
            )
            
        await _broadcast_ws({
            "type":    "timer_completed",
            "timer":   task.to_dict(),
        })
    except asyncio.CancelledError:
        task.status = "cancelled"
        logger.info(f"Timer {task.id} cancelled.")
    except Exception as e:
        task.status = "failed"
        logger.error(f"Timer {task.id} error: {e}")
    finally:
        if task.id in RUNNING_TASKS:
            del RUNNING_TASKS[task.id]


def add_timer(label: str, duration_seconds: int, chat_id: str, agent_id: Optional[str] = None, prompt: Optional[str] = None) -> str:
    timer_id = str(uuid.uuid4())
    task = TimerTask(timer_id, label, duration_seconds, chat_id, agent_id, prompt)
    ACTIVE_TIMERS.append(task)
    task_handle = asyncio.create_task(run_timer(task))
    RUNNING_TASKS[timer_id] = task_handle
    return timer_id


# ═══════════════════════════════════════════════════════════════════════════════
# ALARM CLOCK (BUDILNIK)
# ═══════════════════════════════════════════════════════════════════════════════

class AlarmTask:
    def __init__(self, alarm_id: str, label: str, target_time: float, chat_id: str, agent_id: Optional[str] = None, prompt: Optional[str] = None):
        self.id          = alarm_id
        self.label       = label
        self.target_time = target_time  # epoch timestamp when it should fire
        self.chat_id     = chat_id
        self.agent_id     = agent_id
        self.prompt       = prompt
        self.status      = "running"
        
        # created_at in Israel local time
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now_local = datetime.fromtimestamp(time.time(), ZoneInfo("Asia/Jerusalem"))
        self.created_at  = now_local.strftime("%Y-%m-%d %H:%M:%S")

    def get_time_left(self) -> int:
        if self.status != "running":
            return 0
        return max(0, int(self.target_time - time.time()))

    def to_dict(self) -> Dict[str, Any]:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        target_dt = datetime.fromtimestamp(self.target_time, ZoneInfo("Asia/Jerusalem"))
        return {
            "id":          self.id,
            "label":       self.label,
            "target_time": target_dt.strftime("%Y-%m-%d %H:%M:%S"),
            "time_left":   self.get_time_left(),
            "status":      self.status,
            "created_at":  self.created_at,
            "type":        "alarm",
            "agent_id":    self.agent_id,
            "prompt":      self.prompt,
        }


async def run_alarm(task: AlarmTask):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    target_dt = datetime.fromtimestamp(task.target_time, ZoneInfo("Asia/Jerusalem"))
    target_time_str = target_dt.strftime("%Y-%m-%d %H:%M:%S")
    
    logger.info(f"Alarm {task.id} scheduled to fire at {task.target_time} (in {task.get_time_left()}s): '{task.label}'")
    from backend.activity_logger import log_activity
    log_activity(
        activity_type="idle",
        source="Scheduler",
        message=f"⏰ Alarm set for {target_time_str}: '{task.label}'"
    )
    try:
        delay = task.get_time_left()
        await asyncio.sleep(delay)
        task.status = "completed"
        logger.info(f"Alarm {task.id} completed.")

        if task.agent_id and task.prompt:
            # Just do the work and send the result
            asyncio.create_task(_trigger_agent_task(task.agent_id, task.prompt, task.chat_id))
        else:
            log_activity(
                activity_type="idle",
                source="Scheduler",
                message=f"🔔 Alarm triggered: '{task.label}'"
            )
            from datetime import datetime
            from zoneinfo import ZoneInfo
            target_dt = datetime.fromtimestamp(task.target_time, ZoneInfo("Asia/Jerusalem"))
            target_time_str = target_dt.strftime("%Y-%m-%d %H:%M:%S")

            await _send_telegram_alert(
                task.chat_id,
                f"⏰ **ALARM, SIR**\n\n"
                f"• Event: **{task.label}**\n"
                f"• Trigger time: {target_time_str}\n"
                f"• Status: ✅ Completed"
            )
            
        await _broadcast_ws({
            "type":    "alarm_fired",
            "alarm":   task.to_dict(),
        })
    except asyncio.CancelledError:
        task.status = "cancelled"
        logger.info(f"Alarm {task.id} cancelled.")
    except Exception as e:
        task.status = "failed"
        logger.error(f"Alarm {task.id} error: {e}")
    finally:
        if task.id in RUNNING_TASKS:
            del RUNNING_TASKS[task.id]


def add_alarm(time_str: str, label: str, chat_id: str, agent_id: Optional[str] = None, prompt: Optional[str] = None) -> str:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    tz = ZoneInfo("Asia/Jerusalem")
    now = datetime.now(tz)
    time_str = time_str.strip()
    
    target_timestamp = None
    
    # Try YYYY-MM-DD HH:MM:SS / YYYY-MM-DD HH:MM
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(time_str, fmt).replace(tzinfo=tz)
            target_timestamp = dt.timestamp()
            break
        except ValueError:
            continue
            
    # Try HH:MM:SS / HH:MM
    if not target_timestamp:
        for fmt in ("%H:%M:%S", "%H:%M"):
            try:
                t = datetime.strptime(time_str, fmt).time()
                dt = datetime.combine(now.date(), t).replace(tzinfo=tz)
                if dt < now:
                    dt += timedelta(days=1)
                target_timestamp = dt.timestamp()
                break
            except ValueError:
                continue
                
    if not target_timestamp:
        raise ValueError(f"Could not parse time format: '{time_str}'. Use HH:MM or YYYY-MM-DD HH:MM.")
        
    alarm_id = str(uuid.uuid4())
    task = AlarmTask(alarm_id, label, target_timestamp, chat_id, agent_id, prompt)
    ACTIVE_ALARMS.append(task)
    
    task_handle = asyncio.create_task(run_alarm(task))
    RUNNING_TASKS[alarm_id] = task_handle
    return alarm_id


def cancel_timer_or_alarm(item_id: str) -> bool:
    # Check timers
    for t in ACTIVE_TIMERS:
        if t.id == item_id:
            if t.status == "running":
                t.status = "cancelled"
                if item_id in RUNNING_TASKS:
                    RUNNING_TASKS[item_id].cancel()
            else:
                t.status = "dismissed"
            return True
            
    # Check alarms
    for a in ACTIVE_ALARMS:
        if a.id == item_id:
            if a.status == "running":
                a.status = "cancelled"
                if item_id in RUNNING_TASKS:
                    RUNNING_TASKS[item_id].cancel()
            else:
                a.status = "dismissed"
            return True
            
    return False


def get_all_timers() -> List[Dict[str, Any]]:
    global ACTIVE_TIMERS, ACTIVE_ALARMS, ACTIVE_REMINDERS
    cutoff = time.time()
    
    # Keep running timers and completed ones for up to 5 min
    ACTIVE_TIMERS = [
        t for t in ACTIVE_TIMERS
        if t.status == "running" or (cutoff - (t.start_time + t.duration)) < 300
    ]
    
    # Keep running alarms and completed ones for up to 5 min
    ACTIVE_ALARMS = [
        a for a in ACTIVE_ALARMS
        if a.status == "running" or (cutoff - a.target_time) < 300
    ]
    
    res = []
    res.extend([t.to_dict() for t in ACTIVE_TIMERS if t.status != "dismissed"])
    res.extend([a.to_dict() for a in ACTIVE_ALARMS if a.status != "dismissed"])
    res.extend([r.to_dict() for r in ACTIVE_REMINDERS if r.status != "cancelled" and r.status != "dismissed"])
    
    # Sort: running first, then sort by time left
    res.sort(key=lambda x: (x["status"] != "running", x.get("time_left", 0)))
    return res


# ═══════════════════════════════════════════════════════════════════════════════
# RECURRING REMINDER
# ═══════════════════════════════════════════════════════════════════════════════

class RecurringReminder:
    def __init__(self, reminder_id: str, label: str, interval_hours: float, chat_id: str, agent_id: Optional[str] = None, prompt: Optional[str] = None):
        self.id             = reminder_id
        self.label          = label
        self.interval_hours = interval_hours
        self.interval_secs  = interval_hours * 3600
        self.chat_id        = chat_id
        self.agent_id       = agent_id
        self.prompt         = prompt
        self.status         = "running"
        self.created_at     = time.strftime("%Y-%m-%d %H:%M:%S")
        self.fire_count     = 0
        self.next_fire_at   = time.time() + self.interval_secs

    def get_time_left(self) -> int:
        return max(0, int(self.next_fire_at - time.time()))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id":             self.id,
            "label":          self.label,
            "interval_hours": self.interval_hours,
            "time_left":      self.get_time_left(),
            "fire_count":     self.fire_count,
            "status":         self.status,
            "created_at":     self.created_at,
            "type":           "recurring",
            "agent_id":       self.agent_id,
            "prompt":         self.prompt,
        }


async def run_recurring_reminder(reminder: RecurringReminder):
    logger.info(
        f"Recurring reminder {reminder.id} started — "
        f"every {reminder.interval_hours}h: '{reminder.label}'"
    )
    from backend.activity_logger import log_activity
    log_activity(
        activity_type="idle",
        source="Scheduler",
        message=f"🔔 Recurring reminder started every {reminder.interval_hours}h: '{reminder.label}'"
    )
    try:
        while reminder.status == "running":
            await asyncio.sleep(reminder.interval_secs)
            if reminder.status != "running":
                break

            reminder.fire_count  += 1
            reminder.next_fire_at = time.time() + reminder.interval_secs
            logger.info(f"Recurring reminder {reminder.id} fired #{reminder.fire_count}")

            if reminder.agent_id and reminder.prompt:
                # Just do the work and send the result
                asyncio.create_task(_trigger_agent_task(reminder.agent_id, reminder.prompt, reminder.chat_id))
            else:
                hours_str = (
                    f"{int(reminder.interval_hours)} h"
                    if reminder.interval_hours >= 1
                    else f"{int(reminder.interval_hours * 60)} min"
                )
                log_activity(
                    activity_type="idle",
                    source="Scheduler",
                    message=f"🔔 Recurring reminder #{reminder.fire_count} triggered: '{reminder.label}'"
                )
                await _send_telegram_alert(
                    reminder.chat_id,
                    f"🔔 **REMINDER, SIR** (#{reminder.fire_count})\n\n"
                    f"• {reminder.label}\n"
                    f"• Repeat every: {hours_str}\n\n"
                    f"_Next trigger in {hours_str}._"
                )
                
            await _broadcast_ws({
                "type":     "reminder_fired",
                "reminder": reminder.to_dict(),
            })
    except asyncio.CancelledError:
        reminder.status = "cancelled"
        logger.info(f"Recurring reminder {reminder.id} cancelled.")
    except Exception as e:
        reminder.status = "failed"
        logger.error(f"Recurring reminder {reminder.id} error: {e}")
    finally:
        if reminder.id in RUNNING_TASKS:
            del RUNNING_TASKS[reminder.id]


def add_recurring_reminder(label: str, interval_hours: float, chat_id: str, agent_id: Optional[str] = None, prompt: Optional[str] = None) -> str:
    reminder_id = str(uuid.uuid4())
    reminder = RecurringReminder(reminder_id, label, interval_hours, chat_id, agent_id, prompt)
    ACTIVE_REMINDERS.append(reminder)
    task_handle = asyncio.create_task(run_recurring_reminder(reminder))
    RUNNING_TASKS[reminder_id] = task_handle
    return reminder_id


def cancel_recurring_reminder(reminder_id: str) -> bool:
    for r in ACTIVE_REMINDERS:
        if r.id == reminder_id:
            if r.status == "cancelled" or r.status == "dismissed":
                return False
            r.status = "cancelled"
            if reminder_id in RUNNING_TASKS:
                RUNNING_TASKS[reminder_id].cancel()
            return True
    return False


def get_all_reminders() -> List[Dict[str, Any]]:
    return [r.to_dict() for r in ACTIVE_REMINDERS if r.status == "running"]


# ═══════════════════════════════════════════════════════════════════════════════
# SHARED HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

async def _send_telegram_alert(chat_id: str, text: str):
    try:
        from backend.bot import telegram_app
        if telegram_app:
            await telegram_app.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode="Markdown"
            )
    except Exception as e:
        logger.error(f"Telegram alert error: {e}")


async def _broadcast_ws(payload: Dict):
    try:
        from backend.websocket_manager import manager
        await manager.broadcast(payload)
    except Exception as e:
        logger.error(f"WS broadcast error: {e}")
