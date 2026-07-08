import os
import json
import logging
import asyncio
import httpx
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional

logger = logging.getLogger("hermes.tools")

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _env(key: str) -> Optional[str]:
    """Read env var; return None if missing or empty placeholder."""
    val = os.getenv(key, "").strip()
    return val if val and not val.startswith("your_") else None


# ═══════════════════════════════════════════════════════════════════════════════
# 1. SYSTEM STATS
# ═══════════════════════════════════════════════════════════════════════════════

def _read_cpu_percent_from_proc() -> Optional[int]:
    """Read CPU utilization from /proc/stat without inventing fallback values."""
    if not os.path.exists("/proc/stat"):
        return None

    def snapshot() -> Optional[tuple[int, int]]:
        try:
            with open("/proc/stat") as f:
                first = f.readline().strip().split()
            if not first or first[0] != "cpu":
                return None
            values = [int(v) for v in first[1:]]
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            total = sum(values)
            return idle, total
        except Exception:
            return None

    first = snapshot()
    if not first:
        return None
    import time
    time.sleep(0.1)
    second = snapshot()
    if not second:
        return None

    idle_delta = second[0] - first[0]
    total_delta = second[1] - first[1]
    if total_delta <= 0:
        return None
    return int(round((1 - idle_delta / total_delta) * 100))


