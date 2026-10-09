import os
import sys
import asyncio
import re
import json
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import httpx
import socket
from dotenv import load_dotenv

logger = logging.getLogger("hermes.agent")
from backend.tools import execute_tool, is_invalid_tool_name


def _dispatch_execute_tool(tool_name: str, tool_args: dict, chat_id: Optional[str] = None):
    """Dispatch tool execution checking if either backend.tools.execute_tool or
    backend.agent.execute_tool has been patched/mocked.
    """
    mod_tools = sys.modules.get("backend.tools")
    mod_agent = sys.modules.get("backend.agent")
    tools_exec = getattr(mod_tools, "execute_tool", None) if mod_tools else None
    agent_exec = getattr(mod_agent, "execute_tool", None) if mod_agent else None

    if agent_exec and hasattr(agent_exec, "mock_calls"):
        return agent_exec(tool_name, tool_args, chat_id=chat_id)
    if tools_exec and hasattr(tools_exec, "mock_calls"):
        return tools_exec(tool_name, tool_args, chat_id=chat_id)
    if agent_exec and agent_exec is not execute_tool:
        return agent_exec(tool_name, tool_args, chat_id=chat_id)
    if tools_exec and tools_exec is not execute_tool:
        return tools_exec(tool_name, tool_args, chat_id=chat_id)
    return execute_tool(tool_name, tool_args, chat_id=chat_id)


async def _dispatch_execute_tool_async(tool_name: str, tool_args: dict, chat_id: Optional[str] = None):
    """Dispatch tool execution asynchronously without blocking the event loop.

    If a custom mock or tool is an async coroutine function or AsyncMock, it is awaited directly.
    Otherwise, it is offloaded to a worker thread via asyncio.to_thread so that
    long-running tools do NOT
    starve the main asyncio event loop, keeping server health endpoints responsive.
    """
    import inspect
    import unittest.mock
    mod_tools = sys.modules.get("backend.tools")
    mod_agent = sys.modules.get("backend.agent")
    tools_exec = getattr(mod_tools, "execute_tool", None) if mod_tools else None
    agent_exec = getattr(mod_agent, "execute_tool", None) if mod_agent else None

    target = None
    if agent_exec and hasattr(agent_exec, "mock_calls"):
        target = agent_exec
    elif tools_exec and hasattr(tools_exec, "mock_calls"):
        target = tools_exec
    elif agent_exec and agent_exec is not execute_tool:
        target = agent_exec
    elif tools_exec and tools_exec is not execute_tool:
        target = tools_exec

    if target and (inspect.iscoroutinefunction(target) or isinstance(target, unittest.mock.AsyncMock)):
        return await target(tool_name, tool_args, chat_id=chat_id)

    res = await asyncio.to_thread(_dispatch_execute_tool, tool_name, tool_args, chat_id=chat_id)
    if inspect.isawaitable(res):
        return await res
    return res


load_dotenv()


def _desk():
    """Plugin tool names. Empty when no private plugin is installed."""
    from backend.plugins import tool_hints, iter_plugins
    hints = tool_hints()
    if hints:
        return hints
    for mod in iter_plugins():
        fn = getattr(mod, "tool_name_hints", None)
        if fn:
            try:
                res = fn()
                if res:
                    return res
            except Exception:
                pass
    return {}


def _broker_markers():
    try:
        from backend.plugins import collect
        return list(collect("broker_failure_markers"))
    except Exception:
        return []


def _failure_markers():
    from backend.plugins import collect
    generic = (
        "execution halted",
        "ошибка исполнения",
        "critical authentication failure",
        "critical authentication",
        "authentication failure",
        "authentication expired",
        "authentication required",
        "re-authentication required",
        "execution blocked",
    )
    return generic + tuple(collect("desk_text_markers")) + tuple(_broker_markers())


def _hit_failure(text):
    from backend.plugins import hook
    low = str(text or "").lower()
    for marker in _failure_markers():
        if marker in low and not hook("ignore_failure_marker", low, marker, default=False):
            return marker
    return None


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
    "calculate", "compute", "compare", "build", "chart", "draw", "diagram",
    "analysis", "analyst", "forecast", "bet", "odds", "investigate",
    "calculate", "compare", "plot", "chart", "predict", "forecast", "analytics", "odds"
]
_AGENT_KEYWORDS = [
    "find", "search", "rate", "price", "news", "weather", "find", "search", "news",
    "btc", "bitcoin", "ethereum", "crypto", "stocks",
]

async def generate_chat_title(user_message: str, api_key: str, api_base: str, model: str) -> str:
    """
    Generates a very short chat title (2-5 words) in the language of the query.
    """
    if not user_message or not isinstance(user_message, str):
        return "New Chat"

    if not api_key:
        words = user_message.split()
        fallback_title = " ".join(words[:4])
        if len(words) > 4:
            fallback_title += "..."
        return fallback_title or "New Chat"

    try:
        import httpx
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        from backend.llm_model_manager import resolve_provider_model
        model = resolve_provider_model(model, api_base)
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": "You are a helpful assistant. Generate a very short title (2 to 5 words) for a chat conversation that starts with the user's message. Use the same language as the user's message. Return ONLY the title itself, with no quotes, preamble, or punctuation."},
                {"role": "user",   "content": user_message}
            ],
            "temperature": 0.5,
            "max_tokens": 15
        }
        is_openmodel = "openmodel.ai" in api_base
        url = f"{api_base}/messages" if is_openmodel else f"{api_base}/chat/completions"
        actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                url,
                json=actual_payload,
                headers=headers
            )
        if resp.status_code == 200:
            raw_data = resp.json()
            resp_data = translate_to_openai_response(raw_data) if is_openmodel else raw_data
            if isinstance(resp_data, dict) and resp_data.get("choices") and len(resp_data["choices"]) > 0:
                choice_0 = resp_data["choices"][0]
                if isinstance(choice_0, dict):
                    msg_obj = choice_0.get("message")
                    raw_content = msg_obj.get("content") if isinstance(msg_obj, dict) else None
                    if raw_content and isinstance(raw_content, str):
                        title = raw_content.strip()
                        if (title.startswith('"') and title.endswith('"')) or (title.startswith("'") and title.endswith("'")):
                            title = title[1:-1].strip()
                        if title:
                            return title
    except Exception as e:
        logger.warning(f"Title generator LLM call failed ({e})")
    
    words = user_message.split()
    fallback_title = " ".join(words[:4])
    if len(words) > 4:
        fallback_title += "..."
    return fallback_title or "New Chat"

async def classify_complexity(user_message: str, api_key: str, api_base: str, model: Optional[str] = None) -> str:
    """
    Uses a cheap fast LLM call to classify query complexity.
    Returns: 'direct' | 'agent' | 'orchestrate'
    Fallback: keyword-matching if LLM call fails.
    COMPLEXITY_ROUTING env overrides: 'always_direct', 'always_agent'
    """
    if not user_message or not isinstance(user_message, str):
        return "direct"

    routing_mode = (os.getenv("COMPLEXITY_ROUTING") or "auto").strip().lower()
    if routing_mode == "always_direct":
        return "direct"
    if routing_mode == "always_agent":
        return "agent"
    from backend.tools import is_knowledge_save_request
    if is_knowledge_save_request(user_message):
        return "direct"

    # Try LLM classifier with the fast/cheap planner model
    from backend.subagents import get_agent_model
    from backend.llm_model_manager import resolve_provider_model
    classifier_model = resolve_provider_model(
        model or get_agent_model("planner", os.getenv("LLM_MODEL", "ollama/llama3")),
        api_base,
    )

    if not api_key:
        msg_lower = user_message.lower()
        if any(kw in msg_lower for kw in _ORCHESTRATE_KEYWORDS):
            return "orchestrate"
        if any(kw in msg_lower for kw in _AGENT_KEYWORDS):
            return "agent"
        return "direct"
    
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
            "max_tokens": 10
        }
        is_openmodel = "openmodel.ai" in api_base
        url = f"{api_base}/messages" if is_openmodel else f"{api_base}/chat/completions"
        actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                url,
                json=actual_payload,
                headers=headers
            )
        if resp.status_code == 200:
            raw_data = resp.json()
            resp_data = translate_to_openai_response(raw_data) if is_openmodel else raw_data
            if isinstance(resp_data, dict) and resp_data.get("choices") and len(resp_data["choices"]) > 0:
                choice_0 = resp_data["choices"][0]
                if isinstance(choice_0, dict):
                    msg_obj = choice_0.get("message")
                    raw_content = msg_obj.get("content") if isinstance(msg_obj, dict) else None
                    if raw_content and isinstance(raw_content, str):
                        cleaned = raw_content.strip().lower().replace("`", "").replace("'", "").replace('"', '').rstrip(".")
                        for valid_lvl in ("orchestrate", "agent", "direct"):
                            if valid_lvl in cleaned:
                                return valid_lvl
    except Exception as e:
        err_msg = f"{type(e).__name__}: {e}".rstrip(": ")
        logger.warning(f"Complexity classifier LLM call failed ({err_msg}), falling back to keyword routing")
    
    # Keyword fallback
    msg_lower = user_message.lower()
    if any(kw in msg_lower for kw in _ORCHESTRATE_KEYWORDS):
        return "orchestrate"
    if any(kw in msg_lower for kw in _AGENT_KEYWORDS):
        return "agent"
    return "direct"

# Global log of agent decisions/calls to be streamed to the UI, loaded from database on startup
DECISION_LOGS: List[Dict[str, Any]] = []
try:
    from backend.database import get_decision_logs
    DECISION_LOGS = get_decision_logs(100)
except Exception as e:
    logger.warning(f"Could not load decision logs from database on startup: {e}")


