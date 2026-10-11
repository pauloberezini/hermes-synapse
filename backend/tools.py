import os
import re
import json
import logging
import asyncio
import httpx
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

import contextvars

logger = logging.getLogger("hermes.tools")

# ContextVar and Threading-local context for passing parent_message_id to call_subagent across threads
_parent_msg_cvar: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar("parent_message_id", default=None)

class _CallContextProxy:
    def __init__(self):
        self._local = threading.local()

    @property
    def parent_message_id(self) -> Optional[str]:
        val = getattr(self._local, "parent_message_id", None)
        if val is not None:
            return val
        return _parent_msg_cvar.get(None)

    @parent_message_id.setter
    def parent_message_id(self, val: Optional[str]):
        self._local.parent_message_id = val
        _parent_msg_cvar.set(val)

_call_context = _CallContextProxy()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _env(key: str) -> Optional[str]:
    """Read env var; return None if missing or empty placeholder."""
    val = os.getenv(key, "").strip()
    return val if val and not val.startswith("your_") else None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SYSTEM STATS
# ═══════════════════════════════════════════════════════════════════════════════

def get_system_stats() -> str:
    """Reads system stats from Linux proc files and os metrics."""
    try:
        stat = os.statvfs('/')
        free_bytes  = stat.f_bavail * stat.f_frsize
        total_bytes = stat.f_blocks * stat.f_frsize
        used_bytes  = total_bytes - free_bytes
        disk_pct    = int((used_bytes / total_bytes) * 100) if total_bytes > 0 else 0
        total_gb    = round(total_bytes / (1024**3), 1)
        used_gb     = round(used_bytes  / (1024**3), 1)

        mem_total_gb, mem_used_pct = 8.0, 45
        if os.path.exists('/proc/meminfo'):
            with open('/proc/meminfo') as f:
                mem_info = {}
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        mem_info[parts[0].strip()] = int(parts[1].split()[0])
            if 'MemTotal' in mem_info:
                total_kb = mem_info['MemTotal']
                free_kb  = mem_info.get('MemAvailable', mem_info.get('MemFree', 0))
                mem_used_pct = int(((total_kb - free_kb) / total_kb) * 100)
                mem_total_gb = round(total_kb / (1024**2), 1)

        cpu_load = 5
        try:
            import psutil
            cpu_load = int(psutil.cpu_percent(interval=0.1))
        except Exception:
            pass

        return json.dumps({
            "cpu_load_percent":  cpu_load,
            "ram_used_percent":  mem_used_pct,
            "ram_total_gb":      mem_total_gb,
            "disk_used_percent": disk_pct,
            "disk_total_gb":     total_gb,
            "disk_used_gb":      used_gb,
            "status": "nominal"
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error reading system stats: {e}")
        return json.dumps({"error": str(e), "status": "malfunction"})


# ═══════════════════════════════════════════════════════════════════════════════
# 2. WEATHER — OpenWeatherMap (real) with mock fallback
# ═══════════════════════════════════════════════════════════════════════════════

async def _fetch_weather_owm(location: str) -> Optional[Dict]:
    """Call OpenWeatherMap API. Returns parsed dict or None on failure."""
    api_key = _env("OPENWEATHERMAP_API_KEY")
    if not api_key:
        return None
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": location, "appid": api_key, "units": "metric", "lang": "ru"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                return r.json()
            logger.warning(f"OWM returned {r.status_code} for '{location}'")
    except Exception as e:
        logger.warning(f"OWM request failed: {e}")
    return None

async def _fetch_weather_forecast_owm(location: str) -> Optional[Dict]:
    """Call OpenWeatherMap 5-day / 3-hour forecast API. Returns parsed dict or None on failure."""
    api_key = _env("OPENWEATHERMAP_API_KEY")
    if not api_key:
        return None
    url = "https://api.openweathermap.org/data/2.5/forecast"
    params = {"q": location, "appid": api_key, "units": "metric", "lang": "ru"}
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            r = await client.get(url, params=params)
            if r.status_code == 200:
                return r.json()
            logger.warning(f"OWM Forecast returned {r.status_code} for '{location}'")
    except Exception as e:
        logger.warning(f"OWM Forecast request failed: {e}")
    return None

def get_weather(location: str, days_ahead: int = 0) -> str:
    """Weather tool — returns current weather (days_ahead=0) or forecast for days_ahead (1-4)."""
    api_key = _env("OPENWEATHERMAP_API_KEY")
    if not api_key:
        # Mock forecast fallback
        city = location.strip()
        temp = "+18°C" if days_ahead == 1 else "+20°C"
        return json.dumps({
            "location":    city,
            "temperature": temp,
            "condition":   "partly cloudy (forecast)",
            "days_ahead":  days_ahead,
            "source":      "mock - add OPENWEATHERMAP_API_KEY to .env for real data",
            "status":      "mock"
        }, ensure_ascii=False)

    if days_ahead == 0:
        # Run async OWM call from sync context
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _fetch_weather_owm(location))
                    data = future.result(timeout=10)
            else:
                data = loop.run_until_complete(_fetch_weather_owm(location))
        except Exception as e:
            data = None
            logger.error(f"Weather fetch error: {e}")

        if not data:
            return json.dumps({"error": f"Failed to get weather for '{location}'."})

        main    = data.get("main", {})
        weather = data.get("weather", [{}])[0]
        wind    = data.get("wind", {})
        return json.dumps({
            "location":    data.get("name", location),
            "temperature": f"{main.get('temp', '?'):.1f}°C" if main.get('temp') is not None else "no data",
            "feels_like":  f"{main.get('feels_like', '?'):.1f}°C" if main.get('feels_like') is not None else "no data",
            "condition":   weather.get("description", "unknown"),
            "humidity":    f"{main.get('humidity', '?')}%" if main.get('humidity') is not None else "no data",
            "wind_speed":  f"{wind.get('speed', '?')} m/s" if wind.get('speed') is not None else "no data",
            "source":      "OpenWeatherMap",
            "status":      "real"
        }, ensure_ascii=False)
    else:
        # Fetch 5-day forecast
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _fetch_weather_forecast_owm(location))
                    data = future.result(timeout=10)
            else:
                data = loop.run_until_complete(_fetch_weather_forecast_owm(location))
        except Exception as e:
            data = None
            logger.error(f"Weather forecast fetch error: {e}")

        if not data:
            return json.dumps({"error": f"Failed to get weather forecast for '{location}'."})

        import datetime
        target_date = (datetime.date.today() + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        
        forecast_list = data.get("list", [])
        day_forecasts = [item for item in forecast_list if item.get("dt_txt", "").startswith(target_date)]
        
        if not day_forecasts:
            return json.dumps({"error": f"Forecast for '{location}' on {target_date} was not found."})
            
        midday = [item for item in day_forecasts if "12:00:00" in item.get("dt_txt", "") or "15:00:00" in item.get("dt_txt", "")]
        selected = midday[0] if midday else day_forecasts[len(day_forecasts) // 2]
        
        main = selected.get("main", {})
        weather = selected.get("weather", [{}])[0]
        wind = selected.get("wind", {})
        
        return json.dumps({
            "location":    data.get("city", {}).get("name", location),
            "date":        target_date,
            "days_ahead":  days_ahead,
            "temperature": f"{main.get('temp', '?'):.1f}°C" if main.get('temp') is not None else "no data",
            "feels_like":  f"{main.get('feels_like', '?'):.1f}°C" if main.get('feels_like') is not None else "no data",
            "condition":   weather.get("description", "unknown"),
            "humidity":    f"{main.get('humidity', '?')}%" if main.get('humidity') is not None else "no data",
            "wind_speed":  f"{wind.get('speed', '?')} m/s" if wind.get('speed') is not None else "no data",
            "source":      "OpenWeatherMap Forecast",
            "status":      "real"
        }, ensure_ascii=False)


def get_current_time_israel() -> str:
    """Returns the current date, time and day of the week in Israel (Asia/Jerusalem)."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Jerusalem"))
        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        day_of_week = day_names[now.weekday()]
        return json.dumps({
            "israel_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M:%S"),
            "day_of_week": day_of_week,
            "timezone": "Asia/Jerusalem"
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error getting Israel time: {e}")
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════════
# 3. TIMERS
# ═══════════════════════════════════════════════════════════════════════════════

def set_timer(label: str, duration_seconds: int, chat_id: str, agent_id: Optional[str] = None, prompt: Optional[str] = None) -> str:
    """Creates a countdown timer that fires a Telegram alert on completion."""
    if duration_seconds > 3600:
        return json.dumps({
            "status": "failed",
            "error": "Limit exceeded. A timer cannot be set for more than 1 hour (3600 seconds)."
        }, ensure_ascii=False)
    try:
        from backend.scheduler import add_timer
        if agent_id or prompt:
            timer_id = add_timer(label, duration_seconds, chat_id, agent_id, prompt)
        else:
            timer_id = add_timer(label, duration_seconds, chat_id)
        return json.dumps({
            "status":           "active",
            "timer_id":         timer_id,
            "label":            label,
            "duration_seconds": duration_seconds,
            "message":          f"Timer '{label}' set for {duration_seconds} seconds."
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error setting timer: {e}")
        return json.dumps({"status": "failed", "error": str(e)})


def set_alarm(time_str: str, label: str, chat_id: str, agent_id: Optional[str] = None, prompt: Optional[str] = None) -> str:
    """Creates an alarm clock scheduled for a specific time/date (Israel local time) with Telegram notification."""
    try:
        from backend.scheduler import add_alarm
        if agent_id or prompt:
            alarm_id = add_alarm(time_str, label, chat_id, agent_id, prompt)
        else:
            alarm_id = add_alarm(time_str, label, chat_id)
        return json.dumps({
            "status":      "active",
            "alarm_id":    alarm_id,
            "label":       label,
            "time_str":    time_str,
            "message":     f"Alarm '{label}' set for {time_str}."
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error setting alarm: {e}")
        return json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False)


def cancel_timer_or_alarm(id: str) -> str:
    """Cancels a running countdown timer or alarm clock by its ID."""
    try:
        from backend.scheduler import cancel_timer_or_alarm as scheduler_cancel
        ok = scheduler_cancel(id)
        if ok:
            return json.dumps({
                "status":  "cancelled",
                "id":      id,
                "message": f"Timer or alarm with ID '{id}' successfully cancelled."
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "status":  "not_found",
                "id":      id,
                "message": f"No active timer or alarm with ID '{id}' was found."
            }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error cancelling timer/alarm: {e}")
        return json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RECURRING REMINDERS
# ═══════════════════════════════════════════════════════════════════════════════

def set_recurring_reminder(label: str, interval_hours: float, chat_id: str, agent_id: Optional[str] = None, prompt: Optional[str] = None) -> str:
    """Creates a recurring reminder that fires every N hours via Telegram."""
    try:
        from backend.scheduler import add_recurring_reminder
        if agent_id or prompt:
            reminder_id = add_recurring_reminder(label, interval_hours, chat_id, agent_id, prompt)
        else:
            reminder_id = add_recurring_reminder(label, interval_hours, chat_id)
        return json.dumps({
            "status":         "active",
            "reminder_id":    reminder_id,
            "label":          label,
            "interval_hours": interval_hours,
            "message":        f"Recurring reminder '{label}' set for every {interval_hours}h."
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error setting recurring reminder: {e}")
        return json.dumps({"status": "failed", "error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════════
# 5. GOOGLE CALENDAR
# ═══════════════════════════════════════════════════════════════════════════════

def _get_calendar_service():
    """Build an authorized Google Calendar API service object."""
    token_path = os.path.join(os.path.dirname(__file__), "data", "google_token.json")
    creds_path = os.getenv("GOOGLE_CLIENT_SECRET_PATH", os.path.join(os.path.dirname(__file__), "data", "google_credentials.json"))

    if not os.path.exists(creds_path):
        return None, "google_credentials.json was not found. Run python backend/google_auth.py or set GOOGLE_CLIENT_SECRET_PATH"
    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        SCOPES = ["https://www.googleapis.com/auth/calendar"]
        creds = None

        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, "w") as f:
                    f.write(creds.to_json())
            else:
                return None, "Google token was not found. Run python backend/google_auth.py on your machine."

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return service, None
    except ImportError:
        return None, "Install google-auth-oauthlib and google-api-python-client"
    except Exception as e:
        return None, str(e)


def get_calendar_events(days_ahead: int = 7) -> str:
    """List upcoming Google Calendar events for the next N days.
    
    days_ahead=0  → events for today only (Israel local date)
    days_ahead=1  → events tomorrow (Israel local date)
    days_ahead=7  → events in the next 7 days (default)
    
    NOTE: uses Asia/Jerusalem timezone so midnight is correct even when
    Docker runs in UTC and local time is past midnight.
    """
    service, err = _get_calendar_service()
    if err:
        return json.dumps({"error": err, "hint": "Run python backend/google_auth.py for authorization"})
    try:
        from zoneinfo import ZoneInfo
        LOCAL_TZ = ZoneInfo("Asia/Jerusalem")

        # Compute today's local date in Israel time (not UTC!)
        now_local = datetime.now(LOCAL_TZ)
        today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)

        if days_ahead == 0:
            # Exactly today: [start of local today, start of local tomorrow)
            range_start = today_local
            range_end   = today_local + timedelta(days=1)
            period_label = "today"
        else:
            range_start = today_local
            range_end   = today_local + timedelta(days=days_ahead + 1)
            period_label = f"next {days_ahead} days"

        # Convert to UTC for the Google Calendar API
        today_start = range_start.astimezone(timezone.utc)
        end         = range_end.astimezone(timezone.utc)

        events_result = service.events().list(
            calendarId="primary",
            timeMin=today_start.isoformat(),
            timeMax=end.isoformat(),
            maxResults=20,
            singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
        if not events:
            return json.dumps({"events": [], "message": f"No events on {period_label}."})

        result = []
        for e in events:
            start_info = e.get("start", {})
            start = start_info.get("dateTime", start_info.get("date", ""))
            is_all_day = "date" in start_info and "dateTime" not in start_info
            result.append({
                "title":      e.get("summary", "(untitled)"),
                "start":      start,
                "all_day":    is_all_day,
                "location":   e.get("location", ""),
                "link":       e.get("htmlLink", ""),
                "description": e.get("description", ""),
            })
        return json.dumps({"events": result, "count": len(result)}, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Calendar get events error: {e}")
        return json.dumps({"error": str(e)})


def add_calendar_event(title: str, date: str, time: str = "10:00",
                       duration_minutes: Optional[int] = None,
                       end_time: Optional[str] = None,
                       description: str = "") -> str:
    """Add an event to Google Calendar. date format: YYYY-MM-DD, time: HH:MM."""
    service, err = _get_calendar_service()
    if err:
        return json.dumps({"error": err})
    try:
        # Build start/end datetimes
        from zoneinfo import ZoneInfo
        LOCAL_TZ = ZoneInfo("Asia/Jerusalem")
        start_dt = datetime.strptime(f"{date} {time}", "%Y-%m-%d %H:%M").replace(tzinfo=LOCAL_TZ)
        
        if end_time:
            end_dt = datetime.strptime(f"{date} {end_time}", "%Y-%m-%d %H:%M").replace(tzinfo=LOCAL_TZ)
            if end_dt <= start_dt:
                end_dt += timedelta(days=1)
        else:
            dur = duration_minutes if duration_minutes is not None else 60
            end_dt = start_dt + timedelta(minutes=dur)

        event = {
            "summary":     title,
            "description": description,
            "start":       {"dateTime": start_dt.isoformat()},
            "end":         {"dateTime": end_dt.isoformat()},
        }
        created = service.events().insert(calendarId="primary", body=event).execute()
        return json.dumps({
            "status":   "created",
            "title":    title,
            "start":    start_dt.isoformat(),
            "end":      end_dt.isoformat(),
            "link":     created.get("htmlLink", ""),
            "event_id": created.get("id", ""),
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Calendar add event error: {e}")
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════════════════════════════════════════
# 6. TODOIST
# ═══════════════════════════════════════════════════════════════════════════════

async def _todoist_get(endpoint: str, token: str, params: Dict = None) -> Optional[Any]:
    url = f"https://api.todoist.com/api/v1/{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(url, headers=headers, params=params or {})
            if r.status_code != 200:
                logger.warning(f"Todoist GET {endpoint} -> {r.status_code}: {r.text[:100]}")
                return None
            data = r.json()
            # v1 returns paginated {results: [...]} or plain list
            return data.get("results", data) if isinstance(data, dict) else data
    except Exception as e:
        logger.warning(f"Todoist GET {endpoint} error: {e}")
        return None

async def _todoist_post(endpoint: str, token: str, payload: Dict) -> Optional[Dict]:
    url = f"https://api.todoist.com/api/v1/{endpoint}"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.post(url, headers=headers, json=payload)
            return r.json() if r.status_code in (200, 204) else None
    except Exception as e:
        logger.warning(f"Todoist POST {endpoint} error: {e}")
        return None

def _run_async(coro_or_factory):
    """Run async coro or coroutine factory from a sync context safely."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            def _runner():
                coro = coro_or_factory() if callable(coro_or_factory) else coro_or_factory
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(coro)
                finally:
                    try:
                        pending = asyncio.all_tasks(new_loop)
                        for task in pending:
                            task.cancel()
                        if pending:
                            new_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                        new_loop.run_until_complete(new_loop.shutdown_asyncgens())
                    except Exception:
                        pass
                    new_loop.close()

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(_runner).result(timeout=15)

        try:
            cur_loop = asyncio.get_event_loop()
        except RuntimeError:
            cur_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(cur_loop)

        coro = coro_or_factory() if callable(coro_or_factory) else coro_or_factory
        return cur_loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"_run_async error: {e}")
        if hasattr(coro_or_factory, "close"):
            try:
                coro_or_factory.close()
            except Exception:
                pass
        return None


def get_todoist_tasks(filter_str: str = "today | overdue") -> str:
    """List Todoist tasks. Default filter: today + overdue."""
    token = _env("TODOIST_API_TOKEN")
    if not token:
        return json.dumps({
            "error": "TODOIST_API_TOKEN is not set in .env",
            "hint":  "Get a token at https://app.todoist.com/app/settings/integrations/developer"
        })
    # Todoist v1 uses query param 'filter' for task filtering
    params = {"filter": filter_str} if filter_str else {}
    data = _run_async(lambda: _todoist_get("tasks", token, params))
    if data is None:
        return json.dumps({"error": "Failed to fetch tasks from Todoist"})
    tasks = [
        {
            "id":       t.get("id"),
            "content":  t.get("content"),
            "due":      t.get("due", {}).get("string", "") if t.get("due") else "",
            "priority": t.get("priority", 1),
            "url":      t.get("url", ""),
        }
        for t in (data if isinstance(data, list) else [])
    ]
    return json.dumps({
        "tasks": tasks,
        "count": len(tasks),
        "filter": filter_str,
    }, ensure_ascii=False)

def add_todoist_task(content: str, due_string: str = "", priority: int = 1) -> str:
    """Add a task to Todoist. due_string examples: 'today', 'tomorrow', 'next Monday'."""
    token = _env("TODOIST_API_TOKEN")
    if not token:
        return json.dumps({
            "error": "TODOIST_API_TOKEN is not set in .env",
            "hint":  "Get a token at https://app.todoist.com/app/settings/integrations/developer"
        })
    payload: Dict[str, Any] = {"content": content, "priority": priority}
    if due_string:
        payload["due_string"] = due_string
        payload["due_lang"]   = "ru"

    result = _run_async(lambda: _todoist_post("tasks", token, payload))
    if result is None:
        return json.dumps({"error": "Failed to create a Todoist task"})
    return json.dumps({
        "status":  "created",
        "id":      result.get("id"),
        "content": result.get("content"),
        "due":     result.get("due", {}).get("string", "") if result.get("due") else "",
        "url":     result.get("url", ""),
    }, ensure_ascii=False)


async def _todoist_delete(endpoint: str, token: str) -> bool:
    url = f"https://api.todoist.com/api/v1/{endpoint}"
    headers = {"Authorization": f"Bearer {token}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.delete(url, headers=headers)
            if r.status_code in (200, 204):
                return True
            logger.warning(f"Todoist DELETE {endpoint} -> {r.status_code}: {r.text[:100]}")
            return False
    except Exception as e:
        logger.warning(f"Todoist DELETE {endpoint} error: {e}")
        return False


def delete_todoist_task(task_id: str) -> str:
    """Delete a task from Todoist by its ID."""
    token = _env("TODOIST_API_TOKEN")
    if not token:
        return json.dumps({
            "error": "TODOIST_API_TOKEN is not set in .env",
            "hint":  "Get a token at https://app.todoist.com/app/settings/integrations/developer"
        })
    success = _run_async(lambda: _todoist_delete(f"tasks/{task_id}", token))
    if not success:
        return json.dumps({"error": f"Failed to delete Todoist task {task_id}"})
    return json.dumps({
        "status": "deleted",
        "id": task_id
    }, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOLS SCHEMA (OpenAI function-calling format)
# ═══════════════════════════════════════════════════════════════════════════════

TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_system_stats",
            "description": "Returns server telemetry: CPU load, RAM, and disk space.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Returns the current weather or a forecast for a city.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "City name, for example: London, Ashkelon, Tokyo"},
                    "days_ahead": {"type": "integer", "description": "Days ahead: 0 for current weather (default), 1 for tomorrow, 2 for the day after, up to 4"}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time_israel",
            "description": "Returns the current date, time, and weekday in Israel (Asia/Jerusalem).",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_timer",
            "description": "Sets a countdown timer with a Telegram notification. Maximum duration is 1 hour (3600 seconds). Several timers can run at once.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label":            {"type": "string",  "description": "Event label, for example: standup, check the oven"},
                    "duration_seconds": {"type": "integer", "description": "Duration in seconds (3600 max)"}
                },
                "required": ["label", "duration_seconds"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "Sets an alarm for a time (for example '08:30', '21:00', or '2026-05-30 07:00'). If that time has already passed today, the alarm is set for tomorrow.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_str": {"type": "string", "description": "Trigger time as HH:MM (24-hour) or YYYY-MM-DD HH:MM"},
                    "label":    {"type": "string", "description": "Alarm label (for example: 'wake up', 'meeting')"}
                },
                "required": ["time_str", "label"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_timer_or_alarm",
            "description": "Cancels an active timer or alarm by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Timer or alarm ID"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_recurring_reminder",
            "description": "Creates a recurring reminder that fires every N hours via Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label":          {"type": "string", "description": "Reminder text"},
                    "interval_hours": {"type": "number", "description": "Repeat interval in hours, for example 24 for daily"}
                },
                "required": ["label", "interval_hours"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Lists upcoming Google Calendar events. Use days_ahead=0 for today, 1 for tomorrow. Default is 7 days.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "description": "How many days ahead: 0 = today only (including all-day events), 1 = tomorrow, 7 = a week (default)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_calendar_event",
            "description": "Adds an event to Google Calendar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":            {"type": "string",  "description": "Event title"},
                    "date":             {"type": "string",  "description": "Date as YYYY-MM-DD"},
                    "time":             {"type": "string",  "description": "Time as HH:MM (default 10:00)"},
                    "end_time":         {"type": "string",  "description": "End time as HH:MM (optional)"},
                    "duration_minutes": {"type": "integer", "description": "Duration in minutes (default 60, ignored when end_time is set)"},
                    "description":      {"type": "string",  "description": "Event description (optional)"}
                },
                "required": ["title", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_todoist_tasks",
            "description": "Lists Todoist tasks. Defaults to today and overdue.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_str": {"type": "string", "description": "Todoist filter, for example: 'today', 'overdue', 'p1'"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_todoist_task",
            "description": "Adds a Todoist task.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content":    {"type": "string",  "description": "Task text"},
                    "due_string": {"type": "string",  "description": "Due string, for example: today, tomorrow, next friday"},
                    "priority":   {"type": "integer", "description": "Priority: 1 (normal) through 4 (urgent)"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_todoist_task",
            "description": "Deletes a Todoist task by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Todoist task ID"}
                },
                "required": ["task_id"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Searches the web and returns recent news, articles, or facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "perform_search",
            "description": "Perform real-time web search for latest news, facts, inflation/interest rate reports, or financial events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Search the internet for current events, news, or macroeconomic reports.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_price_alert",
            "description": "Sets a price alert for a crypto asset (btc, eth, ton) or a stock (AAPL, TSLA).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Asset symbol, for example: TON, BTC, AAPL, TSLA"},
                    "target_price": {"type": "number", "description": "Target price in USD"},
                    "condition": {"type": "string", "description": "Trigger: 'above' or 'below' the target price"}
                },
                "required": ["symbol", "target_price", "condition"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_prices",
            "description": "Returns live prices for crypto assets or stocks.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {"type": "string", "description": "Comma-separated symbols, for example: 'TON, BTC, TSLA'"}
                },
                "required": ["symbols"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_github_summary",
            "description": "Fetches a GitHub repo summary: open pull requests, issues, or releases.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string", "description": "Repository as owner/repo. Defaults to the local .git/config remote"},
                    "request_type": {"type": "string", "description": "Request type: 'prs', 'issues', 'releases', or 'all'"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_rss_digest",
            "description": "Fetches the latest items from an RSS source such as Habr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "feed_source": {"type": "string", "description": "News source: 'habr', 'techcrunch', 'hackernews', 'rbc', 'lenta'"},
                    "limit": {"type": "integer", "description": "Number of items (default 5)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_rss_node_feed",
            "description": "Reads items from configured RSS nodes. If node_id is omitted, returns the latest items from every active node.",
            "parameters": {
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "RSS node id (optional, for example 'rss_node_123' or 'all')"},
                    "limit": {"type": "integer", "description": "Maximum number of items to return (optional)"}
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_subagent",
            "description": "Creates or updates a specialized subagent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subagent_id": {"type": "string", "description": "Latin slug, for example: 'sports_betting', 'french_tutor'"},
                    "name": {"type": "string", "description": "Display name, for example: 'Sports analyst'"},
                    "system_prompt": {"type": "string", "description": "System prompt: persona, tone, and rules for the subagent."},
                    "model": {"type": "string", "description": "Model for the subagent. Defaults to LLM_MODEL."},
                    "parent_id": {"type": "string", "description": "Orchestrator id to attach the agent under."},
                    "skills": {"type": "string", "description": "Comma-separated skill ids. Capped to the parent's skills."}
                },
                "required": ["subagent_id", "name", "system_prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_subagent",
            "description": "Sends a task to a subagent by id and returns its reply.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subagent_id": {"type": "string", "description": "Subagent id, for example: 'sports_betting'"},
                    "query": {"type": "string", "description": "Task or question for the subagent"}
                },
                "required": ["subagent_id", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_subagents",
            "description": "Lists every registered subagent.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_subagent_memory",
            "description": "Saves or updates a key-value fact in the current subagent's long-term memory (database and RAG).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Fact key, for example: 'vocabulary', 'user_grammar_level', 'common_mistakes', 'lessons_progress'"},
                    "value": {"type": "string", "description": "Fact value, for example a word list, mistakes, or the user's level."}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_subagent_memory",
            "description": "Loads saved facts for the current subagent. Omit the key to return all of them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Fact key to load (optional)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Runs a shell command locally and returns stdout/stderr.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command, for example: 'curl -s https://api.linear.app/...' or 'python -c ...'"}
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_obsidian",
            "description": (
                "Semantic search over Obsidian notes via the knowledge base (RAG). "
                "Use when the user asks to find something in their notes or in Obsidian."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Semantic search query"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_obsidian_note",
            "description": "Read one Obsidian note by its path inside the vault.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_path": {"type": "string", "description": "Vault-relative path, for example 'Daily/2026-06-23.md' or 'Ideas.md'"}
                },
                "required": ["note_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_obsidian_note",
            "description": (
                "Create a note in Obsidian when the user asks to save or write something down.\n"
                "Pick the folder from the content. Do not ask the user.\n"
                "  Research/<topic> — papers, research, arxiv, analysis\n"
                "  Ideas — ideas, concepts, brainstorms\n"
                "  Projects/<name> — a specific project or task\n"
                "  People/<name> — notes about people\n"
                "  Daily/<YYYY-MM-DD> — journal entries\n"
                "  Finance — money, bets, investments, budget\n"
                "  Health — health, training, food\n"
                "  Tech — tools, tutorials, code\n"
                "  Books — books, notes, quotes\n"
                "  Meetings — meetings, calls, agreements\n"
                "  Jarvis — Jarvis notes with no clearer category\n"
                "Nested folders are fine, for example Research/AI or Projects/Jarvis."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short note title (filename without .md)"},
                    "content": {"type": "string", "description": "Markdown body. Use headings, lists, and links."},
                    "folder": {"type": "string", "description": "Vault folder from the taxonomy above. Nested paths such as 'Research/AI' are allowed"},
                    "source": {"type": "string", "description": "Source file or URL. Leave empty if none."}
                },
                "required": ["title", "content", "folder"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sync_obsidian_vault",
            "description": "Reindex the Obsidian vault into the knowledge base. Use after new notes were added outside Jarvis.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

from backend.plugins import collect as _plugin_collect, hook as _plugin_hook
for _schema in _plugin_collect("extra_tool_schemas"):
    TOOLS_SCHEMA.append(_schema)

def _clean_search_query(query: str) -> str:
    """Clean verbose LLM instructions into focused search keywords."""
    q = query.strip().strip("\"'")
    patterns = [
        r"^(search(\s+the\s+internet|\s+the\s+web|\s+online)?\s+(for|about)\s+)",
        r"^(find(\s+the\s+latest|\s+recent|\s+online|\s+information\s+about|\s+news\s+about|\s+news\s+on)?\s+)",
        r"^(look\s+up\s+)",
        r"^(please\s+search\s+(for\s+)?)",
    ]
    for p in patterns:
        q = re.sub(p, "", q, flags=re.IGNORECASE).strip()
    return q

async def _scrape_ddg(query: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    clean_q = _clean_search_query(query)
    queries_to_try = [query] if query == clean_q else [query, clean_q]

    for current_q in queries_to_try:
        # 1. Attempt DuckDuckGo HTML POST
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.post("https://html.duckduckgo.com/html/", data={"q": current_q}, headers=headers)
                if r.status_code == 200 and ("result" in r.text or "results" in r.text):
                    from bs4 import BeautifulSoup
                    import urllib.parse
                    soup = BeautifulSoup(r.text, "html.parser")
                    results = []
                    items = soup.find_all("div", class_="result")
                    for item in items[:5]:
                        title_el = item.find("a", class_="result__a") or item.find("a")
                        snippet_el = item.find("a", class_="result__snippet") or item.find(class_="result__snippet")
                        if title_el:
                            title = title_el.get_text(separator=" ").strip()
                            link = title_el.get("href", "")
                            if "uddg=" in link:
                                parsed = urllib.parse.urlparse(link)
                                qs = urllib.parse.parse_qs(parsed.query)
                                if qs.get("uddg"):
                                    link = urllib.parse.unquote(qs["uddg"][0])
                            elif link.startswith("//"):
                                link = f"https:{link}"
                            snippet = snippet_el.get_text(separator=" ").strip() if snippet_el else ""
                            if title:
                                results.append(f"• **{title}**\n  {snippet}\n  🔗 {link}")
                    if results:
                        return "\n\n".join(results)
        except Exception as e:
            logger.debug(f"DDG HTML search scrape attempt failed: {e}")

        # 2. Attempt DuckDuckGo Lite POST as fallback
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
                r = await client.post("https://lite.duckduckgo.com/lite/", data={"q": current_q}, headers=headers)
                if r.status_code == 200:
                    from bs4 import BeautifulSoup
                    import urllib.parse
                    soup = BeautifulSoup(r.text, "html.parser")
                    results = []
                    rows = soup.find_all("tr")
                    for i, tr in enumerate(rows):
                        link_el = tr.find("a", class_="result-link")
                        if link_el:
                            title = link_el.get_text(separator=" ").strip()
                            link = link_el.get("href", "")
                            if "uddg=" in link:
                                parsed = urllib.parse.urlparse(link)
                                qs = urllib.parse.parse_qs(parsed.query)
                                if qs.get("uddg"):
                                    link = urllib.parse.unquote(qs["uddg"][0])
                            elif link.startswith("//"):
                                link = f"https:{link}"
                            snippet = ""
                            for next_tr in rows[i+1:i+3]:
                                snip_td = next_tr.find("td", class_="result-snippet")
                                if snip_td:
                                    snippet = snip_td.get_text(separator=" ").strip()
                                    break
                            if title:
                                results.append(f"• **{title}**\n  {snippet}\n  🔗 {link}")
                        if len(results) >= 5:
                            break
                    if results:
                        return "\n\n".join(results)
        except Exception as e:
            logger.debug(f"DDG Lite search scrape attempt failed: {e}")

    return "No results found. Unable to retrieve search results at this time."


async def _searxng_search(query: str, base_url: str) -> str:
    """Search via SearXNG (Self-hosted metasearch API)."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                f"{base_url.rstrip('/')}/search",
                params={"q": query, "format": "json"}
            )
            if r.status_code == 200:
                data = r.json()
                results = []

                # Organic results
                organic = data.get("results", [])
                for res in organic[:6]:
                    snippet = res.get("content", "")
                    results.append(f"\u2022 **{res.get('title', '')}**\n  {snippet}\n  \U0001f517 {res.get('url', '')}")

                if results:
                    return "\n\n".join(results)
    except Exception as e:
        logger.warning(f"SearXNG search failed: {e}")
    return ""


async def _search_google_news_rss(query: str) -> str:
    """Zero-key fallback: query Google News RSS feed for real-time news and macro headlines."""
    try:
        import urllib.parse
        import xml.etree.ElementTree as ET
        import html
        import re

        clean_q = _clean_search_query(query)
        encoded = urllib.parse.quote(clean_q or query)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8",
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            if r.status_code == 200 and r.text:
                root = ET.fromstring(r.text)
                items = root.findall(".//item")
                results = []
                for item in items[:5]:
                    title_el = item.find("title")
                    link_el = item.find("link")
                    desc_el = item.find("description")
                    pub_el = item.find("pubDate")

                    title = html.unescape(title_el.text).strip() if title_el is not None and title_el.text else ""
                    link = link_el.text.strip() if link_el is not None and link_el.text else ""
                    desc = ""
                    if desc_el is not None and desc_el.text:
                        desc = re.sub(r"<[^>]+>", " ", desc_el.text)
                        desc = html.unescape(desc).strip()
                    pub = pub_el.text.strip() if pub_el is not None and pub_el.text else ""

                    snippet_parts = []
                    if pub:
                        snippet_parts.append(f"[{pub}]")
                    if desc and desc != title:
                        snippet_parts.append(desc[:200])
                    snippet = " ".join(snippet_parts)

                    if title:
                        results.append(f"• **{title}**\n  {snippet}\n  🔗 {link}")
                if results:
                    return "\n\n".join(results)
    except Exception as e:
        logger.debug(f"Google News RSS search failed: {e}")
    return ""


async def _search_wikipedia(query: str) -> str:
    """Zero-key fallback: query Wikipedia OpenSearch API for encyclopedic/entity data."""
    try:
        import urllib.parse
        clean_q = _clean_search_query(query)
        encoded = urllib.parse.quote(clean_q or query)
        url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={encoded}&limit=3&namespace=0&format=json"
        headers = {
            "User-Agent": "JarvisAssistant/1.0 (https://github.com/pauloberezini/jarvis)"
        }
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) >= 4:
                    titles = data[1]
                    descriptions = data[2]
                    links = data[3]
                    results = []
                    for t, d, l in zip(titles, descriptions, links):
                        if t and l:
                            results.append(f"• **{t}**\n  {d}\n  🔗 {l}")
                    if results:
                        return "\n\n".join(results)
    except Exception as e:
        logger.debug(f"Wikipedia OpenSearch failed: {e}")
    return ""


def web_search(query: str) -> str:
    # 1. Try SearXNG (Open-source self-hosted metasearch)
    searxng_url = _env("SEARXNG_URL")
    if searxng_url:
        try:
            res = _run_async(_searxng_search(query, searxng_url))
            if res:
                logger.info(f"web_search: SearXNG returned results for '{query}'")
                return res
        except Exception as e:
            logger.warning(f"SearXNG search exception: {e}")

    # 2. Try Tavily as fallback
    tavily_key = _env("TAVILY_API_KEY")
    if tavily_key:
        try:
            async def _tavily_search():
                async with httpx.AsyncClient(timeout=15.0) as client:
                    r = await client.post(
                        "https://api.tavily.com/search",
                        json={"api_key": tavily_key, "query": query, "max_results": 5}
                    )
                    if r.status_code == 200:
                        data = r.json()
                        results = []
                        for res in data.get("results", []):
                            results.append(f"\u2022 **{res.get('title')}**\n  {res.get('content')}\n  \U0001f517 {res.get('url')}")
                        return "\n\n".join(results)
            res = _run_async(_tavily_search())
            if res:
                logger.info(f"web_search: Tavily returned results for '{query}'")
                return res
        except Exception as e:
            logger.warning(f"Tavily search failed: {e}")

    # 3. DuckDuckGo HTML scraping
    logger.info(f"web_search: Falling back to DDG scraping for '{query}'")
    res = _run_async(_scrape_ddg(query))
    if isinstance(res, str) and res.strip() and not res.startswith("No results found"):
        return res

    # 4. Zero-key Google News RSS fallback (resilient to bot/captcha blocks on datacenter IPs)
    logger.info(f"web_search: Falling back to Google News RSS for '{query}'")
    news_res = _run_async(_search_google_news_rss(query))
    if isinstance(news_res, str) and news_res.strip():
        return news_res

    # 5. Zero-key Wikipedia OpenSearch fallback
    logger.info(f"web_search: Falling back to Wikipedia OpenSearch for '{query}'")
    wiki_res = _run_async(_search_wikipedia(query))
    if isinstance(wiki_res, str) and wiki_res.strip():
        return wiki_res

    return "No results found. Unable to retrieve search results at this time."

def add_price_alert(symbol: str, target_price: float, condition: str, chat_id: str = "default") -> str:
    from backend.price_monitor import price_monitor
    try:
        alert = price_monitor.add_alert(symbol, float(target_price), condition, chat_id)
        return json.dumps({
            "status": "success",
            "message": f"Alert set: you will be notified when {alert['display_name']} is {condition} ${target_price}.",
            "alert": alert
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"add_price_alert tool error: {e}")
        return json.dumps({"error": str(e)})

def get_market_prices(symbols: str) -> str:
    from backend.price_monitor import price_monitor
    try:
        parts = [s.strip() for s in symbols.split(",") if s.strip()]
        results = {}
        for s in parts:
            p = _run_async(price_monitor.get_market_price(s))
            results[s] = p if p is not None else "no data"
        return json.dumps(results, ensure_ascii=False)
    except Exception as e:
        logger.error(f"get_market_prices tool error: {e}")
        return json.dumps({"error": str(e)})

def _get_local_repo() -> Optional[str]:
    git_config_path = "/Users/pauloberezini/Documents/private/git/jarvis/.git/config"
    if not os.path.exists(git_config_path):
        return None
    try:
        with open(git_config_path, "r") as f:
            content = f.read()
        import re
        match = re.search(r'url\s*=\s*(.+)', content)
        if match:
            url = match.group(1).strip()
            if "github.com" in url:
                parts = url.split("github.com")[-1]
                parts = parts.strip(":/").replace(".git", "")
                return parts
    except Exception as e:
        logger.warning(f"Error reading local git config: {e}")
    return None

def get_github_summary(repo_name: Optional[str] = None, request_type: str = "all") -> str:
    repo = repo_name or _get_local_repo() or "pauloberezini/jarvis"
    token = _env("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Jarvis-Assistant"}
    if token:
        headers["Authorization"] = f"token {token}"
    
    async def _fetch():
        async with httpx.AsyncClient(timeout=10.0) as client:
            output = []
            if request_type in ("prs", "all"):
                r = await client.get(f"https://api.github.com/repos/{repo}/pulls", headers=headers)
                if r.status_code == 200:
                    prs = r.json()
                    output.append(f"### Open pull requests ({len(prs)}):\n" + "\n".join(
                        [f"- #{p.get('number')}: **{p.get('title')}** by {p.get('user', {}).get('login')} (🔗 {p.get('html_url')})" for p in prs[:5]]
                    ))
            if request_type in ("issues", "all"):
                r = await client.get(f"https://api.github.com/repos/{repo}/issues", headers=headers)
                if r.status_code == 200:
                    issues = [i for i in r.json() if "pull_request" not in i]
                    output.append(f"### Open issues ({len(issues)}):\n" + "\n".join(
                        [f"- #{i.get('number')}: **{i.get('title')}** ({i.get('state')}) (🔗 {i.get('html_url')})" for i in issues[:5]]
                    ))
            if request_type in ("releases", "all"):
                r = await client.get(f"https://api.github.com/repos/{repo}/releases", headers=headers)
                if r.status_code == 200:
                    rels = r.json()
                    output.append(f"### Releases:\n" + "\n".join(
                        [f"- **{rel.get('name') or rel.get('tag_name')}** ({rel.get('published_at')[:10]})" for rel in rels[:3]]
                    ))
            
            if not output:
                return f"Could not fetch data for repository {repo}."
            return f"## Repository {repo}:\n\n" + "\n\n".join(output)

    try:
        return _run_async(_fetch())
    except Exception as e:
        logger.error(f"get_github_summary tool error: {e}")
        return json.dumps({"error": str(e)})

def get_rss_digest(feed_source: str = "Habr", limit: int = 5) -> str:
    feeds = {
        "habr": "https://habr.com/ru/rss/news/",
        "techcrunch": "https://techcrunch.com/feed/",
        "hackernews": "https://news.ycombinator.com/rss",
        "rbc": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
        "lenta": "https://lenta.ru/rss/news"
    }
    url = feeds.get(feed_source.lower().strip(), feeds["habr"])

    async def _fetch():
        import xml.etree.ElementTree as ET
        from bs4 import BeautifulSoup
        headers = {"User-Agent": "Mozilla/5.0"}
        async with httpx.AsyncClient(timeout=10.0, headers=headers, follow_redirects=True) as client:
            r = await client.get(url)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                items = root.findall(".//item")
                output = []
                for item in items[:int(limit)]:
                    title = (item.findtext("title") or "").strip()
                    desc = (item.findtext("description") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    if "<" in desc:
                        desc = BeautifulSoup(desc, "html.parser").get_text(separator=" ")
                    output.append(f"• **{title}**\n  {desc[:250]}...\n  🔗 {link}")
                if output:
                    return f"## Latest news ({feed_source}):\n\n" + "\n\n".join(output)
        return f"Could not read the RSS feed for {feed_source}."

    try:
        return _run_async(_fetch())
    except Exception as e:
        return f"RSS fetch failed: {e}"


def read_rss_node_feed(node_id: Optional[str] = None, limit: Optional[int] = None) -> str:
    """Reads configured RSS feed news entries from autonomous RSS nodes in the database."""
    try:
        from backend.rss_service import get_rss_node_output
        from backend.database import db_get_all_rss_nodes

        if not node_id or node_id.strip() == "" or node_id == "all":
            all_nodes = db_get_all_rss_nodes()
            active_nodes = [n for n in all_nodes if n.get("is_active")]
            if not active_nodes:
                return "No active RSS nodes are configured."

            all_outputs = []
            for n in active_nodes:
                res = get_rss_node_output(n["id"], override_limit=limit)
                items = res.get("items", [])
                if items:
                    lines = [f"### RSS node: {res.get('name')} (ID: {n['id']})"]
                    for idx, item in enumerate(items, 1):
                        title = item.get("title", "Untitled")
                        link = item.get("link", "")
                        summary = item.get("summary", "")
                        if len(summary) > 200:
                            summary = summary[:200] + "..."
                        lines.append(f"{idx}. **{title}**\n   {summary}\n   🔗 {link}")
                    all_outputs.append("\n\n".join(lines))

            if not all_outputs:
                return "Active RSS nodes have no saved items yet."

            return "## Active RSS nodes:\n\n" + "\n\n---\n\n".join(all_outputs)

        res = get_rss_node_output(node_id, override_limit=limit)
        if res.get("status") == "error":
            return json.dumps(res, ensure_ascii=False)

        items = res.get("items", [])
        if not items:
            return f"RSS node '{res.get('name')}' ({node_id}) has no saved items."

        lines = [f"## RSS node: {res.get('name')} (ID: {node_id})", f"*Items returned: {len(items)}*"]
        for idx, item in enumerate(items, 1):
            title = item.get("title", "Untitled")
            link = item.get("link", "")
            summary = item.get("summary", "")
            if len(summary) > 200:
                summary = summary[:200] + "..."
            lines.append(f"{idx}. **{title}**\n   {summary}\n   🔗 {link}")

        return "\n\n".join(lines)
    except Exception as e:
        logger.error(f"read_rss_node_feed tool error: {e}")
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def create_subagent(
    subagent_id: str,
    name: str,
    system_prompt: str,
    model: Optional[str] = None,
    parent_id: Optional[str] = None,
    skills: Optional[str] = None,
) -> str:
    """Create a subagent via the same dedup and skill cap as automatic hiring."""
    from backend.agent_factory import ensure_specialist
    from backend.database import get_subagent
    parent_skills = ""
    if parent_id:
        parent = get_subagent(parent_id)
        parent_skills = (parent or {}).get("skills") or ""
    row = ensure_specialist(
        {
            "id": subagent_id,
            "name": name,
            "mandate": system_prompt,
            "skills": skills or "",
            "reason": "manual",
            "model": model,
        },
        parent_id or "",
        parent_skills,
        reason="manual",
        origin="manual",
    )
    if not row:
        return json.dumps({"error": "specialist was not created"}, ensure_ascii=False)
    verb = "reused" if row.get("reused") else "created"
    return json.dumps({
        "status": "success",
        "id": row.get("id"),
        "message": f"Subagent '{row.get('name')}' (id: '{row.get('id')}') {verb}."
    }, ensure_ascii=False)

def call_subagent(subagent_id: str, query: str) -> str:
    """Delegates a query/task to a specialized subagent and returns its response."""
    from backend.database import get_subagent
    from backend.agent import agent_instance
    import asyncio
    
    clean_id = subagent_id.strip().lower()
    subagent = get_subagent(clean_id)
    if not subagent:
        return json.dumps({"error": f"Subagent '{clean_id}' was not found."}, ensure_ascii=False)
    if subagent.get("hire_status") == "pending":
        return json.dumps({"error": f"Subagent '{clean_id}' is pending confirmation."}, ensure_ascii=False)
    
    # Read parent_message_id from threading.local context (set by parent agent before tool dispatch)
    parent_msg_id = getattr(_call_context, "parent_message_id", None)
        
    try:
        # Run the async agent respond call inside sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                response = pool.submit(
                    asyncio.run,
                    agent_instance._respond_as_subagent(
                        query,
                        subagent,
                        chat_id=clean_id,
                        parent_message_id=parent_msg_id
                    )
                ).result(timeout=45)
        else:
            response = loop.run_until_complete(
                agent_instance._respond_as_subagent(
                    query,
                    subagent,
                    chat_id=clean_id,
                    parent_message_id=parent_msg_id
                )
            )
        return json.dumps({
            "subagent_id": clean_id,
            "query": query,
            "response": response
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error calling subagent {clean_id}: {e}")
        return json.dumps({"error": f"Subagent call failed: {str(e)}"}, ensure_ascii=False)


def list_subagents() -> str:
    """Lists all registered subagents available in the system."""
    from backend.database import get_all_subagents
    agents = get_all_subagents()
    return json.dumps({"subagents": agents}, ensure_ascii=False)

def save_subagent_memory(key: str, value: str, chat_id: Optional[str] = None) -> str:
    """Saves or updates a persistent memory fact (key-value pair) for the active subagent."""
    if not chat_id:
        return json.dumps({"error": "Cannot save subagent memory: chat_id is missing."}, ensure_ascii=False)
    
    from backend.database import db_save_subagent_memory
    from backend.rag import index_document
    
    clean_subagent_id = chat_id.strip().lower()
    
    # 1. Save in DB
    db_save_subagent_memory(clean_subagent_id, key, value)
    
    # 2. Index in Qdrant (RAG)
    doc_id = f"subagent_mem_{clean_subagent_id}_{key}"
    title = f"Subagent memory ({clean_subagent_id}): {key}"
    success = index_document(
        doc_id=doc_id,
        title=title,
        text=f"Subagent {clean_subagent_id} memory for '{key}':\n{value}",
        source=f"subagent_memory_{clean_subagent_id}"
    )
    
    return json.dumps({
        "status": "success",
        "message": f"Saved to the database and indexed in RAG (RAG ok: {success})."
    }, ensure_ascii=False)

def get_subagent_memory(key: Optional[str] = None, chat_id: Optional[str] = None) -> str:
    """Retrieves saved memory facts for the active subagent."""
    if not chat_id:
        return json.dumps({"error": "Cannot load subagent memory: chat_id is missing."}, ensure_ascii=False)
        
    from backend.database import db_get_subagent_memory
    
    clean_subagent_id = chat_id.strip().lower()
    memories = db_get_subagent_memory(clean_subagent_id, key)
    
    return json.dumps({
        "subagent_id": clean_subagent_id,
        "memories": memories
    }, ensure_ascii=False)


# ─── Obsidian Tools ───────────────────────────────────────────────────────────

def search_obsidian(query: str) -> str:
    """Semantic search over indexed Obsidian vault notes via RAG."""
    from backend.rag import search_memory
    hits = search_memory(query, limit=5, threshold=0.4, source_filter="obsidian")
    if not hits:
        # Fallback: try plain text search via Obsidian plugin
        async def _plugin_search():
            from backend.obsidian import search_notes
            return await search_notes(query, limit=5)
        plugin_hits = _run_async(_plugin_search())
        if plugin_hits:
            results = []
            for h in plugin_hits:
                results.append(f"\U0001f4c4 **{h.get('filename', '')}**\n  {h.get('excerpt', '')}")
            return "\n\n".join(results)
        return json.dumps({"results": [], "message": "No notes found for '"+query+"'. Try sync_obsidian_vault."},
                ensure_ascii=False)
    results = []
    for h in hits:
        results.append(
            f"\U0001f4c4 **{h['title']}** (score: {h['score']:.2f})\n"
            f"  {h['content'][:300]}..."
            + (f"\n  File: {h['note_path']}" if h.get('note_path') else "")
        )
    return "\n\n".join(results)


def read_obsidian_note(note_path: str) -> str:
    """Read the full content of an Obsidian note by its vault-relative path."""
    async def _read():
        from backend.obsidian import read_note
        return await read_note(note_path)
    content = _run_async(_read())
    if content is None:
        return json.dumps({"error": f"Note '{note_path}' was not found. Check the path and the Obsidian connection."},
                ensure_ascii=False)
    return json.dumps({"path": note_path, "content": content}, ensure_ascii=False)


def create_obsidian_note(title: str, content: str, folder: str = "Jarvis", source: str = "") -> str:
    """Create a new note in the Obsidian vault under the specified folder."""
    import re
    # Sanitize filename
    safe_title = re.sub(r'[<>:"/\\|?*]', '-', title).strip()
    note_path = f"{folder}/{safe_title}.md" if folder else f"{safe_title}.md"

    # Build YAML frontmatter — rich enough for Dataview / Templater plugins
    from datetime import datetime, timezone, timedelta
    now_utc = datetime.now(timezone.utc)
    # UTC+3 (Israel/Jerusalem) with ISO offset — portable and timezone-aware
    tz_offset = timedelta(hours=3)
    now_local = now_utc.astimezone(timezone(tz_offset))
    created_ts = now_local.strftime("%Y-%m-%dT%H:%M:%S%z")  # e.g. 2026-07-13T12:00:00+0300

    # Derive tags from folder hierarchy: "Research/AI" → ["research", "ai"]
    auto_tags = [seg.lower().replace(" ", "-") for seg in folder.split("/") if seg]
    tags_yaml = "\n".join(f"  - {t}" for t in auto_tags)

    source_line = f'source: "{source}"\n' if source else ""
    aliases_line = f'aliases:\n  - "{title}"\n' if title else ""

    frontmatter = (
        f"---\n"
        f"created: {created_ts}\n"
        f"created_by: Jarvis\n"
        f"{source_line}"
        f"tags:\n{tags_yaml}\n"
        f"{aliases_line}"
        f"---\n"
    )
    full_content = f"{frontmatter}\n# {title}\n\n{content}"

    async def _create():
        from backend.obsidian import create_note
        return await create_note(note_path, full_content)

    ok = _run_async(_create())
    import hashlib
    doc_id = "obsidian_" + hashlib.sha1(note_path.encode()).hexdigest()
    from backend.rag import index_document
    indexed = index_document(doc_id, title, full_content, source="obsidian", note_path=note_path)
    if not ok and not indexed:
        return json.dumps({"error": "Could not create the note. Is Obsidian running with the Local REST API plugin?"},
                ensure_ascii=False)
    if not ok:
        return json.dumps({
            "status": "created",
            "path": note_path,
            "vault": False,
            "message": f"Note '{title}' saved to knowledge base ({note_path}). Obsidian plugin is offline."
        }, ensure_ascii=False)

    return json.dumps({
        "status": "created",
        "path": note_path,
        "vault": True,
        "message": f"Note '{title}' created in Obsidian vault: {note_path}"
    }, ensure_ascii=False)


_KB_WRITE = (
    "knowledge base", "write this down", "save this", "into notes",
    "obsidian", "create a note", "save in obsidian",
    "write in obsidian", "save the idea",
)
_KB_READ_ONLY = ("find in notes", "what is in my notes", "what did i write", "look in obsidian")


def is_knowledge_save_request(text: str) -> bool:
    """True when the user is handing over content to archive, not asking a question."""
    if not text or not isinstance(text, str):
        return False
    low = text.lower()
    if not any(k in low for k in _KB_WRITE):
        return False
    if any(k in low for k in _KB_READ_ONLY):
        return False
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return len(lines) >= 3 or len(text.strip()) >= 200


def _guess_note_folder(text: str) -> str:
    low = text.lower()
    if any(k in low for k in ("recipe", "ingredient", "nutrition", "workout", "turkey")):
        return "Health"
    if any(k in low for k in ("trading", "stock", "forex", "budget", "bet")):
        return "Finance"
    return "Jarvis"


def _guess_note_title(text: str) -> str:
    skip = re.compile(
        r"(knowledge base|write this down|save this|obsidian|into notes)",
        re.IGNORECASE,
    )
    for raw in text.splitlines():
        line = re.sub(r"^[•\-\d\.\)\s]+", "", raw).strip()
        if len(line) < 8 or len(line) > 80 or skip.search(line):
            continue
        return line[:80]
    return "Note"


def try_direct_knowledge_save(user_message: str) -> Optional[str]:
    """Write to Obsidian/RAG without waiting for the LLM to call a tool."""
    if not is_knowledge_save_request(user_message):
        return None
    title = _guess_note_title(user_message)
    folder = _guess_note_folder(user_message)
    raw = create_obsidian_note(title, user_message.strip(), folder)
    try:
        data = json.loads(raw)
    except Exception:
        return None
    if data.get("error"):
        return f"Could not save the note: {data['error']}"
    path = data.get("path", f"{folder}/{title}.md")
    return f"The note is in the knowledge base: `{path}`."


def sync_obsidian_vault() -> str:
    """Trigger full Obsidian vault → Qdrant RAG re-indexing."""
    async def _sync():
        from backend.obsidian import sync_vault_to_rag
        return await sync_vault_to_rag()
    result = _run_async(_sync())
    return json.dumps(result, ensure_ascii=False)

def execute_command(command: str) -> str:
    """Executes a shell command in the local environment and returns its stdout/stderr."""
    import subprocess
    try:
        res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=15)
        output = res.stdout if res.stdout else ""
        error = res.stderr if res.stderr else ""
        return json.dumps({
            "exit_code": res.returncode,
            "stdout": output,
            "stderr": error
        }, ensure_ascii=False)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "Command timed out after 15 seconds."}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"Failed to execute command: {e}"}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL ROUTER
# ═══════════════════════════════════════════════════════════════════════════════

def is_invalid_tool_name(name: Any) -> bool:
    """Checks whether a given candidate name is an invalid, generic, or non-callable tool identifier.
    
    Rejects:
    - None or boolean types (e.g. True, False)
    - Generic keyword placeholders ('function', 'tool', 'call', 'action', 'method', 'type', 'tool_call')
    - Boolean/null literal strings ('true', 'false', 'null', 'none', 'undefined', 'boolean', 'bool')
    - Python reserved keywords ('True', 'False', 'None', 'def', 'class', etc.)
    - Empty or non-identifier tokens (names containing spaces, brackets, or starting with digits)
    """
    if name is None or isinstance(name, bool):
        return True
    name_str = str(name).strip()
    if not name_str:
        return True
    name_lower = name_str.lower()
    generic_keywords = {
        "function", "tool", "call", "action", "method", "type", "tool_call",
        "true", "false", "null", "none", "undefined", "boolean", "bool"
    }
    if name_lower in generic_keywords:
        return True
    import keyword
    if keyword.iskeyword(name_str) or keyword.iskeyword(name_lower):
        return True
    import re
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_\-\.:]*$', name_str):
        return True
    return False


def execute_tool(name: str, arguments: Dict[str, Any], chat_id: str = "default") -> str:
    if is_invalid_tool_name(name):
        logger.warning(f"execute_tool called with invalid generic tool name: '{name}', arguments: {arguments}. Skipping execution.")
        return json.dumps({"error": f"Invalid tool name: '{name}'. Generic keywords and invalid identifiers cannot be executed as tools."}, ensure_ascii=False)

    from backend.governance import gate_tool
    blocked = gate_tool(chat_id, name, arguments or {})
    if blocked is not None:
        return blocked

    logger.info(f"Executing tool '{name}' with args: {arguments}")

    plugin_result = _plugin_hook("execute_named_tool", name, arguments)
    if plugin_result is not None:
        return plugin_result

    if name == "get_system_stats":
        return get_system_stats()

    elif name == "get_weather":
        return get_weather(
            location=arguments.get("location", "London"),
            days_ahead=int(arguments.get("days_ahead", 0))
        )

    elif name == "get_current_time_israel":
        return get_current_time_israel()

    elif name == "set_timer":
        label = arguments.get("label", "Timer")
        duration = int(arguments.get("duration_seconds", 60))
        agent_id = arguments.get("agent_id")
        prompt = arguments.get("prompt")
        if agent_id or prompt:
            return set_timer(label, duration, chat_id, agent_id, prompt)
        return set_timer(label, duration, chat_id)

    elif name == "set_alarm":
        time_str = arguments.get("time_str", "")
        label = arguments.get("label", "Alarm")
        agent_id = arguments.get("agent_id")
        prompt = arguments.get("prompt")
        if agent_id or prompt:
            return set_alarm(time_str, label, chat_id, agent_id, prompt)
        return set_alarm(time_str, label, chat_id)

    elif name == "cancel_timer_or_alarm":
        return cancel_timer_or_alarm(
            arguments.get("id", "")
        )

    elif name == "set_recurring_reminder":
        label = arguments.get("label", "Reminder")
        interval_hours = float(arguments.get("interval_hours", 24))
        agent_id = arguments.get("agent_id")
        prompt = arguments.get("prompt")
        if agent_id or prompt:
            return set_recurring_reminder(label, interval_hours, chat_id, agent_id, prompt)
        return set_recurring_reminder(label, interval_hours, chat_id)

    elif name == "get_calendar_events":
        return get_calendar_events(int(arguments.get("days_ahead", 7)))

    elif name == "add_calendar_event":
        dur = arguments.get("duration_minutes")
        return add_calendar_event(
            title=arguments.get("title", ""),
            date=arguments.get("date", ""),
            time=arguments.get("time", "10:00"),
            end_time=arguments.get("end_time"),
            duration_minutes=int(dur) if dur is not None else None,
            description=arguments.get("description", ""),
        )

    elif name == "get_todoist_tasks":
        return get_todoist_tasks(arguments.get("filter_str", "today | overdue"))

    elif name == "add_todoist_task":
        return add_todoist_task(
            content=arguments.get("content", ""),
            due_string=arguments.get("due_string", ""),
            priority=int(arguments.get("priority", 1)),
        )

    elif name == "delete_todoist_task":
        return delete_todoist_task(
            task_id=arguments.get("task_id", ""),
        )



    elif name in ("web_search", "perform_search", "search", "google_search", "duckduckgo_search", "internet_search"):
        query = (
            arguments.get("query")
            or arguments.get("q")
            or arguments.get("search_query")
            or arguments.get("keywords")
            or ""
        )
        return web_search(query=query)

    elif name == "add_price_alert":
        return add_price_alert(
            symbol=arguments.get("symbol", ""),
            target_price=arguments.get("target_price", 0.0),
            condition=arguments.get("condition", "above"),
            chat_id=chat_id
        )

    elif name == "get_market_prices":
        return get_market_prices(
            symbols=arguments.get("symbols", "")
        )

    elif name == "get_github_summary":
        return get_github_summary(
            repo_name=arguments.get("repo_name"),
            request_type=arguments.get("request_type", "all")
        )

    elif name == "get_rss_digest":
        return get_rss_digest(
            feed_source=arguments.get("feed_source", "Habr"),
            limit=arguments.get("limit", 5)
        )

    elif name == "read_rss_node_feed":
        return read_rss_node_feed(
            node_id=arguments.get("node_id"),
            limit=arguments.get("limit")
        )

    elif name == "create_subagent":
        return create_subagent(
            subagent_id=arguments.get("subagent_id", ""),
            name=arguments.get("name", ""),
            system_prompt=arguments.get("system_prompt", ""),
            model=arguments.get("model"),
            parent_id=arguments.get("parent_id"),
            skills=arguments.get("skills"),
        )

    elif name == "call_subagent":
        return call_subagent(
            subagent_id=arguments.get("subagent_id", ""),
            query=arguments.get("query", "")
        )

    elif name == "list_subagents":
        return list_subagents()

    elif name == "save_subagent_memory":
        return save_subagent_memory(
            key=arguments.get("key", ""),
            value=arguments.get("value", ""),
            chat_id=chat_id
        )

    elif name == "get_subagent_memory":
        return get_subagent_memory(
            key=arguments.get("key"),
            chat_id=chat_id
        )

    elif name == "search_obsidian":
        return search_obsidian(query=arguments.get("query", ""))

    elif name == "read_obsidian_note":
        return read_obsidian_note(note_path=arguments.get("note_path", ""))

    elif name == "create_obsidian_note":
        return create_obsidian_note(
            title=arguments.get("title", ""),
            content=arguments.get("content", ""),
            folder=arguments.get("folder", "Jarvis"),
            source=arguments.get("source", "")
        )

    elif name == "sync_obsidian_vault":
        return sync_obsidian_vault()

    elif name == "execute_command":
        return execute_command(arguments.get("command", ""))

    else:
        # Check if it is an MCP tool
        from backend.mcp_client import mcp_tool_to_server, handle_mcp_tool
        if name in mcp_tool_to_server:
            return _run_async(handle_mcp_tool(name, arguments))

        return json.dumps({"error": f"Tool '{name}' not found."})

