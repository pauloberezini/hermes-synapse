import pytest
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from zoneinfo import ZoneInfo
from backend import scheduler

@pytest.fixture(autouse=True)
def clean_scheduler_state():
    try:
        for job in list(scheduler.scheduler.get_jobs()):
            try:
                job.remove()
            except Exception:
                pass
    except Exception:
        pass
    scheduler._timer_meta.clear()
    scheduler._fire_counts.clear()
    yield
    try:
        for job in list(scheduler.scheduler.get_jobs()):
            try:
                job.remove()
            except Exception:
                pass
    except Exception:
        pass
    scheduler._timer_meta.clear()
    scheduler._fire_counts.clear()

@pytest.mark.asyncio
async def test_add_and_get_timers():
    chat_id = "test_chat"
    label = "Test Timer"
    duration = 10
    
    timer_id = scheduler.add_timer(label, duration, chat_id)
    timers = scheduler.get_all_timers()
    
    assert len(timers) == 1
    assert timers[0]["id"] == timer_id
    assert timers[0]["label"] == label
    assert timers[0]["status"] == "running"

@pytest.mark.asyncio
async def test_cancel_timer():
    timer_id = scheduler.add_timer("To Cancel", 60, "123")
    timers = scheduler.get_all_timers()
    assert len(timers) == 1
    assert timers[0]["status"] == "running"
    
    cancelled = scheduler.cancel_timer_or_alarm(timer_id)
    assert cancelled is True
    
    timers_after = scheduler.get_all_timers()
    assert len(timers_after) == 0
    assert scheduler.cancel_timer_or_alarm("invalid_id") is False

@pytest.mark.asyncio
async def test_alarm_parsing():
    chat_id = "123"
    label = "Morning Alarm"
    
    tz = ZoneInfo("Asia/Jerusalem")
    now = datetime.now(tz)
    
    # 1. YYYY-MM-DD HH:MM:SS
    future_time = now + timedelta(hours=2)
    time_str = future_time.strftime("%Y-%m-%d %H:%M:%S")
    alarm_id1 = scheduler.add_alarm(time_str, label, chat_id)
    
    alarms = scheduler.get_all_timers()
    assert len(alarms) == 1
    assert alarms[0]["id"] == alarm_id1
    
    # 2. HH:MM (if in the future today)
    future_time_today = now + timedelta(minutes=30)
    time_str_today = future_time_today.strftime("%H:%M")
    alarm_id2 = scheduler.add_alarm(time_str_today, label, chat_id)
    
    alarms_after = scheduler.get_all_timers()
    assert len(alarms_after) == 2
    
    # 3. Invalid format
    with pytest.raises(ValueError):
        scheduler.add_alarm("invalid-time-format", label, chat_id)

@pytest.mark.asyncio
async def test_alarm_past_rollover():
    tz = ZoneInfo("Asia/Jerusalem")
    now = datetime.now(tz)
    
    past_time = now - timedelta(minutes=30)
    time_str = past_time.strftime("%H:%M")
    
    alarm_id = scheduler.add_alarm(time_str, "Past Alarm", "123")
    alarms = scheduler.get_all_timers()
    assert len(alarms) == 1
    assert alarms[0]["id"] == alarm_id

@pytest.mark.asyncio
async def test_cancel_alarm():
    tz = ZoneInfo("Asia/Jerusalem")
    future_time = datetime.now(tz) + timedelta(hours=1)
    time_str = future_time.strftime("%H:%M")
    
    alarm_id = scheduler.add_alarm(time_str, "To Cancel", "123")
    alarms = scheduler.get_all_timers()
    assert len(alarms) == 1
    
    cancelled = scheduler.cancel_timer_or_alarm(alarm_id)
    assert cancelled is True
    assert len(scheduler.get_all_timers()) == 0

@pytest.mark.asyncio
async def test_recurring_reminder():
    reminder_id = scheduler.add_recurring_reminder("Drink Water", 2.0, "123")
    reminders = scheduler.get_all_reminders()
    
    assert len(reminders) == 1
    assert reminders[0]["id"] == reminder_id
    assert reminders[0]["label"] == "Drink Water"
    
    cancelled = scheduler.cancel_recurring_reminder(reminder_id)
    assert cancelled is True
    assert len(scheduler.get_all_reminders()) == 0
    assert scheduler.cancel_recurring_reminder("invalid_id") is False

@pytest.mark.asyncio
async def test_error_handling():
    mock_app = MagicMock()
    mock_app.bot.send_message.side_effect = Exception("Bot crashed")
    
    with patch("backend.bot.telegram_app", mock_app), \
         patch("backend.websocket_manager.manager.broadcast", side_effect=Exception("WS crashed")):
         
        await scheduler._send_telegram_alert("123", "Hello")
        await scheduler._broadcast_ws({"msg": "hi"})