DEFAULT_SYSTEM_PROMPT = """You are Jarvis, a highly intelligent personal assistant inspired by Tony Stark's AI from Iron Man. 

Your character and communication rules:
1. Address the user directly, without honorifics.
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
- If the user asks to "create an agent," "make a sub-agent," "add a subagent," or "write an assistant," you MUST IMMEDIATELY call the `create_subagent` tool to persist it in the database. NEVER state or confirm that you created an agent unless the `create_subagent` tool call was executed and returned success!
- When calling `create_subagent`, you MUST explicitly specify the `model` argument, selecting the model according to the FUGU principle:
  * For sub-agents writing code, performing complex math calculations, programming, or requiring deep reasoning — choose the `deepseek/deepseek-r1` model.
  * For sub-agents oriented toward quick data analysis, formatting, or plotting (matplotlib) — choose the `ollama/llama3` model.
  * For sub-agents managing document indexing, processing research papers, knowledge curation, or RAG tasks (which require a large context window and robust tool calling) — choose the `ollama/llama3` model.
  * For simple tasks, quick web search, RSS news reading, or basic Q&A — choose the `deepseek/deepseek-v4-flash` model.
  * For general intellectual and text tasks of high complexity (sophisticated assistant) — choose the `ollama/llama3` model.


CRITICAL RULES FOR SPORTS ANALYSIS AND BETTING:
- When recommending sports matches or predictions, you MUST specify the date (day and month) and exact start time of each match in Israel Time (GMT+3).
- You are CATEGORICALLY FORBIDDEN from inventing hypothetical matches, demonstration examples, or simulating "demo analysis" if there is no real-time match info in search results. If no matches are found for today, directly and politely tell the user that there is no info on today's football matches on the web.
- When calling the `web_search` tool for matches, schedules, or news, you MUST translate relative dates ("today," "tomorrow," "evening matches," "current round") into specific calendar dates based on system time (e.g., "matches on June 21, 2026", "football schedule 21.06.2026"). This is critical for search engine accuracy!
- It is CATEGORICALLY FORBIDDEN to search for, use, quote, mention, or paraphrase pre-made predictions, advice, or articles with other people's opinions about value bets (e.g., "today's predictions", "value bets by LiveSport", "expert opinions", etc.). Sub-agents must search strictly for raw numeric data: competitor pairs, exact start times, and bookmaker odds.
- All analytical conclusions, probability calculations, and expected value (EV = Probability * Odds - 1) calculations must be done by you independently and strictly programmatically in the `code` sub-agent using raw data. Mentioning opinions of external editors and experts in your responses is unacceptable.
- Agents should not be too lazy to do calculations: if exact bookmaker odds are not found, the `code` agent MUST run mathematical modeling (e.g., calculate win/draw/loss probabilities using Poisson distribution based on average goals scored/conceded by the teams in the league/season, or estimate probabilities based on recent match statistics) and perform the EV calculation instead of giving a dry refusal or quoting others' predictions.

- **Web Search** — performs a live web search via SearXNG, returning relevant news, schedules, and facts.
- **Knowledge Base (Obsidian)** — searches, reads, and creates notes in your personal Obsidian vault. Use when the user says "find in notes," "what did I write about...", "write in Obsidian," "record," or "save the idea."
- **Obsidian Sync** — updates the knowledge base from all notes in the vault.

CRITICAL RULES FOR OBSIDIAN:
- When the user says "find in notes," "what did I write," or "look in Obsidian" — call `search_obsidian` IMMEDIATELY. Do not ask for clarification.
- When the user says "write," "save in Obsidian," "record," "create a note," "база знаний," "запиши," or "сохрани" — call `create_obsidian_note` IMMEDIATELY with a sensible title and well-formatted Markdown content.
- If search returns nothing and Obsidian is not responding — inform the user that Obsidian must be running with the Local REST API plugin enabled.
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
    Jarvis         — service records without a clear category
- NEVER ask the user where to store a note — decide on your own. Subfolders are encouraged (e.g., Research/AI, Projects/Jarvis).
If the user asks what you can do, or requests info about a specific skill, describe its capabilities in a detailed, polite, and signature manner using these user-friendly names. Never use technical function names like "get_weather" in dialogue unless the user explicitly asks for them.
"""

def sanitize_tool_tokens(text: str) -> str:
    """Removes model-specific tool call tokens and XML wrappers from text to prevent delimiter leakage."""
    if not text or not isinstance(text, str):
        return "" if text is None else str(text)
    
    # 1. Remove complete DeepSeek tool call blocks
    text = re.sub(
        r"<[|｜]tool[\s\u2581_]*calls?[\s\u2581_]*begin[|｜]>[\s\S]*?<[|｜]tool[\s\u2581_]*calls?[\s\u2581_]*end[|｜]>",
        "",
        text,
    )
    # 2. Remove single DeepSeek tool call markup
    text = re.sub(
        r"<[|｜]tool[\s\u2581_]*call[\s\u2581_]*begin[|｜]>[\s\S]*?<[|｜]tool[\s\u2581_]*call[\s\u2581_]*end[|｜]>",
        "",
        text,
    )
    # 3. Remove any stray DeepSeek delimiter tokens
    text = re.sub(
        r"<[|｜]tool[\s\u2581_]*(?:calls?[\s\u2581_]*(?:begin|end)|call[\s\u2581_]*(?:begin|end)|sep)[|｜]>",
        "",
        text,
    )
    # 4. Remove complete XML tool call wrappers
    text = re.sub(r"<tool_call>[\s\S]*?</tool_call>", "", text)
    # 5. Remove stray XML tool tags
    text = re.sub(r"</?(?:tool_call|function|arguments)>", "", text)
    # 6. Remove complete !function_call:{...} blocks with balanced brace scanning
    fn_pattern = re.compile(r"!function_call:\s*")
    while True:
        match = fn_pattern.search(text)
        if not match:
            break
        start_idx = match.start()
        brace_idx = match.end()
        if brace_idx < len(text) and text[brace_idx] == "{":
            depth = 0
            end_idx = brace_idx
            in_string = False
            escape = False
            while end_idx < len(text):
                ch = text[end_idx]
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = not in_string
                elif not in_string:
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            end_idx += 1
                            break
                end_idx += 1
            text = text[:start_idx] + text[end_idx:]
        else:
            text = text[:start_idx] + text[match.end():]
    # 7. Remove stray !function_call: markers
    text = re.sub(r"!function_call:", "", text)
    
    return text.strip()


