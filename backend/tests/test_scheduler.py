import pytest
import pytest_asyncio
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock
from zoneinfo import ZoneInfo
from backend import scheduler

@pytest_asyncio.fixture(autouse=True)
async def clean_scheduler_state():
    scheduler.ACTIVE_TIMERS = []
    scheduler.ACTIVE_REMINDERS = []
    scheduler.ACTIVE_ALARMS = []
    await scheduler.shutdown_scheduler_tasks()
    yield
    await scheduler.shutdown_scheduler_tasks()
    scheduler.ACTIVE_TIMERS = []
    scheduler.ACTIVE_REMINDERS = []
    scheduler.ACTIVE_ALARMS = []

@pytest.mark.asyncio
async def test_timer_lifecycle():
    chat_id = "test_chat"
    label = "Test Timer"
    duration = 10
    
    mock_bot = AsyncMock()
    mock_app = MagicMock()
    mock_app.bot = mock_bot
    mock_ws = AsyncMock()
    
    original_sleep = asyncio.sleep
    async def mock_sleep_fn(delay):
        if delay > 0.1:
            return
        await original_sleep(delay)
    
    with patch("backend.bot.telegram_app", mock_app), \
         patch("backend.websocket_manager.manager.broadcast", mock_ws), \
         patch("asyncio.sleep", side_effect=mock_sleep_fn):
         
        timer_id = scheduler.add_timer(label, duration, chat_id)
        
        # Verify it was added
        timers = scheduler.get_all_timers()
        assert len(timers) == 1
        assert timers[0]["id"] == timer_id
        assert timers[0]["label"] == label
        assert timers[0]["status"] == "running"
        assert timers[0]["time_left"] > 0
        
        # Allow the task to run (since sleep is mocked it runs instantly)
        await original_sleep(0.01)
        
        # Verify it completed
        timers = scheduler.get_all_timers()
        assert timers[0]["status"] == "completed"
        assert timers[0]["time_left"] == 0
        mock_bot.send_message.assert_called_once()
        assert "Test Timer" in mock_bot.send_message.call_args[1]["text"]

@pytest.mark.asyncio
async def test_cancel_timer():
    timer_id = scheduler.add_timer("To Cancel", 60, "123")
    assert len(scheduler.ACTIVE_TIMERS) == 1
    assert scheduler.ACTIVE_TIMERS[0].status == "running"
    
    cancelled = scheduler.cancel_timer_or_alarm(timer_id)
    assert cancelled is True
    assert scheduler.ACTIVE_TIMERS[0].status == "cancelled"
    
    # Try cancelling again or cancelling a non-existent ID
    assert scheduler.cancel_timer_or_alarm("invalid_id") is False

@pytest.mark.asyncio
async def test_alarm_parsing():
    chat_id = "123"
    label = "Morning Alarm"
    
    # Test valid formats
    tz = ZoneInfo("Asia/Jerusalem")
    now = datetime.now(tz)
    
    # 1. YYYY-MM-DD HH:MM:SS
    future_time = now + timedelta(hours=2)
    time_str = future_time.strftime("%Y-%m-%d %H:%M:%S")
    alarm_id1 = scheduler.add_alarm(time_str, label, chat_id)
    assert len(scheduler.ACTIVE_ALARMS) == 1
    assert scheduler.ACTIVE_ALARMS[0].id == alarm_id1
    
    # 2. HH:MM (if in the future today)
    future_time_today = now + timedelta(minutes=30)
    time_str_today = future_time_today.strftime("%H:%M")
    alarm_id2 = scheduler.add_alarm(time_str_today, label, chat_id)
    assert len(scheduler.ACTIVE_ALARMS) == 2
    
    # 3. Invalid format
    with pytest.raises(ValueError):
        scheduler.add_alarm("invalid-time-format", label, chat_id)

@pytest.mark.asyncio
async def test_alarm_past_rollover():
    # If the time is set in HH:MM format and it is in the past, it should add 1 day.
    tz = ZoneInfo("Asia/Jerusalem")
    now = datetime.now(tz)
    
    past_time = now - timedelta(minutes=30)
    time_str = past_time.strftime("%H:%M")
    
    scheduler.add_alarm(time_str, "Past Alarm", "123")
    alarm = scheduler.ACTIVE_ALARMS[0]
    
    # Target timestamp should be approximately 23.5 hours in the future
    time_diff = alarm.target_time - time.time()
    assert 23 * 3600 < time_diff < 24 * 3600