def get_system_stats() -> str:
    """Reads real system stats or marks unavailable metrics explicitly."""
    try:
        unavailable = []
        stat = os.statvfs('/')
        free_bytes  = stat.f_bavail * stat.f_frsize
        total_bytes = stat.f_blocks * stat.f_frsize
        used_bytes  = total_bytes - free_bytes
        disk_pct    = int((used_bytes / total_bytes) * 100) if total_bytes > 0 else 0
        total_gb    = round(total_bytes / (1024**3), 1)
        used_gb     = round(used_bytes  / (1024**3), 1)

        mem_total_gb, mem_used_pct = None, None
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
        else:
            unavailable.append("ram")

        cpu_load = None
        try:
            import psutil
            cpu_load = int(psutil.cpu_percent(interval=0.1))
        except Exception:
            cpu_load = _read_cpu_percent_from_proc()
        if cpu_load is None:
            unavailable.append("cpu")

        available = len(unavailable) == 0

        return json.dumps({
            "available": available,
            "cpu_load_percent":  cpu_load,
            "ram_used_percent":  mem_used_pct,
            "ram_total_gb":      mem_total_gb,
            "disk_used_percent": disk_pct,
            "disk_total_gb":     total_gb,
            "disk_used_gb":      used_gb,
            "status": "nominal" if available else "partial",
            "scope": "backend_runtime",
            "source": "backend runtime:/proc + statvfs(/)",
            "warning": "Metrics describe the backend process environment/container, not necessarily the whole physical host.",
            "unavailable": unavailable,
            "error": None if available else f"Unavailable metrics: {', '.join(unavailable)}"
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error reading system stats: {e}")
        return json.dumps({
            "available": False,
            "error": str(e),
            "status": "unavailable",
            "scope": "backend_runtime",
            "source": "backend runtime:/proc + statvfs(/)",
            "warning": "Metrics describe the backend process environment/container, not necessarily the whole physical host.",
            "unavailable": ["cpu", "ram", "disk"]
        }, ensure_ascii=False)


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
            "condition":   "переменная облачность (прогноз)",
            "days_ahead":  days_ahead,
            "source":      "mock — добавьте OPENWEATHERMAP_API_KEY в .env для реальных данных",
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
            return json.dumps({"error": f"Не удалось получить погоду для '{location}'."})

        main    = data.get("main", {})
        weather = data.get("weather", [{}])[0]
        wind    = data.get("wind", {})
        return json.dumps({
            "location":    data.get("name", location),
            "temperature": f"{main.get('temp', '?'):.1f}°C" if main.get('temp') is not None else "нет данных",
            "feels_like":  f"{main.get('feels_like', '?'):.1f}°C" if main.get('feels_like') is not None else "нет данных",
            "condition":   weather.get("description", "неизвестно"),
            "humidity":    f"{main.get('humidity', '?')}%" if main.get('humidity') is not None else "нет данных",
            "wind_speed":  f"{wind.get('speed', '?')} м/с" if wind.get('speed') is not None else "нет данных",
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
            return json.dumps({"error": f"Не удалось получить прогноз погоды для '{location}'."})

        import datetime
        target_date = (datetime.date.today() + datetime.timedelta(days=days_ahead)).strftime("%Y-%m-%d")
        
        forecast_list = data.get("list", [])
        day_forecasts = [item for item in forecast_list if item.get("dt_txt", "").startswith(target_date)]
        
        if not day_forecasts:
            return json.dumps({"error": f"Прогноз для '{location}' на {target_date} не найден."})
            
        midday = [item for item in day_forecasts if "12:00:00" in item.get("dt_txt", "") or "15:00:00" in item.get("dt_txt", "")]
        selected = midday[0] if midday else day_forecasts[len(day_forecasts) // 2]
        
        main = selected.get("main", {})
        weather = selected.get("weather", [{}])[0]
        wind = selected.get("wind", {})
        
        return json.dumps({
            "location":    data.get("city", {}).get("name", location),
            "date":        target_date,
            "days_ahead":  days_ahead,
            "temperature": f"{main.get('temp', '?'):.1f}°C" if main.get('temp') is not None else "нет данных",
            "feels_like":  f"{main.get('feels_like', '?'):.1f}°C" if main.get('feels_like') is not None else "нет данных",
            "condition":   weather.get("description", "неизвестно"),
            "humidity":    f"{main.get('humidity', '?')}%" if main.get('humidity') is not None else "нет данных",
            "wind_speed":  f"{wind.get('speed', '?')} м/с" if wind.get('speed') is not None else "нет данных",
            "source":      "OpenWeatherMap Forecast",
            "status":      "real"
        }, ensure_ascii=False)


def get_current_time_israel() -> str:
    """Returns the current date, time and day of the week in Israel (Asia/Jerusalem)."""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Asia/Jerusalem"))
        day_names = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
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

def set_timer(label: str, duration_seconds: int, chat_id: str) -> str:
    """Creates a countdown timer that fires a Telegram alert on completion."""
    if duration_seconds > 3600:
        return json.dumps({
            "status": "failed",
            "error": "Превышен максимальный лимит. Сэр, таймер нельзя установить более чем на 1 час (3600 секунд)."
        }, ensure_ascii=False)
    try:
        from backend.scheduler import add_timer
        timer_id = add_timer(label, duration_seconds, chat_id)
        return json.dumps({
            "status":           "active",
            "timer_id":         timer_id,
            "label":            label,
            "duration_seconds": duration_seconds,
            "message":          f"Таймер '{label}' установлен на {duration_seconds} секунд."
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error setting timer: {e}")
        return json.dumps({"status": "failed", "error": str(e)})


def set_alarm(time_str: str, label: str, chat_id: str) -> str:
    """Creates an alarm clock scheduled for a specific time/date (Israel local time) with Telegram notification."""
    try:
        from backend.scheduler import add_alarm
        alarm_id = add_alarm(time_str, label, chat_id)
        return json.dumps({
            "status":      "active",
            "alarm_id":    alarm_id,
            "label":       label,
            "time_str":    time_str,
            "message":     f"Будильник '{label}' успешно установлен на {time_str}."
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
                "message": f"Таймер или будильник с ID '{id}' успешно отменён."
            }, ensure_ascii=False)
        else:
            return json.dumps({
                "status":  "not_found",
                "id":      id,
                "message": f"Активный таймер или будильник с ID '{id}' не найден."
            }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error cancelling timer/alarm: {e}")
        return json.dumps({"status": "failed", "error": str(e)}, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. RECURRING REMINDERS
# ═══════════════════════════════════════════════════════════════════════════════

def set_recurring_reminder(label: str, interval_hours: float, chat_id: str) -> str:
    """Creates a recurring reminder that fires every N hours via Telegram."""
    try:
        from backend.scheduler import add_recurring_reminder
        reminder_id = add_recurring_reminder(label, interval_hours, chat_id)
        return json.dumps({
            "status":         "active",
            "reminder_id":    reminder_id,
            "label":          label,
            "interval_hours": interval_hours,
            "message":        f"Повторяющееся напоминание '{label}' каждые {interval_hours}ч установлено."
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
    creds_path = os.path.join(os.path.dirname(__file__), "data", "google_credentials.json")

    if not os.path.exists(creds_path):
        return None, "google_credentials.json не найден. Запустите python backend/google_auth.py"
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
                return None, "Токен Google не найден. Запустите python backend/google_auth.py на вашем Mac."

        service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return service, None
    except ImportError:
        return None, "Установите google-auth-oauthlib и google-api-python-client"
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
        return json.dumps({"error": err, "hint": "Запустите python backend/google_auth.py для авторизации"})
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
            period_label = "сегодня"
        else:
            range_start = today_local
            range_end   = today_local + timedelta(days=days_ahead + 1)
            period_label = f"ближайшие {days_ahead} дней"

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
            return json.dumps({"events": [], "message": f"Нет событий на {period_label}."})

        result = []
        for e in events:
            start_info = e.get("start", {})
            start = start_info.get("dateTime", start_info.get("date", ""))
            is_all_day = "date" in start_info and "dateTime" not in start_info
            result.append({
                "title":      e.get("summary", "(без названия)"),
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

def _run_async(coro):
    """Run async coro from a sync context safely."""
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result(timeout=15)
        return loop.run_until_complete(coro)
    except Exception as e:
        logger.error(f"_run_async error: {e}")
        return None


def get_todoist_tasks(filter_str: str = "today | overdue") -> str:
    """List Todoist tasks. Default filter: today + overdue."""
    token = _env("TODOIST_API_TOKEN")
    if not token:
        return json.dumps({
            "error": "TODOIST_API_TOKEN не задан в .env",
            "hint":  "Возьмите токен на https://app.todoist.com/app/settings/integrations/developer"
        })
    # Todoist v1 uses query param 'filter' for task filtering
    params = {"filter": filter_str} if filter_str else {}
    data = _run_async(_todoist_get("tasks", token, params))
    if data is None:
        return json.dumps({"error": "Не удалось получить задачи из Todoist"})
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
            "error": "TODOIST_API_TOKEN не задан в .env",
            "hint":  "Возьмите токен на https://app.todoist.com/app/settings/integrations/developer"
        })
    payload: Dict[str, Any] = {"content": content, "priority": priority}
    if due_string:
        payload["due_string"] = due_string
        payload["due_lang"]   = "ru"

    result = _run_async(_todoist_post("tasks", token, payload))
    if result is None:
        return json.dumps({"error": "Не удалось создать задачу в Todoist"})
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
            "error": "TODOIST_API_TOKEN не задан в .env",
            "hint":  "Возьмите токен на https://app.todoist.com/app/settings/integrations/developer"
        })
    success = _run_async(_todoist_delete(f"tasks/{task_id}", token))
    if not success:
        return json.dumps({"error": f"Не удалось удалить задачу с ID {task_id} в Todoist"})
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
            "description": "Возвращает системную телеметрию сервера: загрузку CPU, RAM и дисковое пространство.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Возвращает текущую погоду или прогноз погоды на несколько дней для указанного города.",
            "parameters": {
                "type": "object",
                "properties": {
                    "location": {"type": "string", "description": "Название города, например: Москва, Ашкелон, Tokyo"},
                    "days_ahead": {"type": "integer", "description": "Прогноз погоды вперед в днях: 0 для текущей погоды (по умолчанию), 1 для завтрашнего дня, 2 для послезавтра и т.д. (до 4 дней)"}
                },
                "required": ["location"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time_israel",
            "description": "Возвращает текущую точную дату, время и день недели в Израиле (Asia/Jerusalem). Используйте для получения актуальной даты или времени.",
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
            "description": "Устанавливает таймер обратного отсчёта с Telegram-уведомлением по истечении. Обратите внимание: максимальная длительность таймера — 1 час (3600 секунд). Допускается параллельная установка нескольких таймеров.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label":            {"type": "string",  "description": "Описание события, например: созвон, проверить духовку"},
                    "duration_seconds": {"type": "integer", "description": "Интервал в секундах (не более 3600)"}
                },
                "required": ["label", "duration_seconds"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_alarm",
            "description": "Устанавливает будильник на определённое время (например: '08:30', '21:00' или '2026-05-30 07:00'). Если время прошло для сегодняшнего дня, будильник автоматически устанавливается на завтра.",
            "parameters": {
                "type": "object",
                "properties": {
                    "time_str": {"type": "string", "description": "Время срабатывания в формате ЧЧ:ММ (24-часовой формат) или ГГГГ-ММ-ДД ЧЧ:ММ"},
                    "label":    {"type": "string", "description": "Описание будильника (например: 'проснуться', 'встреча')"}
                },
                "required": ["time_str", "label"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_timer_or_alarm",
            "description": "Отменяет активный таймер или будильник по его ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Уникальный идентификатор (ID) таймера или будильника"}
                },
                "required": ["id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "set_recurring_reminder",
            "description": "Создаёт повторяющееся напоминание, которое срабатывает каждые N часов через Telegram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "label":          {"type": "string", "description": "Текст напоминания"},
                    "interval_hours": {"type": "number", "description": "Интервал повтора в часах, например: 24 для ежедневного"}
                },
                "required": ["label", "interval_hours"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_calendar_events",
            "description": "Возвращает список предстоящих событий из Google Календаря. Для вопросов 'что сегодня', 'встречи на сегодня' — используй days_ahead=0. Для 'завтра' — days_ahead=1. По умолчанию 7 дней.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "description": "Сколько дней вперёд смотреть: 0 = только сегодня (включая all-day события), 1 = завтра, 7 = неделя (по умолчанию)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_calendar_event",
            "description": "Добавляет новое событие в Google Календарь.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title":            {"type": "string",  "description": "Название события"},
                    "date":             {"type": "string",  "description": "Дата в формате YYYY-MM-DD"},
                    "time":             {"type": "string",  "description": "Время в формате HH:MM (по умолчанию 10:00)"},
                    "end_time":         {"type": "string",  "description": "Время окончания в формате HH:MM (опционально, если известно точное время окончания)"},
                    "duration_minutes": {"type": "integer", "description": "Длительность в минутах (по умолчанию 60, игнорируется если передан end_time)"},
                    "description":      {"type": "string",  "description": "Описание события (опционально)"}
                },
                "required": ["title", "date"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_todoist_tasks",
            "description": "Возвращает список задач из Todoist. По умолчанию показывает задачи на сегодня и просроченные.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_str": {"type": "string", "description": "Фильтр Todoist, например: 'today', 'overdue', 'p1'"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_todoist_task",
            "description": "Добавляет новую задачу в Todoist.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content":    {"type": "string",  "description": "Текст задачи"},
                    "due_string": {"type": "string",  "description": "Срок выполнения, например: сегодня, завтра, следующая пятница"},
                    "priority":   {"type": "integer", "description": "Приоритет: 1 (обычный) .. 4 (срочный)"}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "delete_todoist_task",
            "description": "Удаляет задачу в Todoist по её ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Уникальный идентификатор (ID) задачи в Todoist"}
                },
                "required": ["task_id"]
            }
        }
    },

    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Выполняет поиск в Интернете в реальном времени, возвращая последние новости, статьи или факты.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Поисковый запрос на русском или английском"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "add_price_alert",
            "description": "Устанавливает оповещение о достижении ценового порога криптовалюты (btc, eth, ton) или акции (AAPL, TSLA).",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Символ актива, например: TON, BTC, AAPL, TSLA"},
                    "target_price": {"type": "number", "description": "Целевая цена в USD, при пересечении которой сработает алерт"},
                    "condition": {"type": "string", "description": "Условие срабатывания: 'above' (выше целевой цены) или 'below' (ниже целевой цены)"}
                },
                "required": ["symbol", "target_price", "condition"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_market_prices",
            "description": "Возвращает текущие рыночные цены на активы (криптовалюту или акции) в реальном времени.",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbols": {"type": "string", "description": "Список активов через запятую, например: 'TON, BTC, TSLA'"}
                },
                "required": ["symbols"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_github_summary",
            "description": "Получает сводку по репозиторию GitHub: активные pull requests, issues или релизы.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_name": {"type": "string", "description": "Полное имя репозитория в формате owner/repo. Если не указано, считывается из локального .git/config"},
                    "request_type": {"type": "string", "description": "Тип запроса: 'prs' (только PR), 'issues' (только задачи), 'releases' (только релизы), 'all' (все вместе)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_rss_digest",
            "description": "Получает последние новости из RSS-источников, например с Хабра, и выводит список последних публикаций.",
            "parameters": {
                "type": "object",
                "properties": {
                    "feed_source": {"type": "string", "description": "Источник новостей: 'habr', 'techcrunch', 'hackernews', 'rbc', 'lenta'"},
                    "limit": {"type": "integer", "description": "Количество новостей (по умолчанию 5)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_subagent",
            "description": "Создаёт нового специализированного сабагента или обновляет существующего (например, эксперта по спортивным ставкам, репетитора языков и т.д.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "subagent_id": {"type": "string", "description": "Уникальный латинский идентификатор (slug), например: 'sports_betting', 'french_tutor'"},
                    "name": {"type": "string", "description": "Понятное имя агента, например: 'Аналитик Спортивных Ставок'"},
                    "system_prompt": {"type": "string", "description": "Детальные инструкции (системный промпт), определяющие характер, тон и правила работы сабагента."},
                    "model": {"type": "string", "description": "Модель ИИ для работы сабагента. По умолчанию используется deepseek/deepseek-v4-flash."},
                    "role": {"type": "string", "description": "Роль агента в ИИ-офисе, например Researcher, Engineer, Analyst, Planner."},
                    "model_type": {"type": "string", "description": "Тип модели: external или local."},
                    "model_provider": {"type": "string", "description": "Провайдер модели, например openrouter, openai, anthropic, ollama, local."}
                },
                "required": ["subagent_id", "name", "system_prompt"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "call_subagent",
            "description": "Передаёт задачу или вопрос специализированному сабагенту по его id и возвращает его ответ.",
            "parameters": {
                "type": "object",
                "properties": {
                    "subagent_id": {"type": "string", "description": "Идентификатор сабагента (id), например: 'sports_betting'"},
                    "query": {"type": "string", "description": "Запрос или задание для сабагента"}
                },
                "required": ["subagent_id", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_subagents",
            "description": "Возвращает список всех зарегистрированных сабагентов в системе.",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_subagent_memory",
            "description": "Сохраняет или обновляет факт (пару ключ-значение) в долгосрочной памяти текущего субагента. Информация будет записана в базу данных и проиндексирована в RAG (Qdrant).",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Ключ (идентификатор факта), например: 'vocabulary', 'user_grammar_level', 'common_mistakes', 'lessons_progress'"},
                    "value": {"type": "string", "description": "Содержимое факта, например: список выученных слов, описание ошибок или уровень пользователя."}
                },
                "required": ["key", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_subagent_memory",
            "description": "Извлекает ранее сохраненные факты из памяти текущего субагента. Если ключ не указан, вернет всю память субагента.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Конкретный ключ для извлечения (необязательно)."}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "execute_command",
            "description": "Выполняет команду оболочки (shell command) в локальной системе и возвращает её stdout/stderr. Используйте для выполнения curl-запросов к внешним API, запуска python-скриптов или системных задач.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Команда для выполнения в терминале, например: 'curl -s https://api.linear.app/...' или 'python -c ...'"}
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
                "Семантический поиск по заметкам Obsidian через базу знаний (RAG). "
                "Используйте когда Сэр спрашивает ‘найди в заметках’, ‘что я писал о...’ или ‘посмотри в Obsidian’."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Смысловой поисковый запрос"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_obsidian_note",
            "description": "Прочитать содержимое конкретной заметки Obsidian по её пути внутри хранилища.",
            "parameters": {
                "type": "object",
                "properties": {
                    "note_path": {"type": "string", "description": "Относительный путь заметки в хранилище, например: 'Daily/2026-06-23.md' или 'Идеи.md'"}
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
                "Создать новую заметку в Obsidian. Используйте когда Сэр говорит 'запиши в Obsidian', 'сохрани заметку', 'зафиксируй' и т.п.\n"
                "ВАЖНО: Вы — архивариус. Самостоятельно определяйте папку по смыслу контента, используя следующую таксономию:\n"
                "  Research/<Тема> — научные статьи, исследования, arxiv, анализ\n"
                "  Ideas — идеи, концепции, brainstorm\n"
                "  Projects/<Название> — конкретные проекты и задачи\n"
                "  People/<Имя> — заметки о людях\n"
                "  Daily/<YYYY-MM-DD> — дневниковые записи, события дня\n"
                "  Finance — финансы, ставки, инвестиции, бюджет\n"
                "  Health — здоровье, тренировки, питание\n"
                "  Tech — технологии, инструменты, туториалы, код\n"
                "  Books — книги, конспекты, цитаты\n"
                "  Meetings — встречи, звонки, договорённости\n"
                "  Vexa — служебные заметки от Vexa без чёткой категории\n"
                "Выбирайте папку автоматически — НЕ спрашивайте Сэра. Можно создавать подпапки, например Research/AI или Projects/Vexa."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Краткое, информативное название заметки (имя файла без .md)"},
                    "content": {"type": "string", "description": "Содержимое заметки в Markdown-формате. Структурируйте через заголовки, списки, ссылки."},
                    "folder": {"type": "string", "description": "Папка внутри хранилища. Определяйте по таксономии из описания. Можно вложенные: 'Research/AI'"}
                },
                "required": ["title", "content", "folder"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "sync_obsidian_vault",
            "description": "Полная синхронизация хранилища Obsidian в базу знаний (векторную БД). Используйте если Сэр добавил новые заметки и хочет обновить базу знаний.",
            "parameters": {"type": "object", "properties": {}}
        }
    }
]

# Try to load private BCM tools if present locally
try:
    if os.path.exists(os.path.join(os.path.dirname(__file__), "bcm")):
        from backend.bcm.tools import BCM_TOOLS
        for tool in BCM_TOOLS:
            TOOLS_SCHEMA.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["inputSchema"]
                }
            })
except Exception as e:
    pass

async def _scrape_ddg(query: str) -> str:
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
    }
    params = {"q": query}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, params=params, headers=headers)
            if r.status_code == 200:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(r.text, "html.parser")
                results = []
                items = soup.find_all("div", class_="result")
                for item in items[:5]:
                    title_el = item.find("a", class_="result__a")
                    snippet_el = item.find("a", class_="result__snippet")
                    if title_el:
                        title = title_el.get_text(separator=" ").strip()
                        link = title_el.get("href", "")
                        snippet = snippet_el.get_text(separator=" ").strip() if snippet_el else ""
                        results.append(f"\u2022 **{title}**\n  {snippet}\n  \U0001f517 {link}")
                if results:
                    return "\n\n".join(results)
    except Exception as e:
        logger.warning(f"DDG search scrape failed: {e}")
    return "Не удалось получить результаты поиска."


async def _serper_search(query: str, api_key: str) -> str:
    """Search via Serper.dev (Google Search API). Returns rich results including news, sports, knowledge graph."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": 6, "hl": "ru", "gl": "il"}
            )
            if r.status_code == 200:
                data = r.json()
                results = []

                # Knowledge Graph (facts, entities)
                kg = data.get("knowledgeGraph", {})
                if kg:
                    kg_text = f"\U0001f4cc **{kg.get('title', '')}** \u2014 {kg.get('description', '')}"
                    attrs = kg.get("attributes", {})
                    if attrs:
                        kg_text += "\n  " + " | ".join(f"{k}: {v}" for k, v in list(attrs.items())[:4])
                    results.append(kg_text)

                # Answer box (direct answer)
                answer_box = data.get("answerBox", {})
                if answer_box:
                    ab_answer = answer_box.get("answer") or answer_box.get("snippet", "")
                    if ab_answer:
                        results.append(f"\u2705 **Прямой ответ:** {ab_answer}")

                # Sports results
                sports = data.get("sports", [])
                for s in sports[:3]:
                    results.append(f"\u26bd **{s.get('title', '')}** \u2014 {s.get('snippet', '')}")

                # News results
                news = data.get("news", [])
                for n in news[:3]:
                    results.append(f"\U0001f4f0 **{n.get('title', '')}**\n  {n.get('snippet', '')}\n  \U0001f517 {n.get('link', '')}")

                # Organic results
                organic = data.get("organic", [])
                for res in organic[:4]:
                    snippet = res.get("snippet", "")
                    results.append(f"\u2022 **{res.get('title', '')}**\n  {snippet}\n  \U0001f517 {res.get('link', '')}")

                if results:
                    return "\n\n".join(results)
    except Exception as e:
        logger.warning(f"Serper search failed: {e}")
    return ""

def web_search(query: str) -> str:
    # 1. Try Serper.dev (Google Search — best for real-time sports/news)
    serper_key = _env("SERPER_API_KEY")
    if serper_key:
        try:
            res = _run_async(_serper_search(query, serper_key))
            if res:
                logger.info(f"web_search: Serper returned results for '{query}'")
                return res
        except Exception as e:
            logger.warning(f"Serper search exception: {e}")

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

    # 3. Last resort: DuckDuckGo HTML scraping
    logger.info(f"web_search: Falling back to DDG scraping for '{query}'")
    return _run_async(_scrape_ddg(query))

def add_price_alert(symbol: str, target_price: float, condition: str, chat_id: str = "default") -> str:
    from backend.price_monitor import price_monitor
    try:
        alert = price_monitor.add_alert(symbol, float(target_price), condition, chat_id)
        return json.dumps({
            "status": "success",
            "message": f"Оповещение установлено: при {condition} ${target_price} для {alert['display_name']} вы получите уведомление.",
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
            results[s] = p if p is not None else "нет данных"
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
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Vexa-Assistant"}
    if token:
        headers["Authorization"] = f"token {token}"
    
    async def _fetch():
        async with httpx.AsyncClient(timeout=10.0) as client:
            output = []
            if request_type in ("prs", "all"):
                r = await client.get(f"https://api.github.com/repos/{repo}/pulls", headers=headers)
                if r.status_code == 200:
                    prs = r.json()
                    output.append(f"### Активные Pull Requests ({len(prs)}):\n" + "\n".join(
                        [f"- #{p.get('number')}: **{p.get('title')}** от {p.get('user', {}).get('login')} (🔗 {p.get('html_url')})" for p in prs[:5]]
                    ))
            if request_type in ("issues", "all"):
                r = await client.get(f"https://api.github.com/repos/{repo}/issues", headers=headers)
                if r.status_code == 200:
                    issues = [i for i in r.json() if "pull_request" not in i]
                    output.append(f"### Активные Issues ({len(issues)}):\n" + "\n".join(
                        [f"- #{i.get('number')}: **{i.get('title')}** ({i.get('state')}) (🔗 {i.get('html_url')})" for i in issues[:5]]
                    ))
            if request_type in ("releases", "all"):
                r = await client.get(f"https://api.github.com/repos/{repo}/releases", headers=headers)
                if r.status_code == 200:
                    rels = r.json()
                    output.append(f"### Релизы:\n" + "\n".join(
                        [f"- **{rel.get('name') or rel.get('tag_name')}** ({rel.get('published_at')[:10]})" for rel in rels[:3]]
                    ))
            
            if not output:
                return f"Не удалось получить данные для репозитория {repo}."
            return f"## Сводка репозитория {repo}:\n\n" + "\n\n".join(output)
            
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
                    return f"## Последние новости ({feed_source}):\n\n" + "\n\n".join(output)
        return f"Не удалось прочитать RSS ленту для {feed_source}."

    try:
        return _run_async(_fetch())
    except Exception as e:
        logger.error(f"get_rss_digest tool error: {e}")
        return json.dumps({"error": str(e)})


def create_subagent(
    subagent_id: str,
    name: str,
    system_prompt: str,
    model: Optional[str] = None,
    role: str = "Specialist",
    model_type: str = "external",
    model_provider: str = "openrouter",
) -> str:
    """Creates a new subagent with a dedicated system prompt and model, or updates an existing one."""
    from backend.database import save_subagent
    # Basic slug cleanup
    import re
    clean_id = re.sub(r'[^a-zA-Z0-9_-]', '', subagent_id).lower()
    if not model:
        model = os.getenv("LLM_MODEL", "google/gemini-2.5-pro")
    save_subagent(
        clean_id,
        name,
        system_prompt,
        model,
        role=role,
        model_type=model_type,
        model_provider=model_provider,
    )
    try:
        from backend.database import log_agent_event
        log_agent_event(clean_id, "created", f"Agent '{name}' created via chat tool.", "success")
    except Exception:
        pass
    return json.dumps({
        "status": "success",
        "message": f"Субагент '{name}' (id: '{clean_id}') успешно создан с моделью '{model}' ({model_type}/{model_provider})."
    }, ensure_ascii=False)

def call_subagent(subagent_id: str, query: str) -> str:
    """Delegates a query/task to a specialized subagent and returns its response."""
    from backend.database import get_subagent
    from backend.agent import agent_instance
    import asyncio
    
    clean_id = subagent_id.strip().lower()
    subagent = get_subagent(clean_id)
    if not subagent:
        return json.dumps({"error": f"Субагент с id '{clean_id}' не найден."}, ensure_ascii=False)
        
    try:
        # Run the async agent respond call inside sync context
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                response = pool.submit(asyncio.run, agent_instance.respond(query, session_id=clean_id)).result(timeout=45)
        else:
            response = loop.run_until_complete(agent_instance.respond(query, session_id=clean_id))
        return json.dumps({
            "subagent_id": clean_id,
            "query": query,
            "response": response
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error calling subagent {clean_id}: {e}")
        return json.dumps({"error": f"Сбой при вызове субагента: {str(e)}"}, ensure_ascii=False)

def list_subagents() -> str:
    """Lists all registered subagents available in the system."""
    from backend.database import get_all_subagents
    agents = get_all_subagents()
    return json.dumps({"subagents": agents}, ensure_ascii=False)

def save_subagent_memory(key: str, value: str, chat_id: Optional[str] = None) -> str:
    """Saves or updates a persistent memory fact (key-value pair) for the active subagent."""
    if not chat_id:
        return json.dumps({"error": "Не удалось определить ID субагента для сохранения памяти (chat_id отсутствует)."}, ensure_ascii=False)
    
    from backend.database import db_save_subagent_memory
    from backend.rag import index_document
    
    clean_subagent_id = chat_id.strip().lower()
    
    # 1. Save in SQLite
    db_save_subagent_memory(clean_subagent_id, key, value)
    
    # 2. Index in Qdrant (RAG)
    doc_id = f"subagent_mem_{clean_subagent_id}_{key}"
    title = f"Память субагента ({clean_subagent_id}): {key}"
    success = index_document(
        doc_id=doc_id,
        title=title,
        text=f"Память субагента {clean_subagent_id} по ключу '{key}':\n{value}",
        source=f"subagent_memory_{clean_subagent_id}"
    )
    
    return json.dumps({
        "status": "success",
        "message": f"Информация успешно сохранена в базу данных и проиндексирована в RAG (успех RAG: {success})."
    }, ensure_ascii=False)

def get_subagent_memory(key: Optional[str] = None, chat_id: Optional[str] = None) -> str:
    """Retrieves saved memory facts for the active subagent."""
    if not chat_id:
        return json.dumps({"error": "Не удалось определить ID субагента для извлечения памяти (chat_id отсутствует)."}, ensure_ascii=False)
        
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
        return json.dumps({"results": [], "message": "Заметки по запросу '"+query+"' не найдены. Попробуйте sync_obsidian_vault."},
                ensure_ascii=False)
    results = []
    for h in hits:
        results.append(
            f"\U0001f4c4 **{h['title']}** (score: {h['score']:.2f})\n"
            f"  {h['content'][:300]}..."
            + (f"\n  Файл: {h['note_path']}" if h.get('note_path') else "")
        )
    return "\n\n".join(results)


def read_obsidian_note(note_path: str) -> str:
    """Read the full content of an Obsidian note by its vault-relative path."""
    async def _read():
        from backend.obsidian import read_note
        return await read_note(note_path)
    content = _run_async(_read())
    if content is None:
        return json.dumps({"error": f"Заметка '{note_path}' не найдена. Проверьте путь и подключение Obsidian."},
                ensure_ascii=False)
    return json.dumps({"path": note_path, "content": content}, ensure_ascii=False)


def create_obsidian_note(title: str, content: str, folder: str = "Vexa") -> str:
    """Create a new note in the Obsidian vault under the specified folder."""
    import re
    # Sanitize filename
    safe_title = re.sub(r'[<>:"/\\|?*]', '-', title).strip()
    note_path = f"{folder}/{safe_title}.md" if folder else f"{safe_title}.md"

    # Add a YAML frontmatter timestamp
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M")
    full_content = f"---\ncreated: {now}\ncreated_by: Vexa\n---\n\n# {title}\n\n{content}"

    async def _create():
        from backend.obsidian import create_note
        return await create_note(note_path, full_content)

    ok = _run_async(_create())
    if not ok:
        return json.dumps({"error": "Не удалось создать заметку. Obsidian запущен? Плагин Local REST API активен?"},
                ensure_ascii=False)
    # Also index the new note into RAG
    import hashlib
    doc_id = "obsidian_" + hashlib.sha1(note_path.encode()).hexdigest()
    from backend.rag import index_document
    index_document(doc_id, title, full_content, source="obsidian", note_path=note_path)

    return json.dumps({
        "status": "created",
        "path": note_path,
        "message": f"Заметка '{title}' создана в хранилище Obsidian: {note_path}"
    }, ensure_ascii=False)


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

def execute_tool(name: str, arguments: Dict[str, Any], chat_id: str = "default") -> str:
    logger.info(f"Executing tool '{name}' with args: {arguments}")

    if name.startswith("ctrader_") or name.startswith("bcm_"):
        try:
            from backend.bcm.tools import bcm_execute_tool
            return bcm_execute_tool(name, arguments)
        except ImportError:
            return json.dumps({"error": f"Tool '{name}' is not configured locally."}, ensure_ascii=False)

    if name == "get_system_stats":
        return get_system_stats()

    elif name == "get_weather":
        return get_weather(
            location=arguments.get("location", "Москва"),
            days_ahead=int(arguments.get("days_ahead", 0))
        )

    elif name == "get_current_time_israel":
        return get_current_time_israel()

    elif name == "set_timer":
        return set_timer(
            arguments.get("label", "Таймер"),
            int(arguments.get("duration_seconds", 60)),
            chat_id
        )

    elif name == "set_alarm":
        return set_alarm(
            arguments.get("time_str", ""),
            arguments.get("label", "Будильник"),
            chat_id
        )

    elif name == "cancel_timer_or_alarm":
        return cancel_timer_or_alarm(
            arguments.get("id", "")
        )

    elif name == "set_recurring_reminder":
        return set_recurring_reminder(
            arguments.get("label", "Напоминание"),
            float(arguments.get("interval_hours", 24)),
            chat_id
        )

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



    elif name == "web_search":
        return web_search(
            query=arguments.get("query", "")
        )

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

    elif name == "create_subagent":
        return create_subagent(
            subagent_id=arguments.get("subagent_id", ""),
            name=arguments.get("name", ""),
            system_prompt=arguments.get("system_prompt", ""),
            model=arguments.get("model"),
            role=arguments.get("role", "Specialist"),
            model_type=arguments.get("model_type", "external"),
            model_provider=arguments.get("model_provider", "openrouter"),
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
            folder=arguments.get("folder", "Vexa")
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
