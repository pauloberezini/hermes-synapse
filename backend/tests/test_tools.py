import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend import tools

def test_get_system_stats():
    res_str = tools.get_system_stats()
    stats = json.loads(res_str)
    
    assert "cpu_load_percent" in stats
    assert "ram_used_percent" in stats
    assert "ram_total_gb" in stats
    assert "disk_used_percent" in stats
    assert "disk_total_gb" in stats
    assert stats["status"] == "nominal"

@pytest.mark.asyncio
async def test_get_weather():
    # 1. Test fallback when no OWM API key configured
    with patch("backend.tools._env", return_value=None):
        res_str = tools.get_weather("Москва", days_ahead=0)
        data = json.loads(res_str)
        assert data["location"] == "Москва"
        assert data["temperature"] == "+20°C"
        assert data["status"] == "mock"

    # 2. Test when API key is present and OWM API responds successfully
    with patch("backend.tools._env", return_value="mock_key"), \
         patch("backend.tools._fetch_weather_owm") as mock_weather:
        mock_weather.return_value = {
            "name": "Москва",
            "main": {"temp": 25.0, "feels_like": 24.0, "humidity": 60},
            "weather": [{"description": "ясно"}],
            "wind": {"speed": 3.0}
        }
        res_str = tools.get_weather("Москва", days_ahead=0)
        data = json.loads(res_str)
        assert data["location"] == "Москва"
        assert data["temperature"] == "25.0°C"
        assert data["condition"] == "ясно"
        assert data["status"] == "real"

@patch("backend.scheduler.add_timer", return_value="timer-12345")
def test_execute_tool_set_timer(mock_add_timer):
    args = {"label": "Проверить бэкап", "duration_seconds": 15}
    res_str = tools.execute_tool("set_timer", args, chat_id="111222")
    
    mock_add_timer.assert_called_once_with("Проверить бэкап", 15, "111222")
    
    data = json.loads(res_str)
    assert data["status"] == "active"
    assert data["timer_id"] == "timer-12345"
    assert data["label"] == "Проверить бэкап"

def test_execute_tool_system_stats():
    res_str = tools.execute_tool("get_system_stats", {})
    data = json.loads(res_str)
    assert "cpu_load_percent" in data

def test_execute_tool_set_timer_max_limit():
    args = {"label": "Слишком длинный таймер", "duration_seconds": 5000}
    res_str = tools.execute_tool("set_timer", args, chat_id="111222")
    data = json.loads(res_str)
    assert data["status"] == "failed"
    assert "лимит" in data["error"]

@patch("backend.tools._get_calendar_service")
def test_google_calendar(mock_get_service):
    mock_service = MagicMock()
    mock_get_service.return_value = (mock_service, None)
    
    # 1. get_calendar_events
    mock_service.events().list().execute.return_value = {
        "items": [
            {"summary": "Meeting", "start": {"dateTime": "2026-07-03T12:00:00Z"}, "location": "Office", "htmlLink": "http://link", "description": "Desc"}
        ]
    }
    res = tools.get_calendar_events(days_ahead=7)
    data = json.loads(res)
    assert len(data["events"]) == 1
    assert data["events"][0]["title"] == "Meeting"
    
    # 2. add_calendar_event
    mock_service.events().insert().execute.return_value = {"id": "ev_123", "htmlLink": "http://link_new"}
    res_add = tools.add_calendar_event("New Meeting", "2026-07-03", "14:00")
    data_add = json.loads(res_add)
    assert data_add["status"] == "created"
    assert data_add["event_id"] == "ev_123"

@patch("backend.tools._env", return_value="test_token")
@patch("backend.tools._run_async")
def test_todoist(mock_run_async, mock_env):
    # 1. get_todoist_tasks
    mock_run_async.return_value = [
        {"id": "t1", "content": "Buy milk", "due": {"string": "today"}, "priority": 2, "url": "http://todoist/t1"}
    ]
    res = tools.get_todoist_tasks()
    data = json.loads(res)
    assert data["count"] == 1
    assert data["tasks"][0]["content"] == "Buy milk"
    
    # 2. add_todoist_task
    mock_run_async.return_value = {"id": "t2", "content": "Clean room", "due": {"string": "tomorrow"}, "url": "http://todoist/t2"}
    res_add = tools.add_todoist_task("Clean room", "tomorrow", 1)
    data_add = json.loads(res_add)
    assert data_add["status"] == "created"
    assert data_add["id"] == "t2"
    
    # 3. delete_todoist_task
    mock_run_async.return_value = True
    res_del = tools.delete_todoist_task("t2")
    data_del = json.loads(res_del)
    assert data_del["status"] == "deleted"

@patch("backend.rag.search_memory")
@patch("backend.obsidian.list_notes", AsyncMock(return_value=["note1.md"]))
@patch("backend.obsidian.read_note", AsyncMock(return_value="# Note Content"))
@patch("backend.obsidian.create_note", AsyncMock(return_value=True))
@patch("backend.obsidian.search_notes", AsyncMock(return_value=[{"filename": "note1.md", "excerpt": "excerpt content"}]))
def test_obsidian_tools(mock_search_memory):
    mock_search_memory.return_value = []
    # 1. search_obsidian
    res_search = tools.execute_tool("search_obsidian", {"query": "test"})
    assert "note1.md" in res_search
    
    # 2. read_obsidian_note
    res_read = tools.execute_tool("read_obsidian_note", {"note_path": "note1.md"})
    assert "# Note Content" in res_read
    
    # 3. create_obsidian_note
    res_create = tools.execute_tool("create_obsidian_note", {"title": "New", "content": "Body"})
    assert "создана в хранилище" in res_create

def test_execute_command():
    res = tools.execute_command("echo hello")
    assert "hello" in res
