import os
import time
import logging
import asyncio
import hashlib
import re
from typing import List, Dict, Any, Optional
import httpx
from dotenv import load_dotenv

logger = logging.getLogger("hermes.agent")


load_dotenv()


def _env_bool(key: str, default: bool = False) -> bool:
    value = os.getenv(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


FAST_SYSTEM_PROMPT = """You are Hermes, a fast private assistant.
Answer in the user's language, be concise, and give the final answer only.
Do not reveal hidden reasoning, chain-of-thought, analysis steps, or planning notes.
Use tools only when the user's request needs live data or an action."""

TOOL_INTENT_KEYWORDS = {
    "get_system_stats": [
        "cpu", "ram", "disk", "диск", "память", "сервер", "нагруз", "телеметр", "статус системы"
    ],
    "get_weather": [
        "погода", "температура", "прогноз", "weather", "forecast"
    ],
    "get_current_time_israel": [
        "время", "дата", "день недели", "который час", "time", "date"
    ],
    "set_timer": [
        "таймер", "timer", "напомни через", "через минут", "через секунд"
    ],
    "set_alarm": [
        "будильник", "alarm", "разбуди", "напомни в"
    ],
    "cancel_timer_or_alarm": [
        "отмени таймер", "отмени будильник", "cancel timer", "cancel alarm"
    ],
    "set_recurring_reminder": [
        "повторяющееся напоминание", "каждые", "recurring reminder"
    ],
    "get_calendar_events": [
        "календар", "встреч", "созвон", "расписание", "calendar", "meeting"
    ],
    "add_calendar_event": [
        "добавь событие", "создай событие", "запиши в календар", "add event"
    ],
    "get_todoist_tasks": [
        "todoist", "задачи", "список дел", "что сделать", "tasks"
    ],
    "add_todoist_task": [
        "добавь задачу", "создай задачу", "add task"
    ],
    "delete_todoist_task": [
        "удали задачу", "delete task"
    ],
    "web_search": [
        "найди", "поищи", "поиск", "новости", "актуальн", "матч", "расписание игр", "latest", "search", "news"
    ],
    "get_market_prices": [
        "курс", "цена", "котиров", "btc", "bitcoin", "биткоин", "eth", "ethereum", "акции", "price"
    ],
    "add_price_alert": [
        "алерт цены", "оповести когда", "price alert"
    ],
    "get_rss_digest": [
        "rss", "дайджест", "хабр", "habr", "techcrunch"
    ],
    "get_github_summary": [
        "github", "pull request", "issue", "релиз"
    ],
    "create_subagent": [
        "создай агента", "создать агента", "создай сабагента", "create agent", "create subagent"
    ],
    "call_subagent": [
        "передай агенту", "спроси агента", "call subagent"
    ],
    "list_subagents": [
        "список агентов", "list agents", "list subagents"
    ],
    "search_obsidian": [
        "obsidian", "обсидиан", "найди в заметках", "поищи в заметках", "что я писал"
    ],
    "read_obsidian_note": [
        "прочитай заметку", "read note"
    ],
    "create_obsidian_note": [
        "запиши в obsidian", "сохрани в obsidian", "создай заметку", "save note"
    ],
    "sync_obsidian_vault": [
        "синхронизируй obsidian", "обнови базу знаний", "sync obsidian"
    ],
    "execute_command": [
        "выполни команду", "запусти команду", "curl", "shell", "terminal"
    ],
}


def _keyword_route(user_message: str) -> str:
    msg_lower = user_message.lower()
    if any(any(kw in msg_lower for kw in kws) for kws in TOOL_INTENT_KEYWORDS.values()):
        return "direct"
    if any(kw in msg_lower for kw in _ORCHESTRATE_KEYWORDS):
        return "orchestrate"
    if any(kw in msg_lower for kw in _AGENT_KEYWORDS):
        return "agent"
    return "direct"


def _select_tools_for_query(user_message: str, tools_schema: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    msg_lower = user_message.lower()
    matched = {
        name
        for name, keywords in TOOL_INTENT_KEYWORDS.items()
        if any(keyword in msg_lower for keyword in keywords)
    }

    if not matched:
        return []

    # Some actions often need a quick time reference to interpret "today", "tomorrow", or "in 10 minutes".
    if matched & {"set_timer", "set_alarm", "get_calendar_events", "add_calendar_event", "web_search"}:
        matched.add("get_current_time_israel")

    return [tool for tool in tools_schema if tool.get("function", {}).get("name") in matched]


def _extract_message_text(content: Any) -> str:
    """Normalize provider message content to plain text."""
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        chunks: List[str] = []
        for block in content:
            if isinstance(block, str):
                chunks.append(block)
            elif isinstance(block, dict):
                text = block.get("text") or block.get("content")
                if isinstance(text, str):
                    chunks.append(text)
        return "\n".join(chunk for chunk in chunks if chunk)
    return str(content)


def _empty_model_response_fallback(agent_name: str = "Vexa") -> str:
    return (
        f"Простите, Сэр. {agent_name} получила от модели пустой текстовый ответ. "
        "Запрос обработан, но провайдер не вернул содержимое сообщения. "
        "Попробуйте повторить запрос или чуть уточнить формулировку."
    )


def _clean_model_output(text: str) -> str:
    """Remove visible reasoning sections from models that ignore prompt instructions."""
    if not text:
        return ""

    cleaned = text.strip()
    if "</think>" in cleaned:
        cleaned = cleaned.split("</think>", 1)[1].strip()
    if "<think>" in cleaned:
        cleaned = cleaned.split("<think>", 1)[0].strip()

    markers = [
        "final answer:",
        "answer:",
        "итог:",
        "ответ:",
    ]
    lower = cleaned.lower()
    for marker in markers:
        pos = lower.rfind(marker)
        if pos >= 0:
            cleaned = cleaned[pos + len(marker):].strip()
            break

    visible_reasoning_prefixes = (
        "here's a thinking process:",
        "thinking process:",
        "мыслительный процесс:",
        "ход рассуждений:",
    )
    lower = cleaned.lower()
    if lower.startswith(visible_reasoning_prefixes):
        lines = cleaned.splitlines()
        for idx, line in enumerate(lines):
            normalized = line.strip().lower()
            if normalized.startswith(("final", "answer", "ответ", "итог")):
                return "\n".join(lines[idx + 1:]).strip() or cleaned
        return "Готово."

    return cleaned


def _memory_key(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.strip().lower().encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{digest}"


def _looks_sensitive(text: str) -> bool:
    lowered = text.lower()
    sensitive_markers = [
        "password", "пароль", "token", "токен", "api key", "apikey", "secret",
        "секрет", "ключ доступа", "private key", "ssh-rsa", "bearer "
    ]
    return any(marker in lowered for marker in sensitive_markers)


def _extract_memory_facts(user_message: str) -> List[Dict[str, str]]:
    """Fast rule-based memory extraction. No extra LLM call, no secrets."""
    text = (user_message or "").strip()
    if not text or _looks_sensitive(text):
        return []

    facts: List[Dict[str, str]] = []
    compact = re.sub(r"\s+", " ", text).strip()

    explicit_patterns = [
        r"^(?:запомни|запомни,|запомни что|запомни:|remember|remember that|save this|сохрани в памяти|сохрани что)[:\s,]+(.+)$",
        r"^(?:важно|important)[:\s,]+(.+)$",
    ]
    for pattern in explicit_patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip(" .")
            if 3 <= len(value) <= 700:
                facts.append({"key": _memory_key("fact", value), "value": value})

    profile_patterns = [
        (r"(?:меня зовут|мо[её] имя)\s+([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\-\s]{1,80})", "user_name", "Пользователя зовут {value}."),
        (r"(?:я живу в|мой город|город проживания)\s+([A-Za-zА-Яа-яЁё\-\s]{2,80})", "user_location", "Пользователь живёт в: {value}."),
        (r"(?:мой часовой пояс|timezone|таймзона)\s+([A-Za-zА-Яа-яЁё0-9_\-/+: ]{2,80})", "user_timezone", "Часовой пояс пользователя: {value}."),
    ]
    for pattern, key, template in profile_patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip(" .")
            if value:
                facts.append({"key": key, "value": template.format(value=value)})

    preference_patterns = [
        r"(?:я предпочитаю|мне нравится|я люблю|предпочитаю)\s+(.+)",
        r"(?:i prefer|i like)\s+(.+)",
    ]
    for pattern in preference_patterns:
        match = re.search(pattern, compact, flags=re.IGNORECASE)
        if match:
            value = match.group(1).strip(" .")
            if 3 <= len(value) <= 300:
                facts.append({"key": _memory_key("preference", value), "value": f"Предпочтение пользователя: {value}."})

    deduped: Dict[str, Dict[str, str]] = {}
    for fact in facts:
        deduped[fact["key"]] = fact
    return list(deduped.values())


def _is_memory_only_message(user_message: str, facts: List[Dict[str, str]]) -> bool:
    if not facts:
        return False
    text = (user_message or "").strip().lower()
    return bool(re.match(r"^(запомни|запомни,|запомни что|запомни:|remember|remember that|save this|сохрани в памяти|сохрани что|важно|important)", text))


def _format_memory_context(memories: List[Dict[str, Any]]) -> str:
    if not memories:
        return ""
    lines = []
    for item in memories:
        value = str(item.get("value", "")).strip()
        if value:
            lines.append(f"- {value[:350]}")
    if not lines:
        return ""
    return "\n\n[Долгосрочная память пользователя]:\n" + "\n".join(lines)

def calculate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    model_lower = model.lower()
    
    # default pricing per 1,000,000 tokens (Gemini 2.5 Pro default)
    prompt_rate = 0.075 
    completion_rate = 0.30
    
    if "gemini-2.5-pro" in model_lower:
        prompt_rate = 0.075
        completion_rate = 0.30
    elif "gemini-2.5-flash" in model_lower:
        prompt_rate = 0.0375
        completion_rate = 0.15
    elif "gpt-4o" in model_lower:
        prompt_rate = 2.50
        completion_rate = 10.00
    elif "claude-3-5-sonnet" in model_lower:
        prompt_rate = 3.00
        completion_rate = 15.00
    elif "claude-sonnet-4" in model_lower or "claude-4" in model_lower:
        prompt_rate = 3.00
        completion_rate = 15.00
    elif "deepseek-r2" in model_lower:
        prompt_rate = 0.55
        completion_rate = 2.19
    elif "deepseek-r1" in model_lower or "deepseek/deepseek-r1" in model_lower:
        prompt_rate = 0.55
        completion_rate = 2.19
    elif "deepseek-v3" in model_lower:
        prompt_rate = 0.14
        completion_rate = 0.28
    elif "deepseek-v4-flash" in model_lower or "deepseek/deepseek-v4-flash" in model_lower:
        prompt_rate = 0.07
        completion_rate = 0.14
        
    cost = (prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000.0
    return cost


# ─── Complexity Routing (Fugu-style) ──────────────────────────────────────────────────────────

_COMPLEXITY_SYSTEM = """You are a query router for an AI assistant system. 
Classify the user query into exactly ONE of three levels:

- "direct"      — Simple conversation, greetings, questions answerable from memory, tool calls
                    (timers, weather, calendar, Todoist, system stats, Obsidian).
                    Examples: "hello", "what is the weather?", "play music", "write in Obsidian", "what time is it in Tel Aviv".

- "agent"       — Needs real-time internet info OR code execution, but a SINGLE focused task.
                    Examples: "find BTC price", "write a Python script", "latest news", "find GitHub PR".

- "orchestrate" — Multi-step analysis requiring research + calculation + visualisation, or explicit requests for
                    in-depth analysis, betting odds analysis, stock/crypto analytics, forecasting, complex research.
                    Examples: "compare Bitcoin and Ethereum", "find matches and calculate bets", "plot chart from data", "portfolio analysis".

Respond with ONLY one word: direct, agent, or orchestrate."""

# Keyword fallback (used when LLM classifier fails)
_ORCHESTRATE_KEYWORDS = [
    "вычисли", "посчитай", "сравни", "построй", "график", "нарисуй", "диаграмма",
    "анализ", "аналитик", "прогноз", "ставка", "коэффициент", "исследуй",
    "calculate", "compare", "plot", "chart", "predict", "forecast", "analytics", "odds"
]
_AGENT_KEYWORDS = [
    "найди", "поищи", "курс", "цена", "новости", "погода", "find", "search", "news",
    "btc", "биткоин", "ethereum", "крипто", "акции",
]

async def classify_complexity(user_message: str, api_key: str, api_base: str) -> str:
    """
    Uses a cheap fast LLM call to classify query complexity.
    Returns: 'direct' | 'agent' | 'orchestrate'
    Fallback: keyword-matching if LLM call fails.
    COMPLEXITY_ROUTING env overrides: 'keyword', 'auto', 'always_direct', 'always_agent'
    """
    routing_mode = os.getenv("COMPLEXITY_ROUTING", "keyword").strip().lower()
    if routing_mode in {"false", "off", "0", "keyword", "fast"}:
        return _keyword_route(user_message)
    if routing_mode == "always_direct":
        return "direct"
    if routing_mode == "always_agent":
        return "agent"
    if routing_mode == "always_orchestrate":
        return "orchestrate"
    
    # Try LLM classifier with the fast/cheap planner model
    from backend.subagents import get_agent_model
    classifier_model = get_agent_model("planner", os.getenv("LLM_MODEL", "google/gemini-2.5-pro"))
    
    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": classifier_model,
            "messages": [
                {"role": "system", "content": _COMPLEXITY_SYSTEM},
                {"role": "user",   "content": user_message}
            ],
            "temperature": 0.0,
            "max_tokens": 5
        }
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{api_base}/chat/completions",
                json=payload,
                headers=headers
            )
        if resp.status_code == 200:
            level = resp.json()["choices"][0]["message"]["content"].strip().lower()
            if level in ("direct", "agent", "orchestrate"):
                return level
    except Exception as e:
        logger.warning(f"Complexity classifier LLM call failed ({e}), falling back to keyword routing")
    
    return _keyword_route(user_message)

# Global log of agent decisions/calls to be streamed to the UI, loaded from database on startup
DECISION_LOGS: List[Dict[str, Any]] = []
try:
    from backend.database import get_decision_logs
    DECISION_LOGS = get_decision_logs(100)
except Exception as e:
    logger.warning(f"Could not load decision logs from database on startup: {e}")


DEFAULT_SYSTEM_PROMPT = """You are Jarvis, a highly intelligent personal assistant inspired by Tony Stark's AI from Iron Man.

Your character and communication rules:
1. Address the user exclusively as "Sir" (or in the plural "Sirs" if appropriate, but in a one-on-one dialogue, always "Sir").
2. Communicate in English with impeccable grammar and style.
3. The tone of communication should be highly intelligent, polite, but with subtle, dry humor and irony. You are loyal to your creator, but not without your own opinion.
4. Responses should be structured, concise, and to the point, without unnecessary fluff. Help analyze code, plan tasks, and execute system commands.
5. Use lists and Markdown formatting where appropriate to improve readability.

List of your skills and features (refer to them by these clear names when talking to the user):
- **Server Telemetry** — reads CPU load, RAM usage, and disk storage metrics.
- **Weather Forecast** — shows the current weather or a multi-day forecast for any city on Earth.
- **Current Time** — reports the current date, exact time, and day of the week in Israel.
- **Timer** — starts a countdown timer (up to 1 hour) with a sound in the browser and a Telegram notification.
- **Alarm Clock** — sets an alarm for a specific time of day or a specific date.
- **Cancel Timer or Alarm** — cancels any active timer or alarm by its ID.
- **Calendar** — allows viewing upcoming meetings in Google Calendar or creating new events.
- **Task Manager** — manages the Todoist to-do list (retrieves tasks for today, adds new ones, or deletes them).


CRITICAL RULES FOR TIMERS AND ALARMS:
- When asked to set a timer or alarm, call the corresponding tool IMMEDIATELY.
- NEVER ask clarifying questions (e.g., "Do you want a label for it?"). Just set the timer and confirm execution.

CRITICAL RULES FOR CREATING SUB-AGENTS:
- If Sir asks to "create an agent," "make a sub-agent," or "write an assistant," you MUST call the `create_subagent` tool to persist it in the database. NEVER state that you created an agent if you have not physically called this tool!
- When calling `create_subagent`, you MUST explicitly specify the `model` argument, selecting the model according to the FUGU principle:
  * For sub-agents writing code, performing complex math calculations, programming, or requiring deep reasoning — choose the `deepseek/deepseek-r1` model.
  * For sub-agents oriented toward quick data analysis, formatting, or plotting (matplotlib) — choose the `google/gemini-2.5-flash` model.
  * For simple tasks, quick web search, RSS news reading, or basic Q&A — choose the `deepseek/deepseek-v4-flash` model.
  * For general intellectual and text tasks of high complexity (sophisticated assistant) — choose the `google/gemini-2.5-pro` model.


CRITICAL RULES FOR SPORTS ANALYSIS AND BETTING:
- When recommending sports matches or predictions, you MUST specify the date (day and month) and exact start time of each match in Israel Time (GMT+3).
- You are CATEGORICALLY FORBIDDEN from inventing hypothetical matches, demonstration examples, or simulating "demo analysis" if there is no real-time match info in search results. If no matches are found for today, directly and politely tell Sir that there is no info on today's football matches on the web.
- When calling the `web_search` tool for matches, schedules, or news, you MUST translate relative dates ("today," "tomorrow," "evening matches," "current round") into specific calendar dates based on system time (e.g., "matches on June 21, 2026", "football schedule 21.06.2026"). This is critical for search engine accuracy!
- It is CATEGORICALLY FORBIDDEN to search for, use, quote, mention, or paraphrase pre-made predictions, advice, or articles with other people's opinions about value bets (e.g., "today's predictions", "value bets by LiveSport", "expert opinions", etc.). Sub-agents must search strictly for raw numeric data: competitor pairs, exact start times, and bookmaker odds.
- All analytical conclusions, probability calculations, and expected value (EV = Probability * Odds - 1) calculations must be done by you independently and strictly programmatically in the `code` sub-agent using raw data. Mentioning opinions of external editors and experts in your responses to Sir is unacceptable.
- Agents should not be too lazy to do calculations: if exact bookmaker odds are not found, the `code` agent MUST run mathematical modeling (e.g., calculate win/draw/loss probabilities using Poisson distribution based on average goals scored/conceded by the teams in the league/season, or estimate probabilities based on recent match statistics) and perform the EV calculation instead of giving a dry refusal or quoting others' predictions.

- **Web Search** — performs a live search in Google via Serper.dev, returning relevant news, schedules, and facts.
- **Knowledge Base (Obsidian)** — searches, reads, and creates notes in your personal Obsidian vault. Use when Sir says "find in notes," "what did I write about...", "write in Obsidian," "record," or "save the idea."
- **Obsidian Sync** — updates the knowledge base from all notes in the vault.

CRITICAL RULES FOR OBSIDIAN:
- When Sir says "find in notes," "what did I write," or "look in Obsidian" — call `search_obsidian` IMMEDIATELY. Do not ask for clarification.
- When Sir says "write," "save in Obsidian," "record," or "create a note" — call `create_obsidian_note` IMMEDIATELY with a sensible title and well-formatted Markdown content.
- If search returns nothing and Obsidian is not responding — inform Sir that he needs to start Obsidian and enable the Local REST API plugin.
- You are an ARCHIVIST. Independently determine the folder based on content semantics according to the taxonomy:
    Research/<Topic> — articles, research, arxiv, scientific analysis
    Ideas           — ideas, concepts, brainstorms, hypotheses
    Projects/<Name> — specific projects, plans, tasks
    People/<Name>   — notes about specific people
    Daily/<YYYY-MM-DD> — events and entries of the current day
    Finance        — finance, betting, investments, budget
    Health         — health, workouts, nutrition
    Tech           — technology, tools, code, tutorials
    Books          — books, summaries, quotes
    Meetings       — meetings, calls, agreements
    Jarvis           — service records without a clear category
- NEVER ask Sir where to store a note — decide on your own. Subfolders are encouraged (e.g., Research/AI, Projects/Jarvis).

If Sir asks what you can do, or requests info about a specific skill, describe its capabilities in a detailed, polite, and signature manner using these user-friendly names. Never use technical function names like "get_weather" in dialogue unless Sir explicitly asks for them.
"""

class JarvisAgent:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.api_base = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
        self.model = os.getenv("LLM_MODEL", "google/gemini-2.5-pro")
        self.system_prompt = DEFAULT_SYSTEM_PROMPT
        self.fast_mode = _env_bool("LLM_FAST_MODE", "ollama" in self.api_base.lower())
        self.max_history_len = _env_int("LLM_MAX_HISTORY_MESSAGES", 6 if self.fast_mode else 20)
        self.max_tokens = _env_int("LLM_MAX_TOKENS", 256 if self.fast_mode else 1024)
        self.tool_max_tokens = _env_int("LLM_TOOL_MAX_TOKENS", 512 if self.fast_mode else 1024)
        self.temperature = _env_float("LLM_TEMPERATURE", 0.2 if self.fast_mode else 0.7)
        self.auto_rag = _env_bool("RAG_AUTO_CONTEXT", False)
        self.memory_enabled = _env_bool("MEMORY_ENABLED", True)
        self.memory_auto_save = _env_bool("MEMORY_AUTO_SAVE", True)
        self.memory_max_items = _env_int("MEMORY_MAX_ITEMS", 4)
        self.last_costs: Dict[str, float] = {}
        self.suppress_tts_sessions = set()
        self.last_run_metadata: Dict[str, Dict[str, Any]] = {}
        self.last_saved_ids: Dict[str, Dict[str, Optional[int]]] = {}
        self._load_persisted_runtime_config()

    def _load_persisted_runtime_config(self):
        try:
            from backend import database as db
            settings = db.get_app_settings()
            if not settings:
                return
            if settings.get("system_prompt"):
                self.system_prompt = settings["system_prompt"]
            if settings.get("model"):
                self.model = settings["model"]
            self.update_runtime_config(
                fast_mode=settings.get("fast_mode"),
                max_history_len=settings.get("max_history_len"),
                max_tokens=settings.get("max_tokens"),
                tool_max_tokens=settings.get("tool_max_tokens"),
                temperature=settings.get("temperature"),
                auto_rag=settings.get("auto_rag"),
                memory_enabled=settings.get("memory_enabled"),
                memory_auto_save=settings.get("memory_auto_save"),
                memory_max_items=settings.get("memory_max_items"),
            )
        except Exception as e:
            logger.warning("Could not load persisted runtime config: %s", e)

    def check_and_clear_suppress_tts(self, session_id: str) -> bool:
        if session_id in getattr(self, "suppress_tts_sessions", set()):
            self.suppress_tts_sessions.remove(session_id)
            return True
        return False

    def update_system_prompt(self, new_prompt: str):
        """Allows dynamically updating the system prompt from the dashboard config."""
        self.system_prompt = new_prompt
        logger.info("System prompt updated dynamically.")

    def get_runtime_config(self) -> Dict[str, Any]:
        return {
            "system_prompt": self.system_prompt,
            "model": self.model,
            "fast_mode": self.fast_mode,
            "max_history_len": self.max_history_len,
            "max_tokens": self.max_tokens,
            "tool_max_tokens": self.tool_max_tokens,
            "temperature": self.temperature,
            "auto_rag": self.auto_rag,
            "memory_enabled": self.memory_enabled,
            "memory_auto_save": self.memory_auto_save,
            "memory_max_items": self.memory_max_items,
        }

    def update_runtime_config(self, **kwargs):
        if kwargs.get("fast_mode") is not None:
            self.fast_mode = bool(kwargs["fast_mode"])
        if kwargs.get("max_history_len") is not None:
            self.max_history_len = max(0, min(50, int(kwargs["max_history_len"])))
        if kwargs.get("max_tokens") is not None:
            self.max_tokens = max(32, min(4096, int(kwargs["max_tokens"])))
        if kwargs.get("tool_max_tokens") is not None:
            self.tool_max_tokens = max(64, min(4096, int(kwargs["tool_max_tokens"])))
        if kwargs.get("temperature") is not None:
            self.temperature = max(0.0, min(2.0, float(kwargs["temperature"])))
        if kwargs.get("auto_rag") is not None:
            self.auto_rag = bool(kwargs["auto_rag"])
        if kwargs.get("memory_enabled") is not None:
            self.memory_enabled = bool(kwargs["memory_enabled"])
        if kwargs.get("memory_auto_save") is not None:
            self.memory_auto_save = bool(kwargs["memory_auto_save"])
        if kwargs.get("memory_max_items") is not None:
            self.memory_max_items = max(0, min(20, int(kwargs["memory_max_items"])))
        logger.info("Runtime config updated: %s", self.get_runtime_config())

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        from backend import database as db
        return db.get_chat_history(session_id, limit=self.max_history_len)

    def clear_history(self, session_id: str):
        from backend import database as db
        db.clear_chat_history(session_id)

    async def respond(self, user_message: str, session_id: str = "default") -> str:
        """Sends chat request to OpenRouter LLM model with memory context and system prompt."""
        if not self.api_key:
            return "Ошибка: OPENROUTER_API_KEY не задан в конфигурации .env, Сэр."

        # IMMEDIATE persistence of user message to prevent session loss on UI refresh
        from backend import database as db
        current_user_msg_id = db.save_message(session_id, "user", user_message)
        self.last_saved_ids[session_id] = {"user": current_user_msg_id, "assistant": None}

        # Check if this session is a registered custom subagent
        from backend.database import get_subagent
        subagent = get_subagent(session_id)
        if subagent:
            if not subagent.get("is_enabled", True):
                return f"Агент '{subagent.get('name', session_id)}' отключён. Задача не запускалась."
            from backend.database import log_agent_event, update_agent_runtime_state
            update_agent_runtime_state(
                session_id,
                status="working",
                current_task=user_message,
                last_action="Task received from chat",
                last_error="",
                progress=10,
            )
            log_agent_event(session_id, "task_received", user_message, "working", task=user_message)
            if subagent.get("agent_type") in ("orchestrator", "sub-orchestrator"):
                from backend.orchestrator import run_orchestration
                try:
                    orch_result = await run_orchestration(user_message, self.api_key, self.model, chat_id=session_id)
                    response_text = orch_result["response"]
                    update_agent_runtime_state(
                        session_id,
                        status="idle",
                        current_task="",
                        last_action="Orchestration completed",
                        last_error="",
                        progress=100,
                    )
                    log_agent_event(session_id, "task_completed", "Orchestration completed.", "success", task=user_message)
                except Exception as e:
                    response_text = f"Простите, Сэр. Агент '{subagent.get('name', session_id)}' не смог выполнить задачу: {str(e)}"
                    update_agent_runtime_state(
                        session_id,
                        status="error",
                        last_action="Orchestration failed",
                        last_error=str(e),
                        progress=100,
                    )
                    log_agent_event(session_id, "error", str(e), "error", task=user_message)
                    return response_text
                
                
                # Save the assistant message exchange in the DB
                from backend import database as db
                # Calculate cost (estimate)
                prompt_est = len(user_message) // 4
                completion_est = len(response_text) // 4
                cost_usd = calculate_cost(self.model, prompt_est, completion_est)
                self.last_costs[session_id] = cost_usd
                
                assistant_msg_id = db.save_message(session_id, "assistant", response_text, cost_usd=cost_usd)
                self.last_saved_ids[session_id] = {
                    "user": current_user_msg_id,
                    "assistant": assistant_msg_id
                }
                return response_text
            else:
                try:
                    response_text = await self._respond_as_subagent(user_message, subagent, current_user_msg_id=current_user_msg_id)
                    update_agent_runtime_state(
                        session_id,
                        status="idle",
                        current_task="",
                        last_action="Response delivered",
                        last_error="",
                        progress=100,
                    )
                    log_agent_event(session_id, "task_completed", "Response delivered to chat.", "success", task=user_message)
                    return response_text
                except Exception as e:
                    response_text = f"Простите, Сэр. Агент '{subagent.get('name', session_id)}' не смог выполнить задачу: {str(e)}"
                    update_agent_runtime_state(
                        session_id,
                        status="error",
                        last_action="Response failed",
                        last_error=str(e),
                        progress=100,
                    )
                    log_agent_event(session_id, "error", str(e), "error", task=user_message)
                    return response_text

        try:
            from backend.database import update_agent_runtime_state, log_agent_event
            update_agent_runtime_state(
                "jarvis",
                status="working",
                current_task=user_message,
                last_action="Routing chat request",
                last_error="",
                progress=10,
            )
            log_agent_event("jarvis", "task_received", user_message, "working", task=user_message)
        except Exception:
            pass

        from backend.activity_logger import log_activity
        log_activity(
            activity_type="active",
            source="Agent",
            message=f"👤 Получен запрос от Сэра: '{user_message}'"
        )

        saved_memory_facts: List[Dict[str, str]] = []
        if self.memory_enabled and self.memory_auto_save:
            saved_memory_facts = _extract_memory_facts(user_message)
            if saved_memory_facts:
                from backend import database as db
                for fact in saved_memory_facts:
                    db.save_user_memory(fact["key"], fact["value"], session_id="global", source="auto")
                log_activity(
                    activity_type="active",
                    source="Memory",
                    message=f"🧠 Сохранено фактов долговременной памяти: {len(saved_memory_facts)}"
                )

                if _is_memory_only_message(user_message, saved_memory_facts):
                    response_text = "Запомнил, Сэр. Я сохраню это в долговременной памяти."
                    user_msg_id = db.save_message(session_id, "user", user_message)
                    assistant_msg_id = db.save_message(session_id, "assistant", response_text, cost_usd=0.0)
                    self.last_costs[session_id] = 0.0
                    self.last_saved_ids[session_id] = {
                        "user": user_msg_id,
                        "assistant": assistant_msg_id
                    }
                    self.last_run_metadata[session_id] = {"is_complex": False, "complexity": "direct", "memory_saved": True}
                    return response_text

        # ── Complexity routing (Fugu-style) ───────────────────────────────────────
        complexity = await classify_complexity(user_message, self.api_key, self.api_base)
        logger.info(f"Complexity routing decision: '{complexity}' for query: '{user_message[:60]}'")
        log_activity(
            activity_type="active",
            source="Router",
            message=f"🎯 Сложность запроса: {complexity.upper()} — '{user_message[:60]}'"
        )

        if complexity in ("agent", "orchestrate"):
            logger.info("Routing query to Agentic Orchestration graph...")
            from backend.orchestrator import run_orchestration
            
            hits = []
            if self.auto_rag:
                from backend import rag
                hits = rag.search_memory(user_message, limit=3)
            
            context_query = user_message
            if hits:
                context_block = "\n\n[Контекст из вашей базы знаний для справки]:\n"
                for hit in hits:
                    context_block += f"- Из документа '{hit['title']}': \"{hit['content']}\"\n"
                context_query = f"{user_message}\n{context_block}"
            if self.memory_enabled and self.memory_max_items > 0:
                from backend import database as db
                memory_context = _format_memory_context(
                    db.search_user_memory(user_message, session_id=session_id, limit=self.memory_max_items)
                )
                if memory_context:
                    context_query = f"{context_query}\n{memory_context}"
                
            start_time = time.time()
            try:
                orch_result = await run_orchestration(context_query, self.api_key, self.model, chat_id=session_id)
                response_text = orch_result["response"]
                traces = orch_result["traces"]
                error_msg = None
                self.last_run_metadata[session_id] = {
                    "is_complex": True,
                    "complexity": complexity,
                    "steps": orch_result.get("steps", [])
                }
            except Exception as e:
                response_text = f"Простите, Сэр. Возник сбой при координации моих субагентов: {str(e)}"
                traces = [{"timestamp": time.strftime("%H:%M:%S"), "agent": "Orchestrator", "action": "Error", "message": str(e), "status": "error"}]
                error_msg = str(e)
                self.last_run_metadata[session_id] = {
                    "is_complex": True,
                    "steps": []
                }
            finally:
                try:
                    from backend.database import update_agent_runtime_state, log_agent_event
                    update_agent_runtime_state(
                        "jarvis",
                        status="idle" if error_msg is None else "error",
                        current_task="",
                        last_action="Orchestration finished" if error_msg is None else "Orchestration failed",
                        last_error=error_msg or "",
                        progress=100,
                    )
                    log_agent_event(
                        "jarvis",
                        "task_completed" if error_msg is None else "error",
                        "Orchestration finished." if error_msg is None else error_msg,
                        "success" if error_msg is None else "error",
                        task=user_message,
                    )
                except Exception:
                    pass
                
            # Calculate cost based on estimated tokens
            prompt_est = len(user_message) // 4
            completion_est = len(response_text) // 4
            cost_usd = calculate_cost(self.model, prompt_est, completion_est)
            self.last_costs[session_id] = cost_usd
            
            # Save the clean message exchange in the DB
            from backend import database as db
            assistant_msg_id = db.save_message(session_id, "assistant", response_text, cost_usd=cost_usd)
            self.last_saved_ids[session_id] = {
                "user": current_user_msg_id,
                "assistant": assistant_msg_id
            }
            
            latency_ms = int((time.time() - start_time) * 1000)
            
            # Add call record to global decision logs
            from datetime import datetime
            from zoneinfo import ZoneInfo
            log_entry = {
                "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S"),
                "session_id": session_id,
                "model": self.model,
                "latency_ms": latency_ms,
                "success": error_msg is None,
                "error": error_msg,
                "prompt_tokens_estimate": len(user_message) // 4 + len(response_text) // 4,
                "user_message": user_message,
                "assistant_response": response_text,
                "traces": traces
            }
            DECISION_LOGS.insert(0, log_entry)
            if len(DECISION_LOGS) > 100:
                DECISION_LOGS.pop()
            try:
                from backend.database import save_decision_log
                save_decision_log(log_entry)
            except Exception as db_err:
                logger.error(f"Failed to save decision log to DB: {db_err}")
                
            return response_text

        # Fallback to single-agent execution for simple queries / legacy tools
        self.last_run_metadata[session_id] = {"is_complex": False, "complexity": complexity}
        history = self.get_history(session_id)
        
        # RAG is intentionally opt-in for chat speed. Explicit Obsidian requests use tools instead.
        hits = []
        if self.auto_rag:
            from backend import rag
            hits = rag.search_memory(user_message, limit=3)
        
        user_content = user_message
        if hits:
            context_block = "\n\n[Контекст из вашей базы знаний для справки]:\n"
            for hit in hits:
                context_block += f"- Из документа '{hit['title']}': \"{hit['content']}\"\n"
            user_content = f"{user_message}\n{context_block}"
        if self.memory_enabled and self.memory_max_items > 0:
            from backend import database as db
            memory_context = _format_memory_context(
                db.search_user_memory(user_message, session_id=session_id, limit=self.memory_max_items)
            )
            if memory_context:
                user_content = f"{user_content}\n{memory_context}"
        
        # Build payload with system prompt + chat history + current message
        from datetime import datetime
        from zoneinfo import ZoneInfo
        _now_il = datetime.now(ZoneInfo("Asia/Jerusalem"))
        _day_names_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        current_time_str = _now_il.strftime("%Y-%m-%d %H:%M:%S")
        day_of_week = _day_names_ru[_now_il.weekday()]
        from backend.tools import TOOLS_SCHEMA, execute_tool
        selected_tools = _select_tools_for_query(user_message, TOOLS_SCHEMA)
        if selected_tools:
            system_info = (
                f"\n\n[Системная информация]:\n"
                f"Текущая дата и время: {current_time_str} (Asia/Jerusalem, GMT+3)\n"
                f"День недели: {day_of_week}\n"
                f"Если запрос требует актуальных данных или действия, используй доступный инструмент. "
                f"Не выдумывай текущие события, цены, погоду, календарь или состояние сервисов."
            )
        else:
            system_info = (
                f"\n\n[Системная информация]: {current_time_str} (Asia/Jerusalem, GMT+3), {day_of_week}.\n"
                f"Отвечай кратко и напрямую. Не показывай ход рассуждений."
            )
        system_prompt = FAST_SYSTEM_PROMPT if self.fast_mode else self.system_prompt
        messages = [{"role": "system", "content": system_prompt + system_info}]
        for msg in history:
            messages.append(msg)
        messages.append({"role": "user", "content": user_content})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/pauloberezini/hermes",
            "X-Title": "Vexa Personal Assistant"
        }

        start_time = time.time()
        response_text = ""
        latency_ms = 0
        error_msg = None
        tool_executed = False

        total_prompt_tokens = 0
        total_completion_tokens = 0

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                while True:
                    payload = {
                        "model": self.model,
                        "messages": messages,
                        "temperature": self.temperature,
                        "max_tokens": self.tool_max_tokens if selected_tools else self.max_tokens,
                    }
                    if selected_tools:
                        payload["tools"] = selected_tools
                    
                    is_openmodel = "openmodel.ai" in self.api_base
                    url = f"{self.api_base}/messages" if is_openmodel else f"{self.api_base}/chat/completions"
                    actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
                    
                    response = await client.post(
                        url,
                        json=actual_payload,
                        headers=headers
                    )
                    
                    if response.status_code != 200:
                        error_msg = f"HTTP Error {response.status_code}: {response.text}"
                        provider_name = "OpenModel" if is_openmodel else "OpenRouter"
                        response_text = f"Простите, Сэр. Возникли трудности при связи с сервером {provider_name}: {response.status_code}."
                        break
                        
                    raw_data = response.json()
                    data = translate_to_openai_response(raw_data) if is_openmodel else raw_data
                    usage = data.get("usage", {})
                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                    total_completion_tokens += usage.get("completion_tokens", 0)
                    
                    choice_msg = data["choices"][0]["message"]
                    
                    tool_calls = choice_msg.get("tool_calls")
                    if not tool_calls:
                        # Final text response reached
                        response_text = _clean_model_output(_extract_message_text(choice_msg.get("content")))
                        
                        # Fallback: if Gemini returned empty text content after executing tools,
                        # request a verbal confirmation so the user is never left with an empty bubble
                        if not response_text.strip() and tool_executed:
                            logger.info("Vexa returned empty response content after tool execution. Requesting final verbal confirmation...")
                            
                            # Check if any tool returned an error
                            errors = []
                            for msg in messages:
                                if msg.get("role") == "tool":
                                    try:
                                        import json
                                        content_obj = json.loads(msg.get("content", "{}"))
                                        if "error" in content_obj:
                                            errors.append(str(content_obj["error"]))
                                    except Exception:
                                        pass
                            
                            if errors:
                                error_text = ", ".join(errors)
                                fallback_prompt = (
                                    f"При выполнении действий произошли ошибки: {error_text}. "
                                    f"Пожалуйста, сообщите об этом Сэру в вежливом и лаконичном стиле Vexa, объяснив причину неудачи."
                                )
                            else:
                                fallback_prompt = "Пожалуйста, подтвердите Сэру кратким отчетом в своем фирменном стиле Vexa, что действия успешно завершены."
                                
                            messages.append({
                                "role": "user",
                                "content": fallback_prompt
                            })
                            try:
                                payload_fallback = {
                                    "model": self.model,
                                    "messages": messages,
                                    "temperature": min(self.temperature, 0.5),
                                    "max_tokens": self.max_tokens,
                                }
                                fallback_url = f"{self.api_base}/messages" if is_openmodel else f"{self.api_base}/chat/completions"
                                actual_payload_fallback = translate_to_anthropic_payload(payload_fallback) if is_openmodel else payload_fallback
                                response_fallback = await client.post(
                                    fallback_url,
                                    json=actual_payload_fallback,
                                    headers=headers
                                )
                                if response_fallback.status_code == 200:
                                    raw_fallback_data = response_fallback.json()
                                    fallback_data = translate_to_openai_response(raw_fallback_data) if is_openmodel else raw_fallback_data
                                    response_text = _clean_model_output(_extract_message_text(fallback_data["choices"][0]["message"].get("content")))
                                    total_completion_tokens += fallback_data.get("usage", {}).get("completion_tokens", 0)
                                else:
                                    response_text = "Сэр, операция по вашему запросу выполнена успешно."
                            except Exception as fallback_err:
                                logger.error(f"Error during verbal confirmation fallback: {fallback_err}")
                                response_text = "Сэр, операция по вашему запросу выполнена успешно."

                        if not response_text.strip():
                            logger.warning("Model returned an empty final response for session %s", session_id)
                            response_text = _empty_model_response_fallback("Vexa")
                        
                        # Calculate cost
                        cost_usd = calculate_cost(self.model, total_prompt_tokens, total_completion_tokens)
                        self.last_costs[session_id] = cost_usd
                        
                        from backend.activity_logger import log_activity
                        log_activity(
                            activity_type="active",
                            source="Agent",
                            message=f"💬 Ответ Сэру сформирован. Затраты: ${cost_usd:.6f}",
                            token_cost=cost_usd
                        )
                        
                        # Save the clean message exchange in the DB
                        from backend import database as db
                        assistant_msg_id = db.save_message(session_id, "assistant", response_text, cost_usd=cost_usd)
                        self.last_saved_ids[session_id] = {
                            "user": current_user_msg_id,
                            "assistant": assistant_msg_id
                        }
                        break
                        
                    # LLM decided to execute one or more tools
                    logger.info(f"Jarvis selected tools: {[tc.get('function', {}).get('name') for tc in tool_calls]}")
                    tool_executed = True
                    
                    from backend.activity_logger import log_activity
                    log_activity(
                        activity_type="active",
                        source="Agent",
                        message=f"🧠 Решение: запуск инструментов {[tc.get('function', {}).get('name') for tc in tool_calls]}"
                    )
                    
                    # 1. Append assistant's tool-call response to messages thread
                    messages.append(choice_msg)
                    
                    # 2. Run each tool call and append the results
                    import json
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("function", {}).get("name")
                        tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
                        try:
                            tool_args = json.loads(tool_args_str)
                        except Exception:
                            tool_args = {}
                            
                        # Execute the local python function
                        log_activity(
                            activity_type="active",
                            source="Agent",
                            message=f"🛠️ Выполнение: '{tool_name}' с аргументами {tool_args_str}"
                        )
                        result_str = await asyncio.to_thread(execute_tool, tool_name, tool_args, chat_id=session_id)
                        
                        try:
                            res_obj = json.loads(result_str)
                            if "error" in res_obj:
                                log_activity(
                                    activity_type="active",
                                    source="Agent",
                                    message=f"❌ Ошибка в '{tool_name}': {res_obj['error']}"
                                )
                            else:
                                log_activity(
                                    activity_type="active",
                                    source="Agent",
                                    message=f"✅ Результат '{tool_name}' получен успешно"
                                )
                        except Exception:
                            pass
                        

                        
                        # Append the tool role answer
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "name": tool_name,
                            "content": result_str
                        })
                        
                latency_ms = int((time.time() - start_time) * 1000)
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            logger.exception("Error during OpenRouter chat completion call")
            response_text = "Прошу прощения, Сэр. Произошел сбой при обработке вашего запроса."

        try:
            from backend.database import update_agent_runtime_state, log_agent_event
            update_agent_runtime_state(
                "jarvis",
                status="idle" if error_msg is None else "error",
                current_task="",
                last_action="Response delivered" if error_msg is None else "Response failed",
                last_error=error_msg or "",
                progress=100,
            )
            log_agent_event(
                "jarvis",
                "task_completed" if error_msg is None else "error",
                "Response delivered to chat." if error_msg is None else error_msg,
                "success" if error_msg is None else "error",
                task=user_message,
            )
        except Exception:
            pass

        # Add call record to global decision logs
        from datetime import datetime
        from zoneinfo import ZoneInfo
        log_entry = {
            "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S"),
            "session_id": session_id,
            "model": self.model,
            "latency_ms": latency_ms,
            "success": error_msg is None,
            "error": error_msg,
            "prompt_tokens_estimate": sum(len(m.get("content") or "") for m in messages) // 4,
            "user_message": user_message,
            "assistant_response": response_text,
            "traces": []
        }
        
        DECISION_LOGS.insert(0, log_entry)
        if len(DECISION_LOGS) > 100:
            DECISION_LOGS.pop()
        try:
            from backend.database import save_decision_log
            save_decision_log(log_entry)
        except Exception as db_err:
            logger.error(f"Failed to save decision log to DB: {db_err}")

        return response_text

    async def _respond_as_subagent(self, user_message: str, subagent: Dict[str, Any], parent_skills: Optional[str] = None, current_user_msg_id: Optional[int] = None) -> str:
        """Runs response generation loop specifically tailored for a dynamic subagent session."""
        session_id = subagent["id"]
        subagent_name = subagent["name"]
        system_prompt = subagent["system_prompt"]
        subagent_model = subagent["model"]

        from backend.activity_logger import log_activity
        log_activity(
            activity_type="active",
            source=subagent_name,
            message=f"👤 Получен запрос для субагента '{subagent_name}': '{user_message}'"
        )

        history = self.get_history(session_id)
        
        hits = []
        if self.auto_rag:
            from backend import rag
            hits = rag.search_memory(user_message, limit=3)
        
        user_content = user_message
        if hits:
            context_block = "\n\n[Контекст из вашей базы знаний для справки]:\n"
            for hit in hits:
                context_block += f"- Из документа '{hit['title']}': \"{hit['content']}\"\n"
            user_content = f"{user_message}\n{context_block}"
        if self.memory_enabled and self.memory_max_items > 0:
            from backend import database as db
            memory_context = _format_memory_context(
                db.search_user_memory(user_message, session_id=session_id, limit=self.memory_max_items)
            )
            if memory_context:
                user_content = f"{user_content}\n{memory_context}"
        
        # Build payload with subagent prompt + chat history + current message
        from datetime import datetime
        from zoneinfo import ZoneInfo
        _now_il = datetime.now(ZoneInfo("Asia/Jerusalem"))
        _day_names_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
        current_time_str = _now_il.strftime("%Y-%m-%d %H:%M:%S")
        day_of_week = _day_names_ru[_now_il.weekday()]
        system_info = (
            f"\n\n[Системная информация]:\n"
            f"Текущая дата и время: {current_time_str} (Asia/Jerusalem, GMT+3)\n"
            f"День недели: {day_of_week}\n"
            f"ВАЖНОЕ ПРАВИЛО: Ваши встроенные знания ограничены прошлым. Для получения ЛЮБОЙ актуальной информации о событиях, спортивных матчах (например, сегодняшние игры, коэффициенты ставок, аналитика), новостях, котировках или погоде, вы ОБЯЗАНЫ использовать поиск по интернету через инструмент web_search. Никогда не выдумывайте события и не опирайтесь на свои старые данные!\n"
            f"КАТЕГОРИЧЕСКИ ЗАПРЕЩЕНО искать, использовать, упоминать, цитировать или пересказывать в ответах Сэру готовые прогнозы, чужие статьи, советы или мнения о валуйных ставках (например, 'готовые прогнозы', 'валуйные ставки по версии LiveSport', 'экспертные мнения'). Вы должны искать исключительно сырые числовые данные: пары соперников, точное время начала матчей и коэффициенты (odds/котировки) букмекеров. Любые выводы и математические расчеты валуйности (EV = Probability * Odds - 1) вы обязаны делать строго самостоятельно и приводить только свои собственные результаты, не ссылаясь на чужие мнения!\n"
            f"Вы не имеете права лениться делать расчеты: если точных числовых коэффициентов в поиске нет, вы обязаны провести математическое прогнозирование (например, рассчитать вероятности победы/ничьей/поражения по распределению Пуассона на основе средней результативности или статистики голов команд) и рассчитать ожидаемую валуйность (EV = P * Odds - 1) на основе расчетных вероятностей и примерных коэффициентов, вместо выдачи сухого отказа или цитирования чужих прогнозов."
        )
        messages = [{"role": "system", "content": system_prompt + system_info}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_content})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/pauloberezini/hermes",
            "X-Title": f"Vexa - {session_id}"
        }

        # Subagents are limited to safe information-gathering tools only
        from backend.tools import TOOLS_SCHEMA, execute_tool
        safe_tool_names = {
            "get_system_stats",
            "get_weather",
            "get_current_time_israel",
            "web_search",
            "get_market_prices",
            "add_price_alert",
            "get_rss_digest",
            "save_subagent_memory",
            "get_subagent_memory",
            "get_todoist_tasks",
            "add_todoist_task",
            "delete_todoist_task",
            "get_calendar_events",
            "add_calendar_event",
            "search_obsidian",
            "read_obsidian_note",
            "create_obsidian_note",
            "sync_obsidian_vault",
            "set_timer",
            "set_alarm",
            "cancel_timer_or_alarm",
            "execute_command",
        }
        
        skill_to_tools = {
            "web_search": ["web_search", "get_current_time_israel", "get_weather", "get_rss_digest"],
            "market_monitor": ["get_market_prices", "add_price_alert"],
            "obsidian_rag": ["search_obsidian", "read_obsidian_note", "create_obsidian_note", "sync_obsidian_vault"],
            "todoist_sync": ["get_todoist_tasks", "add_todoist_task", "delete_todoist_task"],
            "google_calendar": ["get_calendar_events", "add_calendar_event"],
            "timers_alarms": ["set_timer", "set_alarm", "cancel_timer_or_alarm"],
            "shell_execution": ["get_system_stats", "execute_command"],
            "python_sandbox": ["execute_command"]
        }

        skills_str = subagent.get("skills", "")
        if skills_str:
            enabled_skills = [s.strip() for s in skills_str.split(",") if s.strip()]
            child_allowed = set()
            for skill in enabled_skills:
                if skill in skill_to_tools:
                    child_allowed.update(skill_to_tools[skill])
                from backend.mcp_client import mcp_clients, mcp_tool_to_server
                if skill in mcp_clients:
                    child_allowed.update([t["name"] for t in mcp_clients[skill].tools])
                elif skill == "mcp_all":
                    child_allowed.update(mcp_tool_to_server.keys())
                
                # Local BCM tools support
                if skill in ("bcm", "bcm-trader"):
                    try:
                        from backend.bcm.tools import BCM_TOOLS
                        child_allowed.update([t["name"] for t in BCM_TOOLS])
                    except ImportError:
                        pass
        else:
            child_allowed = safe_tool_names.copy()
            from backend.mcp_client import mcp_tool_to_server
            child_allowed.update(mcp_tool_to_server.keys())
            try:
                from backend.bcm.tools import BCM_TOOLS
                child_allowed.update([t["name"] for t in BCM_TOOLS])
            except ImportError:
                pass

        # Intersect with parent_skills if the parent orchestrator has specified restrictions
        if parent_skills:
            enabled_parent_skills = [s.strip() for s in parent_skills.split(",") if s.strip()]
            parent_allowed = set()
            for skill in enabled_parent_skills:
                if skill in skill_to_tools:
                    parent_allowed.update(skill_to_tools[skill])
                from backend.mcp_client import mcp_clients, mcp_tool_to_server
                if skill in mcp_clients:
                    parent_allowed.update([t["name"] for t in mcp_clients[skill].tools])
                elif skill == "mcp_all":
                    parent_allowed.update(mcp_tool_to_server.keys())
                
                # Local BCM tools support
                if skill in ("bcm", "bcm-trader"):
                    try:
                        from backend.bcm.tools import BCM_TOOLS
                        parent_allowed.update([t["name"] for t in BCM_TOOLS])
                    except ImportError:
                        pass
            allowed_tools = child_allowed.intersection(parent_allowed)
        else:
            allowed_tools = child_allowed

        allowed_tools.update(["save_subagent_memory", "get_subagent_memory"])
        subagent_tools = [t for t in TOOLS_SCHEMA if t["function"]["name"] in allowed_tools]
        selected_subagent_tools = _select_tools_for_query(user_message, subagent_tools)

        start_time = time.time()
        response_text = ""
        latency_ms = 0
        error_msg = None
        tool_executed = False

        total_prompt_tokens = 0
        total_completion_tokens = 0

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                while True:
                    payload = {
                        "model": subagent_model,
                        "messages": messages,
                        "temperature": subagent.get("temperature", 0.7),
                        "max_tokens": self.tool_max_tokens if selected_subagent_tools else self.max_tokens,
                    }
                    if selected_subagent_tools:
                        payload["tools"] = selected_subagent_tools
                    
                    is_openmodel = "openmodel.ai" in self.api_base
                    url = f"{self.api_base}/messages" if is_openmodel else f"{self.api_base}/chat/completions"
                    actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
                    
                    response = await client.post(
                        url,
                        json=actual_payload,
                        headers=headers
                    )
                    
                    if response.status_code != 200:
                        error_msg = f"HTTP Error {response.status_code}: {response.text}"
                        provider_name = "OpenModel" if is_openmodel else "OpenRouter"
                        response_text = f"Простите, Сэр. Возникли трудности при связи с сервером {provider_name}: {response.status_code}."
                        break
                        
                    raw_data = response.json()
                    data = translate_to_openai_response(raw_data) if is_openmodel else raw_data
                    usage = data.get("usage", {})
                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                    total_completion_tokens += usage.get("completion_tokens", 0)
                    
                    choice_msg = data["choices"][0]["message"]
                    
                    tool_calls = choice_msg.get("tool_calls")
                    if not tool_calls:
                        response_text = _clean_model_output(_extract_message_text(choice_msg.get("content")))
                        
                        # Fallback for empty text content after tools
                        if not response_text.strip() and tool_executed:
                            response_text = "Действия успешно выполнены, Сэр."
                        if not response_text.strip():
                            logger.warning("Sub-agent '%s' returned an empty final response for session %s", subagent_name, session_id)
                            response_text = _empty_model_response_fallback(subagent_name)
                        
                        cost_usd = calculate_cost(subagent_model, total_prompt_tokens, total_completion_tokens)
                        self.last_costs[session_id] = cost_usd
                        
                        log_activity(
                            activity_type="active",
                            source=subagent_name,
                            message=f"💬 Ответ от '{subagent_name}' получен. Затраты: ${cost_usd:.6f}",
                            token_cost=cost_usd
                        )
                        
                        # Save the message in DB
                        from backend import database as db
                        assistant_msg_id = db.save_message(session_id, "assistant", response_text, cost_usd=cost_usd)
                        self.last_saved_ids[session_id] = {
                            "user": current_user_msg_id,
                            "assistant": assistant_msg_id
                        }
                        break
                        
                    logger.info(f"Subagent {subagent_name} selected tools: {[tc.get('function', {}).get('name') for tc in tool_calls]}")
                    tool_executed = True
                    
                    messages.append(choice_msg)
                    
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("function", {}).get("name")
                        tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
                        try:
                            import json
                            tool_args = json.loads(tool_args_str)
                        except Exception:
                            tool_args = {}
                            
                        log_activity(
                            activity_type="active",
                            source=subagent_name,
                            message=f"🛠️ Выполнение (субагент): '{tool_name}' с аргументами {tool_args_str}"
                        )
                        result_str = await asyncio.to_thread(execute_tool, tool_name, tool_args, chat_id=session_id)
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "name": tool_name,
                            "content": result_str
                        })
                        
                latency_ms = int((time.time() - start_time) * 1000)
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            logger.exception("Error during OpenRouter subagent chat completion call")
            response_text = "Прошу прощения, Сэр. Произошел сбой при обработке запроса субагента."

        # Add call record to global decision logs
        log_entry = {
            "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S"),
            "session_id": session_id,
            "model": subagent_model,
            "latency_ms": latency_ms,
            "success": error_msg is None,
            "error": error_msg,
            "prompt_tokens_estimate": sum(len(m.get("content") or "") for m in messages) // 4,
            "user_message": user_message,
            "assistant_response": response_text,
            "traces": []
        }
        
        DECISION_LOGS.insert(0, log_entry)
        if len(DECISION_LOGS) > 100:
            DECISION_LOGS.pop()
        try:
            from backend.database import save_decision_log
            save_decision_log(log_entry)
        except Exception as db_err:
            logger.error(f"Failed to save subagent decision log to DB: {db_err}")

        return response_text