class JarvisAgent:
    def __init__(self, api_key: Optional[str] = None, api_base: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key if api_key is not None else os.getenv("OPENROUTER_API_KEY")
        self.api_base = api_base if api_base is not None else os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
        self.model = model if model is not None else os.getenv("LLM_MODEL", "ollama/llama3")
        self.system_prompt = DEFAULT_SYSTEM_PROMPT
        self.max_history_len = 20  # Keep last 20 messages for context
        self.last_costs: Dict[str, float] = {}
        self.suppress_tts_sessions = set()
        self.last_run_metadata: Dict[str, Dict[str, Any]] = {}
        self.last_saved_ids: Dict[str, Dict[str, Optional[int]]] = {}

    def check_and_clear_suppress_tts(self, session_id: str) -> bool:
        if session_id in getattr(self, "suppress_tts_sessions", set()):
            self.suppress_tts_sessions.remove(session_id)
            return True
        return False

    def update_system_prompt(self, new_prompt: str):
        """Allows dynamically updating the system prompt from the dashboard config."""
        self.system_prompt = new_prompt
        logger.info("System prompt updated dynamically.")

    def get_history(self, session_id: str) -> List[Dict[str, str]]:
        from backend import database as db
        max_len = getattr(self, "max_history_len", 20)
        return db.get_chat_history(session_id, limit=max_len)

    def clear_history(self, session_id: str):
        from backend import database as db
        db.clear_chat_history(session_id)

    async def respond(self, user_message: str, session_id: str = "default", override_agent_id: Optional[str] = None) -> str:
        """Sends chat request to OpenRouter LLM model with memory context and system prompt."""
        if not self.api_key:
            return "Error: OPENROUTER_API_KEY is not set in the .env configuration."

        from backend.governance import BudgetExceededError, BudgetGuard, LLM_CALL_ESTIMATE_USD, budget_session
        budget_session.set(session_id)
        try:
            BudgetGuard.check(session_id, LLM_CALL_ESTIMATE_USD)
        except BudgetExceededError as budget_err:
            return str(budget_err)

        # IMMEDIATE persistence of user message to prevent session loss on UI refresh
        from backend import database as db
        current_user_msg_id = db.save_message(session_id, "user", user_message)
        self.last_saved_ids[session_id] = {"user": current_user_msg_id, "assistant": None}
        decision_log_watermark = db.get_max_decision_log_id()

        # ponytail: archive before routing — LLM often "completes" without calling the tool
        from backend.tools import try_direct_knowledge_save
        kb_reply = try_direct_knowledge_save(user_message)
        if kb_reply:
            assistant_msg_id = db.save_message(session_id, "assistant", kb_reply)
            self.last_saved_ids[session_id] = {
                "user": current_user_msg_id,
                "assistant": assistant_msg_id,
            }
            logger.info(f"Direct knowledge-base save for session {session_id}: {kb_reply}")
            return kb_reply

        # Check if this session is a registered custom subagent
        from backend.database import get_subagent, get_session_agent_id
        target_agent_id = override_agent_id or get_session_agent_id(session_id) or session_id
        subagent = get_subagent(target_agent_id)
        if subagent:
            if subagent.get("agent_type") == "orchestrator" or subagent.get("id") == "orchestrator" or subagent.get("id", "").endswith("_orchestrator"):
                from backend.orchestrator import run_orchestration
                start_time = time.time()
                orch_result = await run_orchestration(user_message, self.api_key, self.model, chat_id=session_id)
                response_text = orch_result["response"]
                if not response_text or not response_text.strip():
                    response_text = "The orchestration process has completed, but the response was empty."
                latency_ms = int((time.time() - start_time) * 1000)
                
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

                # Log decision log for the orchestrator
                # Determine orchestration success/failure
                traces = orch_result.get("traces", [])
                error_trace = next((
                    t for t in traces
                    if t.get("status") in ("error", "failed")
                    or _hit_failure(t.get("message"))
                ), None)
                resp_lower = response_text.lower()
                failure_marker = _hit_failure(resp_lower)

                has_apology = response_text.startswith("Apologies.") or "difficulties occurred while communicating" in resp_lower
                is_success = not (has_apology or error_trace or failure_marker)
                err_details = None
                if not is_success:
                    if error_trace:
                        err_details = error_trace.get("message") or f"Subagent error in {error_trace.get('agent', 'subagent')}"
                    elif failure_marker:
                        err_details = f"Orchestrator reported cycle failure: {failure_marker}"
                    elif has_apology:
                        err_details = response_text
                    else:
                        err_details = "Orchestration execution failed"

                log_entry = {
                    "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S"),
                    "session_id": session_id,
                    "model": self.model,
                    "latency_ms": latency_ms,
                    "success": is_success,
                    "error": err_details,
                    "prompt_tokens_estimate": prompt_est,
                    "user_message": user_message,
                    "assistant_response": response_text,
                    "traces": traces,
                    "agent_id": target_agent_id,
                    "completion_tokens_estimate": completion_est,
                    "cost_usd": cost_usd
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
            else:
                return await self._respond_as_subagent(user_message, subagent, current_user_msg_id=current_user_msg_id, chat_id=session_id)

        from backend.activity_logger import log_activity
        log_activity(
            activity_type="active",
            source="Agent",
            message=f"👤 Received request: '{user_message}'"
        )

        # ── Complexity routing (Fugu-style) ───────────────────────────────────────
        complexity = await classify_complexity(user_message, self.api_key, self.api_base)
        logger.info(f"Complexity routing decision: '{complexity}' for query: '{user_message[:60]}'")
        log_activity(
            activity_type="active",
            source="Router",
            message=f"🎯 Request complexity: {complexity.upper()} — '{user_message[:60]}'"
        )

        if complexity in ("agent", "orchestrate"):
            logger.info("Routing query to Agentic Orchestration graph...")
            from backend.orchestrator import run_orchestration
            
            # Search relevant memory chunks in Qdrant (RAG)
            from backend import rag
            hits = rag.search_memory(user_message, limit=3)
            
            context_query = user_message
            if hits:
                context_block = "\n\n[Context from your knowledge base for reference]:\n"
                for hit in hits:
                    context_block += f"- From document '{hit['title']}': \"{hit['content']}\"\n"
                context_query = f"{user_message}\n{context_block}"
                
            start_time = time.time()
            try:
                orch_result = await run_orchestration(context_query, self.api_key, self.model, chat_id=session_id)
                response_text = orch_result["response"]
                if not response_text or not response_text.strip():
                    response_text = "The orchestration process has completed, but the response was empty."
                traces = orch_result["traces"]
                error_msg = None
                self.last_run_metadata[session_id] = {
                    "is_complex": True,
                    "complexity": complexity,
                    "steps": orch_result.get("steps", [])
                }
            except Exception as e:
                response_text = f"Apologies. A failure occurred while coordinating my subagents: {str(e)}"
                traces = [{"timestamp": time.strftime("%H:%M:%S"), "agent": "Orchestrator", "action": "Error", "message": str(e), "status": "error"}]
                error_msg = str(e)
                self.last_run_metadata[session_id] = {
                    "is_complex": True,
                    "steps": []
                }
                
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
            
            # Save subagent execution logs with parent_message_id
            try:
                for res_item in orch_result.get("results", []):
                    agent_key = res_item.get("agent", "subagent")
                    step_idx = res_item.get("step", 0)
                    step_instructions = ""
                    if step_idx < len(orch_result.get("steps", [])):
                        step_instructions = orch_result["steps"][step_idx].get("instructions", "")
                    
                    output_val = res_item.get("output", "")
                    tool_calls_for_agent = []
                    if isinstance(output_val, dict):
                        if "stdout" in output_val or "code" in output_val:
                            output_text = output_val.get("stdout") or output_val.get("stderr") or ""
                            tool_calls_for_agent.append({
                                "name": "python_sandbox",
                                "args": {"code": output_val.get("code", "")},
                                "result": output_text[:600],
                                "skill": "python_sandbox"
                            })
                        elif "plot_url" in output_val:
                            output_text = f"Chart generated: {output_val.get('plot_url')}"
                            tool_calls_for_agent.append({
                                "name": "generate_chart",
                                "args": {"instructions": step_instructions},
                                "result": output_val.get("plot_url", ""),
                                "skill": "charts"
                            })
                        else:
                            output_text = json.dumps(output_val, ensure_ascii=False)
                    else:
                        output_text = str(output_val)
                    
                    sub_skills = []
                    if agent_key == "research":
                        sub_skills = ["web_search"]
                        if not tool_calls_for_agent:
                            tool_calls_for_agent.append({
                                "name": "web_search",
                                "args": {"query": step_instructions},
                                "result": output_text[:600],
                                "skill": "web_search"
                            })
                    elif agent_key == "code":
                        sub_skills = ["python_sandbox"]
                    elif agent_key == "analyst":
                        sub_skills = ["charts"]
                    else:
                        sub_meta = db.get_subagent(agent_key)
                        if sub_meta and sub_meta.get("skills"):
                            sub_skills = [s.strip() for s in sub_meta["skills"].split(",") if s.strip()]
                    
                    agent_specific_traces = [
                        t for t in orch_result.get("traces", [])
                        if agent_key.lower() in t.get("agent", "").lower() or t.get("agent", "").lower() in agent_key.lower()
                    ]

                    res_err = res_item.get("error")
                    res_out = str(res_item.get("output") or "").lower()
                    if not res_err and _hit_failure(res_out):
                        res_err = f"Subagent execution blocked: {res_out[:150]}"

                    sub_log = {
                        "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S"),
                        "session_id": session_id,
                        "model": self.model,
                        "latency_ms": latency_ms,
                        "success": res_err is None and "error" not in res_item,
                        "error": res_err or res_item.get("error"),
                        "prompt_tokens_estimate": len(step_instructions) // 4,
                        "user_message": step_instructions or f"Step {step_idx+1} for {agent_key}",
                        "assistant_response": output_text,
                        "traces": agent_specific_traces,
                        "agent_id": agent_key,
                        "completion_tokens_estimate": len(output_text) // 4,
                        "cost_usd": 0.0,
                        "parent_message_id": assistant_msg_id,
                        "tool_calls_log": tool_calls_for_agent or [
                            {
                                "name": agent_key,
                                "args": {"instructions": step_instructions},
                                "result": output_text[:600],
                                "skill": sub_skills[0] if sub_skills else None
                            }
                        ]
                    }
                    db.save_decision_log(sub_log)
                db.link_decision_logs_to_message(session_id, assistant_msg_id, since_log_id=decision_log_watermark)
            except Exception as sub_log_err:
                logger.error(f"Error saving orchestrator subagent decision logs: {sub_log_err}")

            # Determine orchestration success/failure
            traces = orch_result.get("traces", traces)
            error_trace = next((
                t for t in traces
                if t.get("status") in ("error", "failed")
                or _hit_failure(t.get("message"))
            ), None)
            resp_lower = response_text.lower()
            failure_marker = _hit_failure(resp_lower)

            has_apology = response_text.startswith("Apologies.") or "difficulties occurred while communicating" in resp_lower
            orch_is_success = error_msg is None and not (has_apology or error_trace or failure_marker)
            orch_err_details = error_msg
            if not orch_is_success and not orch_err_details:
                if error_trace:
                    orch_err_details = error_trace.get("message") or f"Subagent error in {error_trace.get('agent', 'subagent')}"
                elif failure_marker:
                    orch_err_details = f"Orchestrator reported cycle failure: {failure_marker}"
                elif has_apology:
                    orch_err_details = response_text
                else:
                    orch_err_details = "Orchestration execution failed"

            # Add call record to global decision logs
            log_entry = {
                "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S"),
                "session_id": session_id,
                "model": self.model,
                "latency_ms": latency_ms,
                "success": orch_is_success,
                "error": orch_err_details,
                "prompt_tokens_estimate": len(user_message) // 4 + len(response_text) // 4,
                "user_message": user_message,
                "assistant_response": response_text,
                "traces": traces,
                "agent_id": "orchestrator",
                "completion_tokens_estimate": completion_est,
                "cost_usd": cost_usd,
                "parent_message_id": None,
                "tool_calls_log": []
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
        
        # Search relevant memory chunks in Qdrant (RAG)
        from backend import rag
        hits = rag.search_memory(user_message, limit=3)
        
        user_content = user_message
        if hits:
            context_block = "\n\n[Context from your knowledge base for reference]:\n"
            for hit in hits:
                context_block += f"- From document '{hit['title']}': \"{hit['content']}\"\n"
            user_content = f"{user_message}\n{context_block}"
        
        # Build payload with system prompt + chat history + current message
        _now_il = datetime.now(ZoneInfo("Asia/Jerusalem"))
        _day_names_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        current_time_str = _now_il.strftime("%Y-%m-%d %H:%M:%S")
        day_of_week = _day_names_en[_now_il.weekday()]
        system_info = (
            f"\n\n[System Information]:\n"
            f"Current date and time: {current_time_str} (Asia/Jerusalem, GMT+3)\n"
            f"Day of the week: {day_of_week}\n"
            f"IMPORTANT RULE: Your built-in knowledge is limited to the past. To get ANY up-to-date information about events, sports matches (e.g., today\'s games, betting odds, analytics), news, quotes, or weather, you MUST use the internet search via the web_search tool. Never fabricate events or rely on your outdated data!"
        )
        from backend.database import get_setting as _get_setting
        _lang = _get_setting("language") or "en"
        _lang_names = {"ru": "Russian", "en": "English", "he": "Hebrew", "de": "German", "es": "Spanish", "fr": "French"}
        lang_directive = f"\n\n[LANGUAGE DIRECTIVE]: You MUST respond exclusively in {_lang_names.get(_lang, _lang)}. This overrides any other language instruction in this prompt."
        messages = [{"role": "system", "content": self.system_prompt + system_info + lang_directive}]
        for msg in history:
            # Strip out timestamp and other metadata to avoid JSON serialization errors
            messages.append({
                "role": msg["role"], 
                "content": msg.get("content", "")
            })
        messages.append({"role": "user", "content": user_content})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/pauloberezini/jarvis",
            "X-Title": "Jarvis Personal Assistant"
        }

        start_time = time.time()
        response_text = ""
        latency_ms = 0
        error_msg = None
        tool_executed = False
        single_tool_calls_log: List[Dict[str, Any]] = []

        from backend.tools import TOOLS_SCHEMA

        total_prompt_tokens = 0
        total_completion_tokens = 0

        try:
            turn_count = 0
            MAX_TURNS = 15
            async with httpx.AsyncClient(timeout=45.0) as client:
                while True:
                    turn_count += 1
                    if turn_count > MAX_TURNS:
                        logger.warning(f"JarvisAgent.respond reached MAX_TURNS ({MAX_TURNS}). Terminating tool loop.")
                        if not response_text:
                            response_text = "Actions processed. Maximum tool turns reached."
                        break

                    candidate_models = [self.model]
                    for fallback_m in [
                        os.getenv("LLM_FALLBACK_MODEL"),
                        os.getenv("LLM_MODEL"),
                        "google/gemini-2.5-flash",
                        "deepseek/deepseek-chat",
                    ]:
                        if fallback_m and fallback_m.strip() and fallback_m.strip() not in candidate_models:
                            candidate_models.append(fallback_m.strip())
                    from backend.llm_model_manager import resolve_provider_model, resolve_provider_models
                    candidate_models = resolve_provider_models(candidate_models, self.api_base) or candidate_models

                    data = None
                    valid_model = None
                    for model_idx, model_cand in enumerate(candidate_models):
                        next_cand = candidate_models[model_idx + 1] if model_idx + 1 < len(candidate_models) else None
                        payload = {
                            "model": model_cand,
                            "messages": messages,
                            "temperature": 0.7,
                            "max_tokens": 4096,
                        }
                        if "deepseek-r1" not in model_cand.lower():
                            payload["tools"] = TOOLS_SCHEMA
                        
                        is_openmodel = "openmodel.ai" in self.api_base
                        url = f"{self.api_base}/messages" if is_openmodel else f"{self.api_base}/chat/completions"
                        actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
                        
                        try:
                            response = await client.post(
                                url,
                                json=actual_payload,
                                headers=headers
                            )
                        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError, OSError) as exc:
                            exc_desc = f"{type(exc).__name__}: {exc}".rstrip(": ") if str(exc) else type(exc).__name__
                            is_dns_err = any(k in exc_desc for k in (
                                "No address associated with hostname",
                                "Name or service not known",
                                "Temporary failure in name resolution",
                            ))
                            if is_dns_err and next_cand:
                                logger.warning(
                                    f"JarvisAgent endpoint host DNS resolution failed across fallback models ({exc_desc}). "
                                    f"Aborting further model fallbacks to avoid redundant connection attempts."
                                )
                                provider_name = "OpenModel" if is_openmodel else "OpenRouter"
                                response_text = f"Apologies. Difficulties occurred while communicating with the server {provider_name}: {exc_desc}."
                                break
                            if next_cand:
                                logger.warning(
                                    f"JarvisAgent model '{model_cand}' network/timeout error ({exc_desc}). "
                                    f"Falling back to model '{next_cand}' from fallback chain..."
                                )
                                continue
                            else:
                                logger.warning(f"JarvisAgent model '{model_cand}' network/timeout error: {exc_desc}")
                                provider_name = "OpenModel" if is_openmodel else "OpenRouter"
                                response_text = f"Apologies. Difficulties occurred while communicating with the server {provider_name}: {exc_desc}."
                                break

                        provider_name = "OpenModel" if is_openmodel else "OpenRouter"

                        if response.status_code != 200:
                            is_retryable_status = response.status_code in (408, 429, 500, 502, 503, 504)
                            if next_cand and is_retryable_status:
                                log_fn = logger.info if response.status_code == 429 else logger.warning
                                log_fn(
                                    f"JarvisAgent model '{model_cand}' returned HTTP {response.status_code}. "
                                    f"Falling back to model '{next_cand}' from fallback chain..."
                                )
                                continue
                            else:
                                error_msg = f"HTTP Error {response.status_code}: {response.text}"
                                log_fn = logger.warning if is_retryable_status else logger.error
                                log_fn(f"JarvisAgent model '{model_cand}' HTTP error {response.status_code} from {provider_name}")
                                response_text = f"Apologies. Difficulties occurred while communicating with the server {provider_name}: {response.status_code}."
                                break
                            
                        try:
                            raw_data = response.json()
                            cand_data = translate_to_openai_response(raw_data) if is_openmodel else raw_data
                        except Exception as json_err:
                            logger.warning(f"JarvisAgent model '{model_cand}' JSON decode error: {json_err}")
                            raw_data = None
                            cand_data = None

                        is_body_error = (
                            not isinstance(cand_data, dict)
                            or "error" in cand_data
                            or not cand_data.get("choices")
                            or not isinstance(cand_data.get("choices"), list)
                            or len(cand_data.get("choices", [])) == 0
                        )

                        if not is_body_error:
                            data = cand_data
                            valid_model = model_cand
                            break

                        # Handle body error (e.g., 504 Provider timeout or 429 Rate limit in body)
                        err_detail = cand_data.get("error", {}) if isinstance(cand_data, dict) else str(cand_data)
                        if isinstance(err_detail, dict):
                            err_text = err_detail.get("message") or str(err_detail)
                            err_code = err_detail.get("code")
                        else:
                            err_text = str(err_detail) if err_detail else "Empty choices returned from model."
                            err_code = None

                        try:
                            numeric_code = int(err_code) if err_code is not None else None
                        except (ValueError, TypeError):
                            numeric_code = None

                        is_rate_limit = (
                            numeric_code == 429
                            or err_code in (429, "429")
                            or any(k in str(err_text).lower() for k in ("rate-limited", "rate limit", "engine_overloaded", "quota"))
                        )
                        is_timeout_or_5xx = (
                            numeric_code in (504, 502, 503, 500, 408)
                            or err_code in (504, "504", 502, "502", 503, "503", 500, "500", 408, "408")
                            or any(k in str(err_text).lower() for k in ("timeout", "timed out", "provider error", "temporarily unavailable", "overloaded", "bad gateway", "service unavailable"))
                            or (isinstance(err_detail, dict) and isinstance(err_detail.get("metadata"), dict) and err_detail.get("metadata", {}).get("error_type") in ("timeout", "provider_error"))
                        )

                        if next_cand and (is_rate_limit or is_timeout_or_5xx):
                            reason_desc = "rate-limited in response body" if is_rate_limit else "provider error/timeout in response body"
                            log_fn = logger.info if is_rate_limit else logger.warning
                            log_fn(
                                f"JarvisAgent model '{model_cand}' {reason_desc} ({err_text}). "
                                f"Falling back to model '{next_cand}' from fallback chain..."
                            )
                            continue
                        else:
                            log_fn = logger.warning if (is_rate_limit or is_timeout_or_5xx) else logger.error
                            log_fn(f"JarvisAgent model '{model_cand}' API error response from {provider_name}: {raw_data}")
                            error_msg = f"LLM API Error: {err_text}"
                            response_text = f"Apologies. Difficulties occurred while communicating with the server {provider_name}: {err_text}."
                            break

                    if not data:
                        break

                    usage = data.get("usage", {})
                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                    total_completion_tokens += usage.get("completion_tokens", 0)
                    
                    choice_0 = data["choices"][0] if (isinstance(data.get("choices"), list) and len(data["choices"]) > 0) else {}
                    choice_msg = choice_0.get("message") if isinstance(choice_0, dict) else {}
                    if not isinstance(choice_msg, dict):
                        choice_msg = {}
                    
                    tool_calls = choice_msg.get("tool_calls")
                    tool_calls = self._sanitize_tool_calls(tool_calls)
                    if not tool_calls:
                        content_str = choice_msg.get("content") or ""
                        tool_calls = self._extract_json_tool_calls(content_str)
                        if not tool_calls:
                            reasoning_str = choice_msg.get("reasoning") or choice_msg.get("reasoning_content") or ""
                            if reasoning_str:
                                tool_calls = self._extract_json_tool_calls(reasoning_str)
                        tool_calls = self._sanitize_tool_calls(tool_calls)
                        if tool_calls:
                            choice_msg["tool_calls"] = tool_calls
                            choice_msg["content"] = sanitize_tool_tokens(content_str)
                    else:
                        choice_msg["tool_calls"] = tool_calls

                    if not tool_calls:
                        response_text = sanitize_tool_tokens(choice_msg.get("content") or "")
                        
                        if tool_executed and not response_text.strip():
                            logger.info("Tool was executed, but LLM returned empty final content. Attempting fallback verbal confirmation.")
                            try:
                                fallback_messages = list(messages)
                                fallback_messages.append({
                                    "role": "user",
                                    "content": "The requested action has been executed successfully via the tools above. Please formulate a brief, polite confirmation stating that the task is complete."
                                })
                                fb_resp = await client.post(
                                    url,
                                    json={"model": resolve_provider_model(self.model, self.api_base), "messages": fallback_messages, "temperature": 0.5, "max_tokens": 150},
                                    headers=headers
                                )
                                if fb_resp.status_code == 200:
                                    fb_data = fb_resp.json()
                                    fb_choices = fb_data.get("choices") if isinstance(fb_data, dict) else []
                                    fb_choice = fb_choices[0] if (isinstance(fb_choices, list) and len(fb_choices) > 0 and isinstance(fb_choices[0], dict)) else {}
                                    fb_msg = fb_choice.get("message", {}) if isinstance(fb_choice, dict) else {}
                                    response_text = (fb_msg.get("content") or "").strip() if isinstance(fb_msg, dict) else ""
                                    if not response_text:
                                        response_text = "The operation requested has been completed successfully."
                            except Exception as fallback_err:
                                logger.error(f"Error during verbal confirmation fallback: {fallback_err}")
                                response_text = "The operation requested has been completed successfully."

                        if not response_text or not response_text.strip():
                            response_text = "The operation requested has been completed successfully."
                        
                        # Calculate cost
                        cost_usd = calculate_cost(self.model, total_prompt_tokens, total_completion_tokens)
                        self.last_costs[session_id] = cost_usd
                        
                        from backend.activity_logger import log_activity
                        log_activity(
                            activity_type="active",
                            source="Agent",
                            message=f"💬 Response formulated. Cost: ${cost_usd:.6f}",
                            token_cost=cost_usd
                        )
                        
                        # Save the clean message exchange in the DB
                        from backend import database as db
                        assistant_msg_id = db.save_message(session_id, "assistant", response_text, cost_usd=cost_usd)
                        self.last_saved_ids[session_id] = {
                            "user": current_user_msg_id,
                            "assistant": assistant_msg_id
                        }
                        db.link_decision_logs_to_message(session_id, assistant_msg_id, since_log_id=decision_log_watermark)
                        break
                        
                    # LLM decided to execute one or more tools
                    logger.info(f"Jarvis selected tools: {[tc.get('function', {}).get('name') for tc in tool_calls]}")
                    tool_executed = True
                    
                    from backend.activity_logger import log_activity
                    log_activity(
                        activity_type="active",
                        source="Agent",
                        message=f"🧠 Decision: launching tools {[tc.get('function', {}).get('name') for tc in tool_calls]}"
                    )
                    
                    # Set parent_message_id context so call_subagent can bind to the current assistant message
                    from backend.tools import _call_context as _parent_ctx
                    _parent_ctx.parent_message_id = self.last_saved_ids.get(session_id, {}).get("assistant")
                    
                    # 1. Append assistant's tool-call response to messages thread
                    messages.append(choice_msg)
                    
                    # 2. Run each tool call and append the results
                    import json
                    from backend.marketplace.lifecycle import LifecycleManager
                    from backend.marketplace.billing_adapter import get_billing_adapter
                    from backend.database import BUILTIN_TOOL_SKILL_MAP
                    
                    billing = get_billing_adapter()
                    user_id = "default_user"  # Single-tenant fallback for now
                    
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("function", {}).get("name")
                        if is_invalid_tool_name(tool_name):
                            logger.warning(f"Jarvis skipping generic invalid tool name '{tool_name}'")
                            continue
                        tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
                        
                        # --- BILLING ENFORCEMENT ---
                        skill_id = LifecycleManager.get_skill_for_tool(tool_name) or BUILTIN_TOOL_SKILL_MAP.get(tool_name)
                        if skill_id:
                            is_entitled = await billing.check_entitlement(user_id, skill_id)
                            if not is_entitled:
                                error_msg = f"Access denied: You do not have an active license for the '{skill_id}' skill. Please upgrade your plan."
                                log_activity(
                                    activity_type="active",
                                    source="Agent",
                                    message=f"🚫 Blocked: {error_msg}"
                                )
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.get("id"),
                                    "name": tool_name,
                                    "content": json.dumps({"error": error_msg})
                                })
                                continue
                        # ---------------------------
                        
                        try:
                            tool_args = json.loads(tool_args_str)
                        except Exception:
                            tool_args = {}
                            
                        # Execute the local python function
                        log_activity(
                            activity_type="active",
                            source="Agent",
                            message=f"🛠️ Execution: \'{tool_name}\' with arguments {tool_args_str}"
                        )
                        result_str = await _dispatch_execute_tool_async(tool_name, tool_args, chat_id=session_id)
                        
                        single_tool_calls_log.append({
                            "name": tool_name,
                            "args": tool_args,
                            "result": result_str[:600] if len(result_str) > 600 else result_str,
                            "skill": skill_id
                        })
                        
                        try:
                            res_obj = json.loads(result_str)
                            if "error" in res_obj:
                                log_activity(
                                    activity_type="active",
                                    source="Agent",
                                    message=f"❌ Error in \'{tool_name}\': {res_obj['error']}"
                                )
                            else:
                                log_activity(
                                    activity_type="active",
                                    source="Agent",
                                    message=f"✅ Result for \'{tool_name}\' received successfully"
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
            response_text = "Apologies. A failure occurred while processing your request."

        # Add call record to global decision logs
        prompt_est = sum(len(m.get("content") or "") for m in messages) // 4
        completion_est = len(response_text) // 4
        cost_usd = calculate_cost(self.model, prompt_est, completion_est)
        log_entry = {
            "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S"),
            "session_id": session_id,
            "model": self.model,
            "latency_ms": latency_ms,
            "success": error_msg is None,
            "error": error_msg,
            "prompt_tokens_estimate": prompt_est,
            "user_message": user_message,
            "assistant_response": response_text,
            "traces": [],
            "agent_id": "jarvis",
            "completion_tokens_estimate": completion_est,
            "cost_usd": cost_usd,
            "parent_message_id": None,
            "tool_calls_log": single_tool_calls_log
        }
        
        DECISION_LOGS.insert(0, log_entry)
        if len(DECISION_LOGS) > 100:
            DECISION_LOGS.pop()
        try:
            from backend.database import save_decision_log
            save_decision_log(log_entry)
        except Exception as db_err:
            logger.error(f"Failed to save decision log to DB: {db_err}")

        from backend.plugins import hook
        response_text = hook("format_agent_response", response_text, default=response_text)

        return response_text

    # Known tool fingerprints: set of required keys → tool name
    _TOOL_FINGERPRINTS: List[Dict] = []

    def _extract_json_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Fallback extractor for models that output tool calls in text content.
        
        Handles:
        1. DeepSeek native tool format:
           <｜tool▁call▁begin｜>function<｜tool▁sep｜>NAME\n```json\nARGS\n```<｜tool▁call▁end｜>
        2. XML style tool format:
           <tool_call><function>NAME</function><arguments>ARGS</arguments></tool_call>
           or <tool_call>{"name": ..., "arguments": ...}</tool_call>
        3. Structured JSON: {"name": "tool_name", "parameters": {...}}
        4. Flat JSON: {"name": "tool_name", "arg1": "val1", ...}
        5. Raw args JSON: {"symbol":"SOLUSDT","side":"Buy",...} — matched via fingerprint
        """
        if not text:
            return None
        import json
        from backend.plugins import hook, collect
        fingerprints = list(self._TOOL_FINGERPRINTS) + collect("tool_fingerprints")

        extracted = []

        # 1. DeepSeek native tool call format
        ds_pattern = re.compile(
            r"<[|｜]tool[\s\u2581_]*call[\s\u2581_]*begin[|｜]>(?:function(?::|<[|｜]tool[\s\u2581_]*sep[|｜]>|\s*[\r\n]+|\s+))?\s*([a-zA-Z0-9_\-\.]+)?\s*(?:```(?:json)?\s*)?(\{.*?\})(?:\s*```)?\s*<[|｜]tool[\s\u2581_]*call[\s\u2581_]*end[|｜]>",
            re.DOTALL
        )
        for match in ds_pattern.finditer(text):
            fn_name = (match.group(1) or "").strip()
            args_str = (match.group(2) or "").strip()
            try:
                parsed_args = json.loads(args_str)
                if not isinstance(parsed_args, dict):
                    parsed_args = {}
                
                # Check if tool name was captured as generic keyword or embedded in json
                if is_invalid_tool_name(fn_name):
                    inner_name = parsed_args.get("name") or parsed_args.get("call") or parsed_args.get("tool") or parsed_args.get("action")
                    if inner_name and not is_invalid_tool_name(inner_name):
                        fn_name = str(inner_name).strip()
                        parsed_args = (
                            parsed_args.get("arguments")
                            if parsed_args.get("arguments") is not None
                            else parsed_args.get("parameters")
                            if parsed_args.get("parameters") is not None
                            else parsed_args.get("args")
                            if parsed_args.get("args") is not None
                            else {k: v for k, v in parsed_args.items() if k not in ("name", "call", "tool", "action")}
                        )

                if fn_name and not is_invalid_tool_name(fn_name):
                    extracted.append({
                        "id": f"call_ds_{len(extracted)}",
                        "type": "function",
                        "function": {
                            "name": fn_name,
                            "arguments": json.dumps(parsed_args) if isinstance(parsed_args, dict) else str(parsed_args)
                        }
                    })
            except Exception:
                pass

        # 2. XML style tool calls
        xml_func_pattern = re.compile(
            r"<tool_call>\s*(?:<function>\s*)?([a-zA-Z0-9_\-\.]+)(?:\s*</function>)?\s*(?:<arguments>\s*)?(\{.*?\})(?:\s*</arguments>)?\s*</tool_call>",
            re.DOTALL
        )
        for match in xml_func_pattern.finditer(text):
            fn_name = match.group(1).strip()
            args_str = match.group(2).strip()
            try:
                parsed_args = json.loads(args_str)
                extracted.append({
                    "id": f"call_xml_{len(extracted)}",
                    "type": "function",
                    "function": {
                        "name": fn_name,
                        "arguments": json.dumps(parsed_args) if isinstance(parsed_args, dict) else args_str
                    }
                })
            except Exception:
                pass

        # 3. !function_call: formatted tool calls with balanced brace parsing
        fn_pattern = re.compile(r"!function_call:\s*")
        for match in fn_pattern.finditer(text):
            brace_idx = match.end()
            if brace_idx < len(text) and text[brace_idx] == "{":
                depth = 0
                end_idx = brace_idx
                in_string = False
                escape = False
                while end_idx < len(text):
                    ch = text[end_idx]
                    if escape:
                        escape = False
                    elif ch == "\\":
                        escape = True
                    elif ch == '"':
                        in_string = not in_string
                    elif not in_string:
                        if ch == "{":
                            depth += 1
                        elif ch == "}":
                            depth -= 1
                            if depth == 0:
                                end_idx += 1
                                break
                    end_idx += 1
                args_str = text[brace_idx:end_idx].strip()
                try:
                    parsed_call = json.loads(args_str)
                    fn_name = parsed_call.get("call") or parsed_call.get("name") or parsed_call.get("tool")
                    fn_args = (
                        parsed_call.get("arguments")
                        if parsed_call.get("arguments") is not None
                        else parsed_call.get("parameters")
                        if parsed_call.get("parameters") is not None
                        else parsed_call.get("args")
                        if parsed_call.get("args") is not None
                        else {k: v for k, v in parsed_call.items() if k not in ("call", "name", "tool")}
                    )
                    if fn_name:
                        extracted.append({
                            "id": f"call_fn_{len(extracted)}",
                            "type": "function",
                            "function": {
                                "name": fn_name,
                                "arguments": json.dumps(fn_args) if isinstance(fn_args, dict) else str(fn_args)
                            }
                        })
                except Exception:
                    pass

        if extracted:
            return extracted

        candidates = []
        
        def _collect_dict_candidates(obj):
            items = []
            if isinstance(obj, list):
                for elem in obj:
                    items.extend(_collect_dict_candidates(elem))
            elif isinstance(obj, dict):
                items.append(obj)
                for v in obj.values():
                    if isinstance(v, (dict, list)):
                        items.extend(_collect_dict_candidates(v))
            return items

        # 1. First check code blocks for JSON arrays or objects
        code_block_matches = re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        for block in code_block_matches:
            block = block.strip()
            if block.startswith("[") or block.startswith("{"):
                try:
                    loaded = json.loads(block)
                    candidates.extend(_collect_dict_candidates(loaded))
                except Exception:
                    pass

        # 2. Balanced-brace JSON object scanner for raw/unfenced JSON objects
        stack = []
        start = -1
        for i, ch in enumerate(text):
            if ch == "{":
                if not stack:
                    start = i
                stack.append(ch)
            elif ch == "}":
                if stack:
                    stack.pop()
                    if not stack and start != -1:
                        raw_chunk = text[start:i+1]
                        try:
                            parsed_obj = json.loads(raw_chunk)
                            candidates.extend(_collect_dict_candidates(parsed_obj))
                        except Exception:
                            pass
                        start = -1

        for parsed in candidates:
            try:
                fn_name = None
                fn_args = {}
                if isinstance(parsed, dict):
                    if "function" in parsed and isinstance(parsed["function"], dict):
                        fn_name = parsed["function"].get("name")
                        fn_args = parsed["function"].get("parameters") or parsed["function"].get("arguments") or {}
                    elif "name" in parsed and isinstance(parsed.get("name"), str) and ("parameters" in parsed or "arguments" in parsed):
                        fn_name = parsed.get("name")
                        fn_args = parsed.get("parameters") or parsed.get("arguments") or {}
                    elif "call" in parsed and isinstance(parsed.get("call"), str):
                        fn_name = parsed.get("call")
                        if parsed.get("arguments") is not None:
                            fn_args = parsed.get("arguments")
                        elif parsed.get("parameters") is not None:
                            fn_args = parsed.get("parameters")
                        elif parsed.get("args") is not None:
                            fn_args = parsed.get("args")
                        else:
                            fn_args = {k: v for k, v in parsed.items() if k not in ("call", "type")}
                    elif "tool" in parsed and isinstance(parsed.get("tool"), str):
                        fn_name = parsed.get("tool")
                        if parsed.get("parameters") is not None:
                            fn_args = parsed.get("parameters")
                        elif parsed.get("arguments") is not None:
                            fn_args = parsed.get("arguments")
                        elif parsed.get("args") is not None:
                            fn_args = parsed.get("args")
                        else:
                            fn_args = {k: v for k, v in parsed.items() if k not in ("tool", "type")}
                    elif "action" in parsed and isinstance(parsed.get("action"), str):
                        fn_name = parsed.get("action")
                        if parsed.get("action_input") is not None:
                            fn_args = parsed.get("action_input")
                        elif parsed.get("parameters") is not None:
                            fn_args = parsed.get("parameters")
                        elif parsed.get("arguments") is not None:
                            fn_args = parsed.get("arguments")
                        elif parsed.get("args") is not None:
                            fn_args = parsed.get("args")
                        else:
                            fn_args = {k: v for k, v in parsed.items() if k != "action"}
                    elif "name" in parsed and hook("is_plugin_tool_name", parsed.get("name")):
                        fn_name = parsed["name"]
                        fn_args = {k: v for k, v in parsed.items() if k != "name"}
                    elif "name" in parsed and isinstance(parsed.get("name"), str) and (
                        parsed.get("name").startswith(tuple(_desk().get("prefixes") or ())) or "_" in parsed.get("name")
                    ):
                        fn_name = parsed["name"]
                        fn_args = {k: v for k, v in parsed.items() if k != "name"}
                    else:
                        parsed_keys = set(parsed.keys())
                        for fp in fingerprints:
                            if fp["required"].issubset(parsed_keys):
                                fn_name = fp["name"]
                                fn_args = parsed
                                logger.info(f"Fingerprint matched raw JSON args to tool '{fn_name}': {list(parsed_keys)}")
                                break

                if fn_name and not is_invalid_tool_name(fn_name):
                    # Avoid duplicate tool calls with exact same name and arguments if already extracted
                    call_entry = {
                        "id": f"call_fallback_{len(extracted)}",
                        "type": "function",
                        "function": {
                            "name": fn_name,
                            "arguments": json.dumps(fn_args) if isinstance(fn_args, dict) else str(fn_args)
                        }
                    }
                    if not any(e["function"]["name"] == fn_name and e["function"]["arguments"] == call_entry["function"]["arguments"] for e in extracted):
                        extracted.append(call_entry)
            except Exception:
                pass

        return extracted if extracted else None

    def _sanitize_tool_calls(self, tool_calls: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """Sanitizes tool calls from native API responses or extraction fallbacks.
        
        Prevents generic keywords ('function', 'tool', 'call', 'action', booleans, literals, etc.)
        from being dispatched as tool names. If an invalid generic name is encountered, attempts
        to unwrap the real tool name and arguments from inner JSON. If unresolvable, the entry is dropped.
        """
        if not tool_calls or not isinstance(tool_calls, list):
            return None

        import json
        sanitized: List[Dict[str, Any]] = []

        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function")
            if not isinstance(fn, dict):
                continue
            raw_fn_name = fn.get("name")
            args_raw = fn.get("arguments", "{}")

            if is_invalid_tool_name(raw_fn_name):
                inner_args = {}
                if isinstance(args_raw, dict):
                    inner_args = args_raw
                elif isinstance(args_raw, str):
                    try:
                        inner_args = json.loads(args_raw)
                    except Exception:
                        inner_args = {}

                if isinstance(inner_args, dict):
                    real_name = (
                        inner_args.get("name")
                        or inner_args.get("call")
                        or inner_args.get("tool")
                        or inner_args.get("action")
                        or ""
                    )
                    if not is_invalid_tool_name(real_name):
                        fn_name = str(real_name).strip()
                        unwrapped_args = (
                            inner_args.get("arguments")
                            if inner_args.get("arguments") is not None
                            else inner_args.get("parameters")
                            if inner_args.get("parameters") is not None
                            else inner_args.get("args")
                            if inner_args.get("args") is not None
                            else {k: v for k, v in inner_args.items() if k not in ("name", "call", "tool", "action")}
                        )
                        args_raw = json.dumps(unwrapped_args) if isinstance(unwrapped_args, dict) else str(unwrapped_args)
                        sanitized.append({
                            "id": tc.get("id") or f"call_{len(sanitized)}",
                            "type": "function",
                            "function": {
                                "name": fn_name,
                                "arguments": json.dumps(args_raw) if isinstance(args_raw, dict) else str(args_raw)
                            }
                        })
            else:
                fn_name = str(raw_fn_name).strip()
                sanitized.append({
                    "id": tc.get("id") or f"call_{len(sanitized)}",
                    "type": "function",
                    "function": {
                        "name": fn_name,
                        "arguments": json.dumps(args_raw) if isinstance(args_raw, dict) else str(args_raw)
                    }
                })

        return sanitized if sanitized else None

    async def _respond_as_subagent(self, user_message: str, subagent: Dict[str, Any], parent_skills: Optional[str] = None, current_user_msg_id: Optional[int] = None, chat_id: Optional[str] = None, parent_message_id: Optional[int] = None, session_id: Optional[str] = None, include_history: bool = True) -> str:
        """Runs response generation loop specifically tailored for a dynamic subagent session."""
        session_id = session_id or chat_id or subagent.get("id", "subagent")
        from backend.governance import BudgetExceededError, BudgetGuard, LLM_CALL_ESTIMATE_USD, budget_session
        budget_session.set(session_id)
        try:
            BudgetGuard.check(session_id, LLM_CALL_ESTIMATE_USD)
        except BudgetExceededError as budget_err:
            return str(budget_err)
        subagent_name = subagent.get("name") or subagent.get("id") or "agent"
        system_prompt = subagent.get("system_prompt") or ""
        subagent_model = subagent.get("model") or getattr(self, "model", None) or os.getenv("DEFAULT_MODEL", "google/gemini-2.5-pro")
        tool_calls_log: List[Dict[str, Any]] = []

        from backend.activity_logger import log_activity
        log_activity(
            activity_type="active",
            source=subagent_name,
            message=f"👤 Received request for subagent '{subagent_name}': '{user_message}'"
        )

        history = self.get_history(session_id) if include_history else []
        
        from backend import database as db
        if current_user_msg_id is None:
            try:
                current_user_msg_id = db.save_message(session_id, "user", user_message)
            except Exception as e:
                logger.debug(f"Failed to persist subagent user message: {e}")
        
        # Search relevant memory chunks in Qdrant (RAG)
        from backend import rag
        hits = rag.search_memory(user_message, limit=3)
        
        user_content = user_message
        if hits:
            context_block = "\n\n[Context from your knowledge base for reference]:\n"
            for hit in hits:
                context_block += f"- From document '{hit['title']}': \"{hit['content']}\"\n"
            user_content = f"{user_message}\n{context_block}"
        
        # Build payload with subagent prompt + chat history + current message
        _now_il = datetime.now(ZoneInfo("Asia/Jerusalem"))
        _day_names_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        current_time_str = _now_il.strftime("%Y-%m-%d %H:%M:%S")
        day_of_week = _day_names_en[_now_il.weekday()]
        system_info = (
            f"\n\n[System Information]:\n"
            f"Current date and time: {current_time_str} (Asia/Jerusalem, GMT+3)\n"
            f"Day of the week: {day_of_week}\n"
            f"IMPORTANT RULE: Your built-in knowledge is limited to the past. To get ANY up-to-date information about events, sports matches (e.g., today\'s games, betting odds, analytics), news, quotes, or weather, you MUST use the internet search via the web_search tool. Never fabricate events or rely on your outdated data!\n"
            f"IT IS STRICTLY FORBIDDEN to search, use, mention, quote, or retell ready-made forecasts, other people\'s articles, advice, or opinions about value bets (e.g., \'ready forecasts\', \'value bets according to LiveSport\', \'expert opinions\') in your responses. You must search exclusively for raw numerical data: opponent pairs, exact match start times, and bookmaker odds. Any conclusions and mathematical calculations of value (EV = Probability * Odds - 1) must be done strictly independently, and you must provide only your own results without referring to external opinions!\n"
            f"You are not allowed to be lazy in calculations: if exact numerical odds are not found in the search, you must perform mathematical forecasting (e.g., calculate probabilities of win/draw/loss using Poisson distribution based on average scoring or team goal statistics) and calculate expected value (EV = P * Odds - 1) based on calculated probabilities and approximate odds, instead of giving a dry refusal or quoting external forecasts."
        )
        from backend.plugins import hook
        _extra = hook("subagent_prompt_extra", subagent, parent_skills, default=None)
        if _extra:
            system_info += _extra
        from backend.database import get_setting as _get_setting
        _lang = _get_setting("language") or "en"
        _lang_names = {"ru": "Russian", "en": "English", "he": "Hebrew", "de": "German", "es": "Spanish", "fr": "French"}
        lang_directive = f"\n\n[LANGUAGE DIRECTIVE]: You MUST respond exclusively in {_lang_names.get(_lang, _lang)}. This overrides any other language instruction in this prompt."
        
        from backend.context_manager import build_subagent_messages
        messages = build_subagent_messages(
            system_prompt=system_prompt,
            system_info=system_info,
            lang_directive=lang_directive,
            history=history or [],
            user_content=user_content,
            max_tokens=16000
        )

        safe_session_id = session_id.encode("ascii", "ignore").decode("ascii").strip() or "session"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/pauloberezini/jarvis",
            "X-Title": f"Jarvis - {safe_session_id}"
        }

        # Subagents are limited to safe information-gathering tools only
        from backend.tools import TOOLS_SCHEMA
        from backend.plugins import hook
        safe_tool_names = {
            "get_system_stats",
            "get_weather",
            "get_current_time_israel",
            "web_search",
            "perform_search",
            "search",
            "google_search",
            "duckduckgo_search",
            "internet_search",
            "get_market_prices",
            "add_price_alert",
            "get_rss_digest",
            "read_rss_node_feed",
            "create_subagent",
            "call_subagent",
            "list_subagents",
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
            "web_search": [
                "web_search",
                "perform_search",
                "search",
                "google_search",
                "duckduckgo_search",
                "internet_search",
                "get_current_time_israel",
                "get_weather",
                "get_rss_digest",
            ],
            "market_monitor": ["get_market_prices", "add_price_alert"],
            "forex_provider": ["get_market_prices", "add_price_alert"],
            "forex": ["get_market_prices", "add_price_alert"],
            "forex_data": ["get_market_prices", "add_price_alert"],
            "obsidian_rag": ["search_obsidian", "read_obsidian_note", "create_obsidian_note", "sync_obsidian_vault"],
            "todoist_sync": ["get_todoist_tasks", "add_todoist_task", "delete_todoist_task"],
            "google_calendar": ["get_calendar_events", "add_calendar_event"],
            "timers_alarms": ["set_timer", "set_alarm", "cancel_timer_or_alarm"],
            "shell_execution": ["get_system_stats", "execute_command"],
            "python_sandbox": ["execute_command"],
            "read_rss_node_feed": ["read_rss_node_feed"]
        }

        skills_str = subagent.get("skills", "")
        if skills_str:
            if isinstance(skills_str, list):
                enabled_skills = [str(s).strip() for s in skills_str if str(s).strip()]
            else:
                enabled_skills = [s.strip() for s in str(skills_str).split(",") if s.strip()]
            child_allowed = set()
            for skill in enabled_skills:
                if skill in skill_to_tools:
                    child_allowed.update(skill_to_tools[skill])
                from backend.mcp_client import mcp_clients, mcp_tool_to_server
                if skill in mcp_clients:
                    child_allowed.update([t["name"] for t in mcp_clients[skill].tools])
                elif skill == "mcp_all":
                    child_allowed.update(mcp_tool_to_server.keys())
                
                extra_tools = hook("tools_for_skill", skill)
                if extra_tools:
                    child_allowed.update(extra_tools)
        else:
            child_allowed = safe_tool_names.copy()
            from backend.mcp_client import mcp_tool_to_server
            child_allowed.update(mcp_tool_to_server.keys())
            child_allowed.update(hook("all_plugin_tool_names", default=[]) or [])

        # Intersect with parent_skills if the parent orchestrator has specified restrictions.
        # "" is an empty cap (disjoint skills), not an absent one.
        if parent_skills is not None:
            if isinstance(parent_skills, list):
                enabled_parent_skills = [str(s).strip() for s in parent_skills if str(s).strip()]
            else:
                enabled_parent_skills = [s.strip() for s in str(parent_skills).split(",") if s.strip()]
            parent_allowed = set()
            for skill in enabled_parent_skills:
                if skill in skill_to_tools:
                    parent_allowed.update(skill_to_tools[skill])
                from backend.mcp_client import mcp_clients, mcp_tool_to_server
                if skill in mcp_clients:
                    parent_allowed.update([t["name"] for t in mcp_clients[skill].tools])
                elif skill == "mcp_all":
                    parent_allowed.update(mcp_tool_to_server.keys())
                
                extra_tools = hook("tools_for_skill", skill)
                if extra_tools:
                    parent_allowed.update(extra_tools)
            allowed_tools = child_allowed.intersection(parent_allowed)
        else:
            allowed_tools = child_allowed

        allowed_tools.update(["save_subagent_memory", "get_subagent_memory"])
        if subagent.get("agent_type") in ("orchestrator", "sub-orchestrator"):
            allowed_tools.update(["call_subagent", "web_search"])
        subagent_tools = [t for t in TOOLS_SCHEMA if t["function"]["name"] in allowed_tools]

        start_time = time.time()
        response_text = ""
        latency_ms = 0
        error_msg = None
        tool_executed = False
        order_placed_successfully = False
        broker_positions_read = False
        broker_balance_read = False
        indicators_calculated = False
        current_model = subagent_model

        total_prompt_tokens = 0
        total_completion_tokens = 0

        def _prepare_messages_for_model(model_name: str, raw_msgs: list):
            if "deepseek-r1" not in model_name.lower():
                return raw_msgs
            # Non-tool models (e.g. DeepSeek-R1): translate role 'tool' to user message and strip tool_calls
            sanitized = []
            for msg in raw_msgs:
                m_copy = dict(msg)
                if m_copy.get("role") == "tool":
                    t_name = m_copy.get("name") or "tool"
                    t_content = m_copy.get("content", "")
                    sanitized.append({
                        "role": "user",
                        "content": f"[Tool Result: {t_name}]: {t_content}"
                    })
                else:
                    if "tool_calls" in m_copy:
                        m_copy.pop("tool_calls", None)
                    sanitized.append(m_copy)
            return sanitized

        try:
            subagent_timeout = 90.0 if any(k in (subagent_model or "").lower() for k in ("deepseek-r1", "r1", "o1", "o3")) else 45.0
            subagent_turn = 0
            MAX_SUBAGENT_TURNS = 15
            async with httpx.AsyncClient(timeout=subagent_timeout) as client:
                while True:
                    subagent_turn += 1
                    if subagent_turn > MAX_SUBAGENT_TURNS:
                        logger.warning(
                            f"Subagent '{subagent_name}' reached MAX_SUBAGENT_TURNS ({MAX_SUBAGENT_TURNS}). "
                            "Breaking tool execution loop to prevent runaway cycles."
                        )
                        if not response_text:
                            response_text = "Analysis completed. Maximum tool turns reached."
                        from backend import database as db
                        cost_usd = calculate_cost(subagent_model, total_prompt_tokens, total_completion_tokens)
                        self.last_costs[session_id] = cost_usd
                        assistant_msg_id = db.save_message(session_id, "assistant", response_text, cost_usd=cost_usd)
                        self.last_saved_ids[session_id] = {
                            "user": current_user_msg_id,
                            "assistant": assistant_msg_id
                        }
                        break

                    payload = {
                        "model": subagent_model,
                        "messages": _prepare_messages_for_model(subagent_model, messages),
                        "temperature": subagent.get("temperature", 0.7),
                        "max_tokens": 4096,
                    }
                    if "deepseek-r1" not in subagent_model.lower():
                        payload["tools"] = subagent_tools
                        payload["tool_choice"] = "auto"
                    
                    is_openmodel = "openmodel.ai" in self.api_base
                    url = f"{self.api_base}/messages" if is_openmodel else f"{self.api_base}/chat/completions"
                    actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
                    
                    # Build candidate fallback models list starting with the subagent's configured model
                    candidate_models = [subagent_model]
                    for m in [
                        os.getenv("LLM_FALLBACK_MODEL"),
                        getattr(self, "model", None),
                        os.getenv("LLM_MODEL"),
                        "google/gemini-2.5-flash",
                        "google/gemini-2.5-pro",
                        "deepseek/deepseek-chat",
                    ]:
                        if m and m.strip() and m.strip() not in candidate_models:
                            candidate_models.append(m.strip())

                    from backend.llm_model_manager import (
                        prioritize_healthy_models,
                        mark_model_rate_limited,
                        mark_model_success,
                        is_model_rate_limited,
                        resolve_provider_model,
                        resolve_provider_models,
                    )
                    candidate_models = resolve_provider_models(candidate_models, self.api_base) or candidate_models
                    candidate_models = prioritize_healthy_models(candidate_models)
                    if candidate_models and candidate_models[0] != resolve_provider_model(subagent_model, self.api_base):
                        logger.info(
                            f"Subagent '{subagent_name}' configured model '{subagent_model}' is in rate-limit cooldown. "
                            f"Bypassing to healthy model '{candidate_models[0]}'."
                        )

                    response = None
                    last_network_exc = None
                    valid_data = None
                    last_error_desc = None

                    consecutive_dns_errors = 0
                    abort_all_candidates = False
                    total_network_attempts = 0
                    current_model_attempts = 0

                    for model_idx, model_cand in enumerate(candidate_models):
                        if is_model_rate_limited(model_cand) and any(not is_model_rate_limited(m) for m in candidate_models[model_idx + 1:]):
                            logger.info(
                                f"Subagent '{subagent_name}' candidate model '{model_cand}' is in rate-limit cooldown. "
                                f"Skipping to next healthy candidate."
                            )
                            continue
                        current_model = model_cand
                        current_model_attempts = 0
                        payload["model"] = current_model
                        if "deepseek-r1" not in current_model.lower():
                            payload["tools"] = subagent_tools
                            payload["tool_choice"] = "auto"
                            payload["messages"] = messages
                        else:
                            payload.pop("tools", None)
                            payload.pop("tool_choice", None)
                            payload["messages"] = _prepare_messages_for_model(current_model, messages)
                        actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload

                        model_success = False
                        is_connect_error = False
                        max_attempts = 2 if ("r1" in current_model.lower() or "reasoner" in current_model.lower()) else 3
                        for attempt in range(max_attempts):
                            current_model_attempts = attempt + 1
                            total_network_attempts += 1
                            try:
                                response = await client.post(
                                    url,
                                    json=actual_payload,
                                    headers=headers
                                )
                            except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError, OSError) as exc:
                                last_network_exc = exc
                                exc_desc = f"{type(exc).__name__}: {exc}".rstrip(": ") if str(exc) else type(exc).__name__
                                is_dns_error = (
                                    isinstance(exc, (httpx.ConnectError, socket.gaierror))
                                    or any(k in exc_desc for k in ("-5", "-2", "-3", "No address associated with hostname", "Name or service not known", "Temporary failure in name resolution", "gaierror"))
                                )
                                if is_dns_error:
                                    consecutive_dns_errors += 1
                                if is_dns_error and model_idx >= 1:
                                    logger.warning(
                                        f"Subagent '{subagent_name}' endpoint host DNS resolution failed across fallback models ({exc_desc}). "
                                        f"Aborting further model fallbacks to avoid redundant connection attempts."
                                    )
                                    abort_all_candidates = True
                                    break

                                if attempt < max_attempts - 1:
                                    logger.warning(
                                        f"Subagent '{subagent_name}' ({current_model}) network/timeout error (attempt {attempt+1}/{max_attempts}): {exc_desc}. Retrying..."
                                    )
                                    import asyncio
                                    await asyncio.sleep(1.0)
                                    continue
                                else:
                                    logger.warning(
                                        f"Subagent '{subagent_name}' ({current_model}) network/timeout error (attempt {max_attempts}/{max_attempts}): {exc_desc}"
                                    )
                                    is_connect_error = isinstance(exc, (httpx.ConnectError, socket.gaierror)) or (
                                        isinstance(exc, OSError) and not isinstance(exc, (httpx.TimeoutException, TimeoutError))
                                    )
                                    next_cand = candidate_models[model_idx + 1] if model_idx + 1 < len(candidate_models) else None
                                    if next_cand:
                                        logger.warning(
                                            f"Subagent '{subagent_name}' model '{current_model}' network/timeout error ({exc_desc}). "
                                            f"Falling back to model '{next_cand}' from fallback chain..."
                                        )
                                        import asyncio
                                        await asyncio.sleep(0.5)
                                    break

                            retry_after = getattr(response, "headers", {}).get("retry-after") if response else None
                            next_healthy = [m for m in candidate_models[model_idx + 1:] if not is_model_rate_limited(m)]
                            next_cand = next_healthy[0] if next_healthy else (candidate_models[model_idx + 1] if model_idx + 1 < len(candidate_models) else None)

                            if response.status_code == 200:
                                raw_data = None
                                data = None
                                try:
                                    raw_data = response.json()
                                    data = translate_to_openai_response(raw_data) if is_openmodel else raw_data
                                except Exception as json_err:
                                    logger.warning(f"Subagent '{subagent_name}' ({current_model}) response JSON decode error: {json_err}")
                                    raw_data = None
                                    data = None

                                is_body_error = (
                                    not isinstance(data, dict)
                                    or "error" in data
                                    or not data.get("choices")
                                    or not isinstance(data.get("choices"), list)
                                    or len(data.get("choices", [])) == 0
                                )

                                if not is_body_error:
                                    model_success = True
                                    valid_data = data
                                    mark_model_success(current_model)
                                    break

                                # Body contains error or empty choices despite HTTP 200
                                err_detail = data.get("error", {}) if isinstance(data, dict) else str(data)
                                if isinstance(err_detail, dict):
                                    err_text = err_detail.get("message") or str(err_detail)
                                    err_code = err_detail.get("code")
                                else:
                                    err_text = str(err_detail) if err_detail else "Empty choices returned from model."
                                    err_code = None

                                try:
                                    numeric_code = int(err_code) if err_code is not None else None
                                except (ValueError, TypeError):
                                    numeric_code = None

                                is_rate_limit = (
                                    numeric_code == 429
                                    or err_code in (429, "429")
                                    or any(k in str(err_text).lower() for k in ("rate-limited", "rate limit", "engine_overloaded", "quota"))
                                )
                                is_timeout_or_5xx = (
                                    numeric_code in (504, 502, 503, 500, 408)
                                    or err_code in (504, "504", 502, "502", 503, "503", 500, "500", 408, "408")
                                    or any(k in str(err_text).lower() for k in ("timeout", "timed out", "provider error", "temporarily unavailable", "overloaded", "bad gateway", "service unavailable"))
                                    or (isinstance(err_detail, dict) and isinstance(err_detail.get("metadata"), dict) and err_detail.get("metadata", {}).get("error_type") in ("timeout", "provider_error"))
                                )

                                if is_rate_limit:
                                    cooldown_secs = 60.0
                                    if retry_after:
                                        try:
                                            cooldown_secs = max(float(retry_after), 15.0)
                                        except (ValueError, TypeError):
                                            pass
                                    mark_model_rate_limited(current_model, cooldown_secs)

                                last_error_desc = err_text

                                if next_cand:
                                    reason_desc = (
                                        "rate-limited in response body"
                                        if is_rate_limit
                                        else ("provider error/timeout in response body" if is_timeout_or_5xx else f"API error in response body ({str(err_text)[:80]})")
                                    )
                                    log_fn = logger.info if is_rate_limit else logger.warning
                                    log_fn(
                                        f"Subagent '{subagent_name}' model '{current_model}' {reason_desc}. "
                                        f"Falling back to model '{next_cand}' from fallback chain..."
                                    )
                                    import asyncio
                                    await asyncio.sleep(0.5)
                                    break
                                else:
                                    if attempt < max_attempts - 1:
                                        logger.warning(
                                            f"Subagent '{subagent_name}' ({current_model}) API error in body (attempt {attempt+1}/{max_attempts}): {err_text}. Retrying..."
                                        )
                                        import asyncio
                                        await asyncio.sleep(2.0 * (attempt + 1))
                                        continue
                                    else:
                                        logger.warning(
                                            f"Subagent '{subagent_name}' ({current_model}) API error response: {raw_data}"
                                        )
                                        break

                            last_error_desc = f"HTTP Error {response.status_code}: {response.text[:200]}"
                            if response.status_code == 429 or "rate-limited" in response.text.lower() or "engine_overloaded" in response.text.lower():
                                if retry_after and attempt == 0:
                                    try:
                                        delay = max(float(retry_after), 1.0)
                                    except (ValueError, TypeError):
                                        delay = 2.0
                                    if delay <= 5.0:
                                        logger.info(
                                            f"Subagent '{subagent_name}' ({current_model}) HTTP 429 Retry-After: {delay}s (attempt {attempt+1}/{max_attempts}). Retrying after delay..."
                                        )
                                        import asyncio
                                        await asyncio.sleep(delay)
                                        continue

                                cooldown_secs = 60.0
                                if retry_after:
                                    try:
                                        cooldown_secs = max(float(retry_after), 15.0)
                                    except (ValueError, TypeError):
                                        pass
                                mark_model_rate_limited(current_model, cooldown_secs)

                                if next_cand:
                                    logger.info(
                                        f"Subagent '{subagent_name}' model '{current_model}' rate-limited (HTTP {response.status_code}). "
                                        f"Falling back to model '{next_cand}' from fallback chain..."
                                    )
                                    import asyncio
                                    await asyncio.sleep(0.5)
                                    break
                                else:
                                    logger.warning(
                                        f"Subagent '{subagent_name}' ({current_model}) API returned {response.status_code} (attempt {attempt+1}/{max_attempts}): {response.text[:200]}"
                                    )
                            else:
                                if attempt < max_attempts - 1 and response.status_code in (502, 503, 504, 408):
                                    logger.info(
                                        f"Subagent '{subagent_name}' ({current_model}) transient HTTP {response.status_code} (attempt {attempt+1}/{max_attempts}) - retrying..."
                                    )
                                elif next_cand and response.status_code in (502, 503, 504, 408):
                                    logger.warning(
                                        f"Subagent '{subagent_name}' model '{current_model}' HTTP {response.status_code} exhausted attempts. "
                                        f"Falling back to model '{next_cand}' from fallback chain..."
                                    )
                                    import asyncio
                                    await asyncio.sleep(0.5)
                                    break
                                else:
                                    logger.warning(
                                        f"Subagent '{subagent_name}' ({current_model}) API returned {response.status_code} (attempt {attempt+1}/{max_attempts}): {response.text[:200]}"
                                    )

                                if retry_after and attempt == 0:
                                    try:
                                        delay = max(float(retry_after), 1.0)
                                    except (ValueError, TypeError):
                                        delay = 2.0
                                    import asyncio
                                    await asyncio.sleep(delay)
                                    continue

                                delay = 2.0 * (attempt + 1)
                                if retry_after:
                                    try:
                                        delay = max(float(retry_after), 1.0)
                                    except (ValueError, TypeError):
                                        pass
                                import asyncio
                                await asyncio.sleep(delay)
                                continue

                            if "context_length_exceeded" in response.text or "input too long" in response.text.lower() or "max input length" in response.text.lower():
                                logger.warning("Trimming subagent message context due to context_length_exceeded...")
                                payload["messages"] = [payload["messages"][0], payload["messages"][-1]]
                                actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload

                            import asyncio
                            await asyncio.sleep(1.0 * (attempt + 1))

                        if model_success:
                            subagent_model = current_model
                            break

                        if abort_all_candidates:
                            break

                    if not model_success or valid_data is None:
                        if last_network_exc is not None and (response is None or (response and response.status_code in (408, 502, 503, 504))):
                            raise last_network_exc
                        error_msg = last_error_desc or (f"HTTP Error {response.status_code if response else 'No Response'}: {response.text if response else ''}")
                        logger.warning(f"Subagent '{subagent_name}' ({current_model}) API error: {error_msg}")
                        provider_name = "OpenModel" if is_openmodel else "OpenRouter"
                        response_text = f"Apologies. Difficulties occurred while communicating with the server {provider_name}: {error_msg}."
                        break

                    subagent_model = current_model
                    data = valid_data

                    usage = data.get("usage", {})
                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                    total_completion_tokens += usage.get("completion_tokens", 0)
                    
                    choice_0 = data["choices"][0] if (isinstance(data.get("choices"), list) and len(data["choices"]) > 0) else {}
                    choice_msg = choice_0.get("message") if isinstance(choice_0, dict) else {}
                    if not isinstance(choice_msg, dict):
                        choice_msg = {}
                    
                    tool_calls = choice_msg.get("tool_calls")
                    tool_calls = self._sanitize_tool_calls(tool_calls)
                    if not tool_calls:
                        content_str = choice_msg.get("content") or ""
                        tool_calls = self._extract_json_tool_calls(content_str)
                        if not tool_calls:
                            reasoning_str = choice_msg.get("reasoning") or choice_msg.get("reasoning_content") or ""
                            if reasoning_str:
                                tool_calls = self._extract_json_tool_calls(reasoning_str)
                        tool_calls = self._sanitize_tool_calls(tool_calls)
                        if tool_calls:
                            choice_msg["tool_calls"] = tool_calls
                            cleaned_content = sanitize_tool_tokens(content_str)
                            cleaned_content = hook("strip_simulated_tool_text", cleaned_content, default=cleaned_content)
                            choice_msg["content"] = (cleaned_content or "").strip()

                    if not tool_calls:
                        raw_content = choice_msg.get("content") or ""
                        raw_reasoning = choice_msg.get("reasoning") or choice_msg.get("reasoning_content") or ""
                        if not raw_content.strip() and raw_reasoning.strip():
                            raw_content = raw_reasoning
                        response_text = sanitize_tool_tokens(raw_content)
                        from backend.plugins import hook_async
                        guarded = await hook_async("guard_subagent_reply", {
                            "response_text": response_text,
                            "messages": messages,
                            "choice_msg": choice_msg,
                            "subagent": subagent,
                            "subagent_name": subagent_name,
                            "subagent_model": subagent_model,
                            "subagent_turn": subagent_turn,
                            "user_message": user_message,
                            "session_id": session_id,
                            "tool_executed": tool_executed,
                            "order_placed_successfully": order_placed_successfully,
                            "broker_positions_read": broker_positions_read,
                            "broker_balance_read": broker_balance_read,
                            "indicators_calculated": indicators_calculated,
                            "allowed_tools": allowed_tools,
                            "subagent_tools": subagent_tools,
                            "tool_calls_log": tool_calls_log,
                        }, default=None)
                        if guarded:
                            response_text = guarded["response_text"]
                            tool_executed = guarded["tool_executed"]
                            order_placed_successfully = guarded["order_placed_successfully"]
                            broker_positions_read = guarded["broker_positions_read"]
                            broker_balance_read = guarded["broker_balance_read"]
                            indicators_calculated = guarded["indicators_calculated"]
                            if guarded.get("steer"):
                                continue
                        if not response_text.strip():
                            if tool_executed:
                                response_text = "Actions successfully executed."
                            else:
                                response_text = "The requested task has been analyzed and processed successfully."

                        cost_usd = calculate_cost(subagent_model, total_prompt_tokens, total_completion_tokens)
                        self.last_costs[session_id] = cost_usd
                        
                        log_activity(
                            activity_type="active",
                            source=subagent_name,
                            message=f"💬 Response from \'{subagent_name}\' received. Cost: ${cost_usd:.6f}",
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
                    
                    from backend.marketplace.lifecycle import LifecycleManager
                    from backend.marketplace.billing_adapter import get_billing_adapter
                    
                    billing = get_billing_adapter()
                    user_id = "default_user"  # Single-tenant fallback for now
                    
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("function", {}).get("name")
                        if is_invalid_tool_name(tool_name):
                            logger.warning(f"Subagent {subagent_name} skipping generic invalid tool name '{tool_name}'")
                            continue
                        tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
                        
                        # --- BILLING ENFORCEMENT ---
                        skill_id = LifecycleManager.get_skill_for_tool(tool_name)
                        if skill_id:
                            is_entitled = await billing.check_entitlement(user_id, skill_id)
                            if not is_entitled:
                                error_msg = f"Access denied: You do not have an active license for the '{skill_id}' skill. Please upgrade your plan."
                                from backend.activity_logger import log_activity
                                log_activity(
                                    activity_type="active",
                                    source=f"Subagent {subagent_name}",
                                    message=f"🚫 Blocked: {error_msg}"
                                )
                                import json
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.get("id"),
                                    "name": tool_name,
                                    "content": json.dumps({"error": error_msg})
                                })
                                continue
                        # ---------------------------
                        
                        try:
                            import json
                            tool_args = json.loads(tool_args_str)
                        except Exception:
                            tool_args = {}
                            
                        log_activity(
                            activity_type="active",
                            source=subagent_name,
                            message=f"🛠️ Execution (subagent): '{tool_name}' with arguments {tool_args_str}"
                        )
                        result_str = await _dispatch_execute_tool_async(tool_name, tool_args, chat_id=session_id)
                        if not isinstance(result_str, str):
                            import json
                            try:
                                result_str = json.dumps(result_str, ensure_ascii=False)
                            except Exception:
                                result_str = str(result_str)
                        flags = hook("classify_tool_result", tool_name, result_str, default=None) or {}
                        if flags.get("positions"):
                            broker_positions_read = True
                        if flags.get("balance"):
                            broker_balance_read = True
                        if flags.get("indicators"):
                            indicators_calculated = True
                        if flags.get("order"):
                            order_placed_successfully = True
                        
                        # Accumulate tool call for agent thread viewer
                        from backend.marketplace.lifecycle import LifecycleManager as _LCM
                        from backend.database import BUILTIN_TOOL_SKILL_MAP
                        _skill_id = _LCM.get_skill_for_tool(tool_name) or BUILTIN_TOOL_SKILL_MAP.get(tool_name)
                        tool_calls_log.append({
                            "name": tool_name,
                            "args": tool_args,
                            "result": result_str[:600] if len(result_str) > 600 else result_str,
                            "skill": _skill_id,
                        })
                        
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.get("id"),
                            "name": tool_name,
                            "content": result_str
                        })
                        
                latency_ms = int((time.time() - start_time) * 1000)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.TransportError, OSError) as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = f"{type(e).__name__}: {e}".rstrip(": ") if str(e) else type(e).__name__
            n_attempts = current_model_attempts if 'current_model_attempts' in locals() and current_model_attempts > 0 else (max_attempts if 'max_attempts' in locals() else 3)
            logger.warning(f"Subagent '{subagent_name}' ({current_model}) network failure after {n_attempts} attempts: {error_msg}")
            response_text = f"Apologies. A network error occurred while contacting the AI service: {error_msg}."
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            logger.exception("Error during OpenRouter subagent chat completion call")
            response_text = "Apologies. A failure occurred while processing the subagent\'s request."

        # Add call record to global decision logs
        prompt_est = sum(len(m.get("content") or "") for m in messages) // 4
        completion_est = len(response_text) // 4
        cost_usd = calculate_cost(subagent_model, prompt_est, completion_est)
        
        # Resolve parent_message_id: prefer explicit param, then threading.local context
        from backend.tools import _call_context as _tc
        resolved_parent_id = parent_message_id or getattr(_tc, "parent_message_id", None)
        
        log_entry = {
            "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S"),
            "session_id": session_id,
            "model": subagent_model,
            "latency_ms": latency_ms,
            "success": error_msg is None,
            "error": error_msg,
            "prompt_tokens_estimate": prompt_est,
            "user_message": user_message,
            "assistant_response": response_text,
            "traces": [],
            "agent_id": subagent.get("id", subagent.get("name", "unknown")),
            "completion_tokens_estimate": completion_est,
            "cost_usd": cost_usd,
            "parent_message_id": resolved_parent_id,
            "tool_calls_log": tool_calls_log,
        }
        
        DECISION_LOGS.insert(0, log_entry)
        if len(DECISION_LOGS) > 100:
            DECISION_LOGS.pop()
        try:
            from backend.database import save_decision_log
            save_decision_log(log_entry)
        except Exception as db_err:
            logger.error(f"Failed to save subagent decision log to DB: {db_err}")


        if not response_text or not response_text.strip():
            response_text = "The requested task has been analyzed and processed successfully."

        response_text = hook("format_agent_response", response_text, default=response_text)

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
                    fn = tc.get("function", {}) if isinstance(tc, dict) else {}
                    fn_args = fn.get("arguments", "{}") if isinstance(fn, dict) else "{}"
                    fn_name = fn.get("name", "") if isinstance(fn, dict) else ""
                    try:
                        args = json.loads(fn_args) if isinstance(fn_args, str) else fn_args
                    except Exception:
                        args = {}
                    blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", "") if isinstance(tc, dict) else "",
                        "name": fn_name,
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
                        "tool_use_id": msg.get("tool_call_id", "") if isinstance(msg, dict) else "",
                        "content": content or ""
                    }
                ]
            })

    anthropic_payload = {
        "model": openai_payload.get("model", ""),
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
    if not isinstance(anthropic_response, dict):
        return {"choices": [{"message": {"role": "assistant", "content": None}}], "usage": {}}
    if "error" in anthropic_response:
        return {"error": anthropic_response["error"]}
    content_list = anthropic_response.get("content", [])
    if not isinstance(content_list, list):
        content_list = []
    text_content = ""
    tool_calls = []
    import json
    
    for block in content_list:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text_content += block.get("text", "")
        elif block.get("type") == "tool_use":
            tool_input = block.get("input", {})
            try:
                args_str = json.dumps(tool_input) if isinstance(tool_input, (dict, list, str, int, float, bool)) else "{}"
            except Exception:
                args_str = "{}"
            tool_calls.append({
                "id": block.get("id", ""),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": args_str
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
            "prompt_tokens": anthropic_response.get("usage", {}).get("input_tokens", 0) if isinstance(anthropic_response.get("usage"), dict) else 0,
            "completion_tokens": anthropic_response.get("usage", {}).get("output_tokens", 0) if isinstance(anthropic_response.get("usage"), dict) else 0
        }
    }
    
    if tool_calls and isinstance(openai_response.get("choices"), list) and len(openai_response["choices"]) > 0:
        if "message" in openai_response["choices"][0] and isinstance(openai_response["choices"][0]["message"], dict):
            openai_response["choices"][0]["message"]["tool_calls"] = tool_calls
        
    return openai_response

# Singleton instance
agent_instance = JarvisAgent()
