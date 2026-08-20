import os
import time
import logging
from typing import List, Dict, Any, Optional
import httpx
from dotenv import load_dotenv

logger = logging.getLogger("hermes.agent")


load_dotenv()

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

async def classify_complexity(user_message: str, api_key: str, api_base: str) -> str:
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

    # Try LLM classifier with the fast/cheap planner model
    from backend.subagents import get_agent_model
    classifier_model = get_agent_model("planner", os.getenv("LLM_MODEL", "ollama/llama3"))

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
        logger.warning(f"Complexity classifier LLM call failed ({e}), falling back to keyword routing")
    
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
- If Sir asks to "create an agent," "make a sub-agent," "add a subagent," or "write an assistant," you MUST IMMEDIATELY call the `create_subagent` tool to persist it in the database. NEVER state or confirm that you created an agent unless the `create_subagent` tool call was executed and returned success!
- When calling `create_subagent`, you MUST explicitly specify the `model` argument, selecting the model according to the FUGU principle:
  * For sub-agents writing code, performing complex math calculations, programming, or requiring deep reasoning — choose the `deepseek/deepseek-r1` model.
  * For sub-agents oriented toward quick data analysis, formatting, or plotting (matplotlib) — choose the `ollama/llama3` model.
  * For sub-agents managing document indexing, processing research papers, knowledge curation, or RAG tasks (which require a large context window and robust tool calling) — choose the `ollama/llama3` model.
  * For simple tasks, quick web search, RSS news reading, or basic Q&A — choose the `deepseek/deepseek-v4-flash` model.
  * For general intellectual and text tasks of high complexity (sophisticated assistant) — choose the `ollama/llama3` model.


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
    Jarvis         — service records without a clear category
- NEVER ask Sir where to store a note — decide on your own. Subfolders are encouraged (e.g., Research/AI, Projects/Jarvis).

CRITICAL RULES FOR BCM & TRADING DECISIONS / TOOL OUTPUTS:
- NEVER output raw JSON blocks or unformatted JSON strings to Sir when presenting market analysis, trading decisions, or scheduled reports.
- Always parse and format JSON trading decisions into an executive, beautifully formatted Markdown summary with emojis (e.g. ⏸️ WAIT / 🚀 BUY / 🔻 SELL), confidence %, equity health, key indicators, and clear reasoning.