@pytest.mark.asyncio
async def test_alarm_execution():
    mock_bot = AsyncMock()
    mock_app = MagicMock()
    mock_app.bot = mock_bot
    mock_ws = AsyncMock()
    
    original_sleep = asyncio.sleep
    async def mock_sleep_fn(delay):
        if delay > 0.1:
            return
        await original_sleep(delay)
        
    with patch("backend.bot.telegram_app", mock_app), \
         patch("backend.websocket_manager.manager.broadcast", mock_ws), \
         patch("asyncio.sleep", side_effect=mock_sleep_fn):
         
        # Set alarm 5 seconds in the future
        tz = ZoneInfo("Asia/Jerusalem")
        future_dt = datetime.fromtimestamp(time.time() + 5, tz)
        time_str = future_dt.strftime("%Y-%m-%d %H:%M:%S")
        
        scheduler.add_alarm(time_str, "Test Alarm", "123")
        
        # Yield to event loop to run background task
        await original_sleep(0.01)
        
        alarms = scheduler.get_all_timers()
        alarms = [a for a in alarms if a["type"] == "alarm"]
        assert len(alarms) == 1
        assert alarms[0]["status"] == "completed"
        mock_bot.send_message.assert_called_once()
        assert "Test Alarm" in mock_bot.send_message.call_args[1]["text"]

@pytest.mark.asyncio
async def test_cancel_alarm():
    tz = ZoneInfo("Asia/Jerusalem")
    future_time = datetime.now(tz) + timedelta(hours=1)
    time_str = future_time.strftime("%H:%M")
    
    alarm_id = scheduler.add_alarm(time_str, "To Cancel", "123")
    assert len(scheduler.ACTIVE_ALARMS) == 1
    assert scheduler.ACTIVE_ALARMS[0].status == "running"
    
    cancelled = scheduler.cancel_timer_or_alarm(alarm_id)
    assert cancelled is True
    assert scheduler.ACTIVE_ALARMS[0].status == "cancelled"

@pytest.mark.asyncio
async def test_recurring_reminder_execution():
    mock_bot = AsyncMock()
    mock_app = MagicMock()
    mock_app.bot = mock_bot
    mock_ws = AsyncMock()
    
    loop_count = 0
    reminder_id = None
    
    original_sleep = asyncio.sleep
    async def mock_sleep_fn(delay):
        nonlocal loop_count
        if delay > 0.1:
            loop_count += 1
            if loop_count >= 2:
                # Cancel the reminder to exit the while loop
                scheduler.cancel_recurring_reminder(reminder_id)
            return
        await original_sleep(delay)
        
    with patch("backend.bot.telegram_app", mock_app), \
         patch("backend.websocket_manager.manager.broadcast", mock_ws), \
         patch("asyncio.sleep", side_effect=mock_sleep_fn):
         
        # Add reminder every 2 hours
        reminder_id = scheduler.add_recurring_reminder("Drink Water", 2.0, "123")
        
        # Yield to event loop
        await original_sleep(0.01)
        
        assert len(scheduler.ACTIVE_REMINDERS) == 1
        assert scheduler.ACTIVE_REMINDERS[0].fire_count == 1
        assert scheduler.ACTIVE_REMINDERS[0].status == "cancelled"
        
        mock_bot.send_message.assert_called_once()
        assert "Drink Water" in mock_bot.send_message.call_args[1]["text"]
        assert "Repeat every: 2 h" in mock_bot.send_message.call_args[1]["text"]

@pytest.mark.asyncio
async def test_cancel_recurring_reminder():
    reminder_id = scheduler.add_recurring_reminder("To Cancel", 1.0, "123")
    assert len(scheduler.ACTIVE_REMINDERS) == 1
    assert scheduler.ACTIVE_REMINDERS[0].status == "running"
    
    cancelled = scheduler.cancel_recurring_reminder(reminder_id)
    assert cancelled is True
    assert scheduler.ACTIVE_REMINDERS[0].status == "cancelled"
    
    # Try cancelling again
    assert scheduler.cancel_recurring_reminder(reminder_id) is False

@pytest.mark.asyncio
async def test_get_all_timers_cutoff():
    t1 = scheduler.TimerTask("t1", "Running", 60, "123")
    t1.status = "running"
    t1.start_time = time.time()
    
    t2 = scheduler.TimerTask("t2", "Completed recent", 60, "123")
    t2.status = "completed"
    t2.start_time = time.time() - 100
    
    t3 = scheduler.TimerTask("t3", "Completed old", 60, "123")
    t3.status = "completed"
    t3.start_time = time.time() - 400
    
    scheduler.ACTIVE_TIMERS = [t1, t2, t3]
    
    timers = scheduler.get_all_timers()
    assert len(timers) == 2
    ids = [t["id"] for t in timers]
    assert "t1" in ids
    assert "t2" in ids
    assert "t3" not in ids

@pytest.mark.asyncio
async def test_error_handling():
    mock_app = MagicMock()
    mock_app.bot.send_message.side_effect = Exception("Bot crashed")
    
    with patch("backend.bot.telegram_app", mock_app), \
         patch("backend.websocket_manager.manager.broadcast", side_effect=Exception("WS crashed")):
         
        await scheduler._send_telegram_alert("123", "Hello")
        await scheduler._broadcast_ws({"msg": "hi"})