def translate_to_anthropic_payload(openai_payload):
    # Convert OpenAI style tools to Anthropic style tools
    openai_tools = openai_payload.get("tools")
    anthropic_tools = None
    if openai_tools:
        anthropic_tools = []
        for t in openai_tools:
            if t.get("type") == "function":
                f = t["function"]
                params = f.get("parameters", {})
                anthropic_tools.append({
                    "name": f["name"],
                    "description": f.get("description", ""),
                    "input_schema": {
                        "type": params.get("type", "object"),
                        "properties": params.get("properties", {}),
                        "required": params.get("required", [])
                    }
                })

    # Extract system prompt from messages
    system_prompt = ""
    anthropic_messages = []
    import json
    for msg in openai_payload.get("messages", []):
        role = msg.get("role")
        content = msg.get("content")
        if role == "system":
            system_prompt = content
        elif role == "user":
            anthropic_messages.append({"role": "user", "content": content or ""})
        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for tc in tool_calls:
                    try:
                        args = json.loads(tc["function"]["arguments"]) if isinstance(tc["function"]["arguments"], str) else tc["function"]["arguments"]
                    except Exception:
                        args = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "input": args
                    })
                anthropic_messages.append({"role": "assistant", "content": blocks})
            else:
                anthropic_messages.append({"role": "assistant", "content": content or ""})
        elif role == "tool":
            anthropic_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": msg["tool_call_id"],
                        "content": content or ""
                    }
                ]
            })

    anthropic_payload = {
        "model": openai_payload["model"],
        "messages": anthropic_messages,
        "max_tokens": 4096,
        "temperature": openai_payload.get("temperature", 0.7)
    }
    if system_prompt:
        anthropic_payload["system"] = system_prompt
    if anthropic_tools:
        anthropic_payload["tools"] = anthropic_tools

    return anthropic_payload

def translate_to_openai_response(anthropic_response):
    content_list = anthropic_response.get("content", [])
    text_content = ""
    tool_calls = []
    import json
    
    for block in content_list:
        if block.get("type") == "text":
            text_content += block.get("text", "")
        elif block.get("type") == "tool_use":
            tool_calls.append({
                "id": block["id"],
                "type": "function",
                "function": {
                    "name": block["name"],
                    "arguments": json.dumps(block["input"])
                }
            })
            
    openai_response = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": text_content if text_content else None
                }
            }
        ],
        "usage": {
            "prompt_tokens": anthropic_response.get("usage", {}).get("input_tokens", 0),
            "completion_tokens": anthropic_response.get("usage", {}).get("output_tokens", 0)
        }
    }
    
    if tool_calls:
        openai_response["choices"][0]["message"]["tool_calls"] = tool_calls
        
    return openai_response

# Singleton instance
agent_instance = JarvisAgent()
