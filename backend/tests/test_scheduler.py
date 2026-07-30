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
    try:
        from backend import database
        database._execute("DELETE FROM session_metadata WHERE session_id LIKE 'task_%'")
    except Exception:
        pass
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

@pytest.mark.asyncio
async def test_update_timer_and_trigger_now():
    timer_id = scheduler.add_timer("Initial Timer", 120, "123", prompt="Initial prompt")
    assert scheduler.update_timer(timer_id, "Updated Timer", "one-shot", duration_seconds=300, prompt="Updated prompt") is True
    
    timers = scheduler.get_all_timers()
    assert len(timers) == 1
    assert timers[0]["label"] == "Updated Timer"
    
    with patch("backend.scheduler._trigger_agent_task", new_callable=AsyncMock) as mock_trigger:
        triggered = scheduler.trigger_timer_now(timer_id)
        assert triggered is True
        assert mock_trigger.call_count == 1
        call_kwargs = mock_trigger.call_args.kwargs
        assert call_kwargs["agent_id"] == "jarvis"
        assert call_kwargs["prompt"] == "Updated prompt"
        assert call_kwargs["chat_id"] == "123"
        assert call_kwargs["task_session_id"] == f"task_{timer_id}"

    assert scheduler.update_timer("non_existent_id", "Label", "one-shot", duration_seconds=60) is False
    assert scheduler.trigger_timer_now("non_existent_id") is False


@pytest.mark.asyncio
async def test_pause_and_resume_timer():
    timer_id = scheduler.add_timer("Pausable Timer", 100, "123")
    timers = scheduler.get_all_timers()
    assert timers[0]["status"] == "running"
    
    # Pause
    assert scheduler.pause_timer(timer_id) is True
    timers_paused = scheduler.get_all_timers()
    assert timers_paused[0]["status"] == "paused"
    
    # Resume
    assert scheduler.resume_timer(timer_id) is True
    timers_resumed = scheduler.get_all_timers()
    assert timers_resumed[0]["status"] == "running"
    
    assert scheduler.pause_timer("invalid_id") is False
    assert scheduler.resume_timer("invalid_id") is False


@pytest.mark.asyncio
async def test_restart_timer():
    timer_id = scheduler.add_timer("Timer to Restart", 60, "123")
    assert scheduler.pause_timer(timer_id) is True
    
    # Restart should reset schedule and set status back to running
    assert scheduler.restart_timer(timer_id) is True
    timers = scheduler.get_all_timers()
    assert len(timers) == 1
    assert scheduler.restart_timer("invalid_id") is False


@pytest.mark.asyncio
async def test_restore_state_from_db_kwargs():
    timer_id = scheduler.add_timer("Persisted Task", 300, "chat123", agent_id="jarvis", prompt="Run diagnostic")
    # Simulate memory clear (server restart)
    scheduler._timer_meta.clear()
    assert len(scheduler._timer_meta) == 0

    scheduler.restore_state()
    timers = scheduler.get_all_timers()
    assert len(timers) == 1
    assert timers[0]["id"] == timer_id
    assert timers[0]["label"] == "Persisted Task"
    assert timers[0]["agent_id"] == "jarvis"
    assert timers[0]["prompt"] == "Run diagnostic"
    assert timers[0]["type"] == "one-shot"
    assert timers[0]["created_at"] != ""

@pytest.mark.asyncio
async def test_scheduled_session_creation_and_history():
    from backend import database
    timer_id = scheduler.add_timer("Check Weather", 60, "123", agent_id="jarvis", prompt="Check rain forecast")
    session_id = f"task_{timer_id}"
    
    # Verify title in session_metadata
    title = database.get_session_title(session_id)
    assert title is not None
    assert "Check Weather" in title

    # Test execution triggers using task_session_id
    with patch("backend.agent.agent_instance.respond", new_callable=AsyncMock) as mock_respond, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock) as mock_broadcast:
        mock_respond.return_value = "Rain is expected at 14:00."
        await scheduler._trigger_agent_task("jarvis", "Check rain forecast", "123", task_session_id=session_id, job_id=timer_id)
        
        mock_respond.assert_called_once_with("Check rain forecast", session_id=session_id, override_agent_id="jarvis")
        # Verify websocket broadcast sent with correct chat_id
        broadcast_calls = [call.args[0] for call in mock_broadcast.call_args_list]
        user_msgs = [c for c in broadcast_calls if c.get("type") == "chat_message" and c.get("role") == "user"]
        assert len(user_msgs) > 0
        assert user_msgs[0]["chat_id"] == session_id