If Sir asks what you can do, or requests info about a specific skill, describe its capabilities in a detailed, polite, and signature manner using these user-friendly names. Never use technical function names like "get_weather" in dialogue unless Sir explicitly asks for them.
"""

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
        return db.get_chat_history(session_id, limit=self.max_history_len)

    def clear_history(self, session_id: str):
        from backend import database as db
        db.clear_chat_history(session_id)

    async def respond(self, user_message: str, session_id: str = "default", override_agent_id: Optional[str] = None) -> str:
        """Sends chat request to OpenRouter LLM model with memory context and system prompt."""
        if not self.api_key:
            return "Error: OPENROUTER_API_KEY is not set in the .env configuration, Sir."

        # IMMEDIATE persistence of user message to prevent session loss on UI refresh
        from backend import database as db
        current_user_msg_id = db.save_message(session_id, "user", user_message)
        self.last_saved_ids[session_id] = {"user": current_user_msg_id, "assistant": None}

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
                    response_text = "Sir, the orchestration process has completed, but the response was empty."
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
                from datetime import datetime
                from zoneinfo import ZoneInfo
                log_entry = {
                    "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d %H:%M:%S"),
                    "session_id": session_id,
                    "model": self.model,
                    "latency_ms": latency_ms,
                    "success": not response_text.startswith("Apologies, Sir."),
                    "error": None if not response_text.startswith("Apologies, Sir.") else response_text,
                    "prompt_tokens_estimate": prompt_est,
                    "user_message": user_message,
                    "assistant_response": response_text,
                    "traces": orch_result.get("traces", []),
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
            message=f"👤 Received request from Sir: '{user_message}'"
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
                    response_text = "Sir, the orchestration process has completed, but the response was empty."
                traces = orch_result["traces"]
                error_msg = None
                self.last_run_metadata[session_id] = {
                    "is_complex": True,
                    "complexity": complexity,
                    "steps": orch_result.get("steps", [])
                }
            except Exception as e:
                response_text = f"Apologies, Sir. A failure occurred while coordinating my subagents: {str(e)}"
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
        from datetime import datetime
        from zoneinfo import ZoneInfo
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

        from backend.tools import TOOLS_SCHEMA, execute_tool

        total_prompt_tokens = 0
        total_completion_tokens = 0

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                while True:
                    payload = {
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.7,
                        "max_tokens": 4096,
                    }
                    if "deepseek-r1" not in self.model.lower():
                        payload["tools"] = TOOLS_SCHEMA
                    
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
                        response_text = f"Apologies, Sir. Difficulties occurred while communicating with the server {provider_name}: {response.status_code}."
                        break
                        
                    raw_data = response.json()
                    data = translate_to_openai_response(raw_data) if is_openmodel else raw_data

                    if not isinstance(data, dict) or "error" in data or not data.get("choices"):
                        err_detail = data.get("error", {}) if isinstance(data, dict) else str(data)
                        if isinstance(err_detail, dict):
                            err_text = err_detail.get("message") or str(err_detail)
                        else:
                            err_text = str(err_detail) if err_detail else "Empty choices returned from model."
                        error_msg = f"LLM API Error: {err_text}"
                        provider_name = "OpenModel" if is_openmodel else "OpenRouter"
                        logger.error(f"LLM API error response from {provider_name}: {raw_data}")
                        response_text = f"Apologies, Sir. Difficulties occurred while communicating with the server {provider_name}: {err_text}."
                        break

                    usage = data.get("usage", {})
                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                    total_completion_tokens += usage.get("completion_tokens", 0)
                    
                    choice_0 = data["choices"][0] if (isinstance(data.get("choices"), list) and len(data["choices"]) > 0) else {}
                    choice_msg = choice_0.get("message") if isinstance(choice_0, dict) else {}
                    if not isinstance(choice_msg, dict):
                        choice_msg = {}
                    
                    tool_calls = choice_msg.get("tool_calls")
                    if not tool_calls:
                        content_str = choice_msg.get("content") or ""
                        tool_calls = self._extract_json_tool_calls(content_str)

                    if not tool_calls:
                        # Final text response reached
                        response_text = choice_msg.get("content") or ""
                        
                        # Fallback: if LLM returned empty text content,
                        # request a verbal confirmation or provide fallback so user is never left with an empty bubble
                        if not response_text.strip():
                            logger.info("Jarvis returned empty response content. Requesting final verbal confirmation...")
                            
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
                                    f"An error occurred during tool execution: {error_text}. "
                                    f"Please inform Sir concisely in your signature Jarvis voice explaining the issue."
                                )
                            else:
                                fallback_prompt = "Please confirm to Sir with a concise report in your signature Jarvis voice that actions completed successfully."
                                
                            messages.append({
                                "role": "user",
                                "content": fallback_prompt
                            })
                            try:
                                payload_fallback = {
                                    "model": self.model,
                                    "messages": messages,
                                    "temperature": 0.5
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
                                    if isinstance(fallback_data, dict) and fallback_data.get("choices") and len(fallback_data["choices"]) > 0:
                                        fb_choice_0 = fallback_data["choices"][0]
                                        fb_choice = fb_choice_0.get("message") if isinstance(fb_choice_0, dict) else {}
                                        fb_content = fb_choice.get("content") if isinstance(fb_choice, dict) else ""
                                        response_text = fb_content if isinstance(fb_content, str) else ""
                                        total_completion_tokens += fallback_data.get("usage", {}).get("completion_tokens", 0)
                                    else:
                                        response_text = "Sir, the operation requested has been completed successfully."
                                else:
                                    response_text = "Sir, the operation requested has been completed successfully."
                            except Exception as fallback_err:
                                logger.error(f"Error during verbal confirmation fallback: {fallback_err}")
                                response_text = "Sir, the operation requested has been completed successfully."

                        if not response_text or not response_text.strip():
                            response_text = "Sir, the operation requested has been completed successfully."
                        
                        # Calculate cost
                        cost_usd = calculate_cost(self.model, total_prompt_tokens, total_completion_tokens)
                        self.last_costs[session_id] = cost_usd
                        
                        from backend.activity_logger import log_activity
                        log_activity(
                            activity_type="active",
                            source="Agent",
                            message=f"💬 Response to Sir formulated. Cost: ${cost_usd:.6f}",
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
                    
                    billing = get_billing_adapter()
                    user_id = "default_user"  # Single-tenant fallback for now
                    
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("function", {}).get("name")
                        tool_args_str = tool_call.get("function", {}).get("arguments", "{}")
                        
                        # --- BILLING ENFORCEMENT ---
                        skill_id = LifecycleManager.get_skill_for_tool(tool_name)
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
                        result_str = execute_tool(tool_name, tool_args, chat_id=session_id)
                        
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
            response_text = "Apologies, Sir. A failure occurred while processing your request."

        # Add call record to global decision logs
        from datetime import datetime
        from zoneinfo import ZoneInfo
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

        try:
            from backend.bcm.autonomous_trader import format_any_bcm_response
            response_text = format_any_bcm_response(response_text)
        except Exception:
            pass

        return response_text

    # Known tool fingerprints: set of required keys → tool name
    _TOOL_FINGERPRINTS: List[Dict] = [
        {"required": {"symbol", "side", "qty"}, "optional": {"category", "order_type", "market_unit", "price"}, "name": "bybit_place_order"},
        {"required": {"symbol", "side", "qty", "category"}, "optional": {"order_type", "market_unit"}, "name": "bybit_place_order"},
        {"required": {"base_coin"}, "optional": {"exp_date"}, "name": "bybit_get_options_chain"},
        {"required": {"account_type"}, "optional": {}, "name": "bybit_get_balance"},
    ]

    def _extract_json_tool_calls(self, text: str) -> Optional[List[Dict[str, Any]]]:
        """Fallback extractor for models that output raw JSON function calls in text content.
        
        Handles two cases:
        1. Structured: {"name": "tool_name", "parameters": {...}}
        2. Raw args: {"symbol":"SOLUSDT","side":"Buy",...} — matched via fingerprint
        """
        if not text:
            return None
        import json

        candidates = []
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
                        candidates.append(text[start:i+1])
                        start = -1

        extracted = []
        for raw in candidates:
            try:
                parsed = json.loads(raw)
                fn_name = None
                fn_args = {}
                if isinstance(parsed, dict):
                    if "function" in parsed and isinstance(parsed["function"], dict):
                        fn_name = parsed["function"].get("name")
                        fn_args = parsed["function"].get("parameters") or parsed["function"].get("arguments") or {}
                    elif "name" in parsed and ("parameters" in parsed or "arguments" in parsed):
                        fn_name = parsed.get("name")
                        fn_args = parsed.get("parameters") or parsed.get("arguments") or {}
                    elif "name" in parsed and isinstance(parsed.get("name"), str) and any(
                        parsed["name"].startswith(pfx) for pfx in ("bybit_", "bcm_", "exchange_")
                    ):
                        # {"name": "bybit_place_order", "symbol": "SOLUSDT", ...}
                        fn_name = parsed["name"]
                        fn_args = {k: v for k, v in parsed.items() if k != "name"}
                    else:
                        # Try fingerprint matching for raw argument blobs (no name/function wrapper)
                        parsed_keys = set(parsed.keys())
                        for fp in self._TOOL_FINGERPRINTS:
                            if fp["required"].issubset(parsed_keys):
                                fn_name = fp["name"]
                                fn_args = parsed
                                logger.info(f"Fingerprint matched raw JSON args to tool '{fn_name}': {list(parsed_keys)}")
                                break

                if fn_name:
                    extracted.append({
                        "id": f"call_fallback_{len(extracted)}",
                        "type": "function",
                        "function": {
                            "name": fn_name,
                            "arguments": json.dumps(fn_args) if isinstance(fn_args, dict) else str(fn_args)
                        }
                    })
            except Exception:
                pass

        return extracted if extracted else None

    async def _respond_as_subagent(self, user_message: str, subagent: Dict[str, Any], parent_skills: Optional[str] = None, current_user_msg_id: Optional[int] = None, chat_id: Optional[str] = None, parent_message_id: Optional[int] = None) -> str:
        """Runs response generation loop specifically tailored for a dynamic subagent session."""
        session_id = chat_id or subagent["id"]
        subagent_name = subagent["name"]
        system_prompt = subagent["system_prompt"]
        subagent_model = subagent["model"]
        tool_calls_log: List[Dict[str, Any]] = []

        from backend.activity_logger import log_activity
        log_activity(
            activity_type="active",
            source=subagent_name,
            message=f"👤 Received request for subagent '{subagent_name}': '{user_message}'"
        )

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
        
        # Build payload with subagent prompt + chat history + current message
        from datetime import datetime
        from zoneinfo import ZoneInfo
        _now_il = datetime.now(ZoneInfo("Asia/Jerusalem"))
        _day_names_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        current_time_str = _now_il.strftime("%Y-%m-%d %H:%M:%S")
        day_of_week = _day_names_en[_now_il.weekday()]
        system_info = (
            f"\n\n[System Information]:\n"
            f"Current date and time: {current_time_str} (Asia/Jerusalem, GMT+3)\n"
            f"Day of the week: {day_of_week}\n"
            f"IMPORTANT RULE: Your built-in knowledge is limited to the past. To get ANY up-to-date information about events, sports matches (e.g., today\'s games, betting odds, analytics), news, quotes, or weather, you MUST use the internet search via the web_search tool. Never fabricate events or rely on your outdated data!\n"
            f"IT IS STRICTLY FORBIDDEN to search, use, mention, quote, or retell ready-made forecasts, other people\'s articles, advice, or opinions about value bets (e.g., \'ready forecasts\', \'value bets according to LiveSport\', \'expert opinions\') in responses to Sir. You must search exclusively for raw numerical data: opponent pairs, exact match start times, and bookmaker odds. Any conclusions and mathematical calculations of value (EV = Probability * Odds - 1) must be done strictly independently, and you must provide only your own results without referring to external opinions!\n"
            f"You are not allowed to be lazy in calculations: if exact numerical odds are not found in the search, you must perform mathematical forecasting (e.g., calculate probabilities of win/draw/loss using Poisson distribution based on average scoring or team goal statistics) and calculate expected value (EV = P * Odds - 1) based on calculated probabilities and approximate odds, instead of giving a dry refusal or quoting external forecasts."
        )
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
        from backend.tools import TOOLS_SCHEMA, execute_tool
        safe_tool_names = {
            "get_system_stats",
            "get_weather",
            "get_current_time_israel",
            "web_search",
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
            "web_search": ["web_search", "get_current_time_israel", "get_weather", "get_rss_digest"],
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
                if skill in ("bcm", "bcm-trader", "bybit", "bybit_trader"):
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
                if skill in ("bcm", "bcm-trader", "bybit", "bybit_trader"):
                    try:
                        from backend.bcm.tools import BCM_TOOLS
                        parent_allowed.update([t["name"] for t in BCM_TOOLS])
                    except ImportError:
                        pass
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

        total_prompt_tokens = 0
        total_completion_tokens = 0

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                while True:
                    payload = {
                        "model": subagent_model,
                        "messages": messages,
                        "temperature": subagent.get("temperature", 0.7),
                        "max_tokens": 4096,
                    }
                    if "deepseek-r1" not in subagent_model.lower():
                        payload["tools"] = subagent_tools
                        payload["tool_choice"] = "auto"
                    
                    is_openmodel = "openmodel.ai" in self.api_base
                    url = f"{self.api_base}/messages" if is_openmodel else f"{self.api_base}/chat/completions"
                    actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
                    
                    response = None
                    for attempt in range(3):
                        response = await client.post(
                            url,
                            json=actual_payload,
                            headers=headers
                        )
                        if response.status_code == 200:
                            break
                        
                        logger.warning(f"Subagent '{subagent_name}' ({subagent_model}) API returned {response.status_code} (attempt {attempt+1}/3): {response.text[:200]}")
                        
                        # If context length exceeded or provider error, trim prompt and retry
                        if "context_length_exceeded" in response.text or "input too long" in response.text.lower() or "max input length" in response.text.lower():
                            logger.warning("Trimming subagent message context due to context_length_exceeded...")
                            # Keep system prompt and latest user prompt only
                            payload["messages"] = [payload["messages"][0], payload["messages"][-1]]
                            actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload
                        
                        import asyncio
                        await asyncio.sleep(1.0)
                    
                    if response is None or response.status_code != 200:
                        error_msg = f"HTTP Error {response.status_code if response else 'No Response'}: {response.text if response else ''}"
                        logger.error(f"Subagent '{subagent_name}' ({subagent_model}) API error: {error_msg}")
                        provider_name = "OpenModel" if is_openmodel else "OpenRouter"
                        response_text = f"Apologies, Sir. Difficulties occurred while communicating with the server {provider_name}: {response.status_code if response else 'Timeout'}."
                        break
                        
                    raw_data = response.json()
                    data = translate_to_openai_response(raw_data) if is_openmodel else raw_data

                    if not isinstance(data, dict) or "error" in data or not data.get("choices"):
                        err_detail = data.get("error", {}) if isinstance(data, dict) else str(data)
                        if isinstance(err_detail, dict):
                            err_text = err_detail.get("message") or str(err_detail)
                        else:
                            err_text = str(err_detail) if err_detail else "Empty choices returned from model."
                        error_msg = f"LLM API Error: {err_text}"
                        provider_name = "OpenModel" if is_openmodel else "OpenRouter"
                        logger.error(f"Subagent '{subagent_name}' ({subagent_model}) API error response: {raw_data}")
                        response_text = f"Apologies, Sir. Difficulties occurred while communicating with the server {provider_name}: {err_text}."
                        break

                    usage = data.get("usage", {})
                    total_prompt_tokens += usage.get("prompt_tokens", 0)
                    total_completion_tokens += usage.get("completion_tokens", 0)
                    
                    choice_0 = data["choices"][0] if (isinstance(data.get("choices"), list) and len(data["choices"]) > 0) else {}
                    choice_msg = choice_0.get("message") if isinstance(choice_0, dict) else {}
                    if not isinstance(choice_msg, dict):
                        choice_msg = {}
                    
                    tool_calls = choice_msg.get("tool_calls")
                    if not tool_calls:
                        content_str = choice_msg.get("content") or ""
                        tool_calls = self._extract_json_tool_calls(content_str)

                    if not tool_calls:
                        response_text = choice_msg.get("content") or ""
                        
                        # Programmatic anti-hallucination guardrail for trading agents:
                        # If no successful bybit_place_order was executed in this turn, strictly forbid claims of trade execution.
                        if not order_placed_successfully and any(w in response_text.lower() for w in ["successfully executed", "- executed", "trade opened", "placed via bybit_place_order"]):
                            logger.warning(f"Subagent '{subagent_name}' claimed trade execution without successful bybit_place_order. Overriding response.")
                            response_text = "⚠️ Warning: Order placement call (`bybit_place_order`) was not executed in this turn. Trades on Bybit were NOT opened."

                        # Fallback for empty text content after tools
                        if not response_text.strip() and tool_executed:
                            response_text = "Actions successfully executed, Sir."
                        
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
                            message=f"🛠️ Execution (subagent): '{tool_name}' с аргументами {tool_args_str}"
                        )
                        result_str = execute_tool(tool_name, tool_args, chat_id=session_id)
                        if tool_name == "bybit_place_order" and ("success" in result_str.lower() or "orderid" in result_str.lower()):
                            order_placed_successfully = True
                        
                        # Accumulate tool call for agent thread viewer
                        from backend.marketplace.lifecycle import LifecycleManager as _LCM
                        _skill_id = _LCM.get_skill_for_tool(tool_name)
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
        except Exception as e:
            latency_ms = int((time.time() - start_time) * 1000)
            error_msg = str(e)
            logger.exception("Error during OpenRouter subagent chat completion call")
            response_text = "Apologies, Sir. A failure occurred while processing the subagent\'s request."

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
            "agent_id": subagent["id"],
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


        try:
            from backend.bcm.autonomous_trader import format_any_bcm_response
            response_text = format_any_bcm_response(response_text)
        except Exception:
            pass

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
    
    if tool_calls:
        openai_response["choices"][0]["message"]["tool_calls"] = tool_calls
        
    return openai_response

# Singleton instance
agent_instance = JarvisAgent()
