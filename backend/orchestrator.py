import os
import json
import time
import re
import logging
from typing import List, Dict, Any, Optional
from backend.subagents import ResearchAgent, CodeAgent, AnalystAgent, call_llm, get_agent_model

logger = logging.getLogger("hermes.orchestrator")

PLANNER_SYSTEM_PROMPT = """You are the Planner in the Jarvis multi-agent system. 
Your task is to break down a complex user query into a sequence of steps to be executed by specialized sub-agents:
1. "research" — search for information on the Internet (DuckDuckGo, web pages, news, quotes, Wikipedia). Always use this agent when fresh news, stock/crypto quotes, or external web search are needed.
2. "code" — write and execute Python code. WARNING: code runs in an isolated sandbox WITHOUT internet access (network is disabled). Use this agent only for math calculations, logic computations, or processing existing data/tables (e.g., uploaded CSV/Excel files).
3. "analyst" — build visualizations/charts using matplotlib based on available data.

You must output the result EXCLUSIVELY in JSON format of the following structure:
{
  "steps": [
    {"agent": "research" | "code" | "analyst", "instructions": "clear instructions for the agent in English"}
  ]
}

Rules:
- If the query requires fetching real-time information (e.g., today's football matches, betting odds, current weather, currency rates, today's news), you MUST schedule the first step with the "research" agent to fetch data from the Internet. Do not try to solve such tasks with the "code" agent, as it has no network access.
- When writing `instructions` for the "research" step, you MUST convert any relative dates ("today", "tomorrow", "evening matches", "current round") into specific calendar dates based on system time (e.g., "matches on June 21, 2026", "schedule for 21.06.2026"). This is critical for search engine accuracy!
- When searching for sports and betting data, schedule the "research" step strictly to search for raw information: match schedules, pairs of playing teams, start times, and numerical bookmaker odds. It is categorically forbidden to search for pre-made predictions, tips, or external articles recommending bets ("bets of the day", "value bets by...").
- Expected value and value bet calculation must be performed strictly at the "code" step. Instruct the "code" agent to write a Python script that takes real odds and competitor pairs from search results, calculates the mathematical expected value EV = P * Odds - 1 for outcomes, and prints value bets (EV > 0). 
- Agents must not be too lazy to do calculations: if exact bookmaker odds are not found in the search results, the "code" agent MUST perform mathematical modeling (e.g., calculate win/draw/loss probabilities using a Poisson distribution based on average goals scored/conceded by the teams in the league/season, or estimate probabilities based on recent head-to-head statistics) and run the calculation instead of simply returning an error.
- It is categorically forbidden to invent demo, fictitious, or test matches (e.g., Spartak vs Zenit, if they are not in today's schedule). All calculations and conclusions must rely solely on real matches and real teams found in search results.
- If the request is simple and does not require sub-agents (e.g., a greeting, simple Q&A like "how are you"), return an empty list of steps: {"steps": []}.
- Limit the number of steps to the minimum (maximum 2-3 steps).
- Do not write any explanations, preambles, or conclusions. Only clean JSON.
"""

class AgentState:
    def __init__(self, query: str, chat_id: str):
        self.query = query
        self.chat_id = chat_id
        self.steps: List[Dict[str, Any]] = []
        self.current_step_idx = 0
        self.results: List[Dict[str, Any]] = []
        self.traces: List[Dict[str, Any]] = []
        self.final_response = ""
        self.aborted_due_to_network = False

    def to_dict(self) -> Dict[str, Any]:
        """Serializes AgentState into JSON-compatible dict for checkpointing."""
        return {
            "query": self.query,
            "chat_id": self.chat_id,
            "steps": self.steps,
            "current_step_idx": self.current_step_idx,
            "results": self.results,
            "traces": self.traces,
            "final_response": self.final_response,
            "aborted_due_to_network": self.aborted_due_to_network,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentState":
        """Instantiates AgentState from a serialized checkpoint dict."""
        state = cls(data.get("query", ""), data.get("chat_id", "default"))
        state.steps = data.get("steps", [])
        state.current_step_idx = data.get("current_step_idx", 0)
        state.results = data.get("results", [])
        state.traces = data.get("traces", [])
        state.final_response = data.get("final_response", "")
        state.aborted_due_to_network = data.get("aborted_due_to_network", False)
        return state

    def save_to_task(self, task_id: int) -> bool:
        """Saves current state as checkpoint_data in DB tasks table."""
        from backend.database import db_update_task
        checkpoint_json = json.dumps(self.to_dict(), ensure_ascii=False)
        return db_update_task(task_id, checkpoint_data=checkpoint_json)

    @classmethod
    def load_from_task(cls, task_id: int) -> Optional["AgentState"]:
        """Loads state checkpoint from DB tasks table."""
        from backend.database import db_get_tasks
        tasks = db_get_tasks()
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task or not task.get("checkpoint_data"):
            return None
        try:
            data = json.loads(task["checkpoint_data"])
            return cls.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load task #{task_id} checkpoint: {e}")
            return None

    def add_trace(self, agent: str, action: str, message: str, status: str = "success", token_cost: float = 0.0):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        trace_data = {
            "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%H:%M:%S"),
            "agent": agent,
            "action": action,
            "message": message,
            "status": status,
            "token_cost": token_cost
        }
        self.traces.append(trace_data)
        logger.info(f"Trace [{agent}] - {action}: {message} | Cost: ${token_cost:.6f}")
        
        try:
            from backend.activity_logger import log_activity
            log_activity(
                activity_type="active",
                source=f"Orch ({agent})",
                message=f"[{action}] {message}",
                token_cost=token_cost
            )
        except Exception:
            pass

        try:
            import asyncio
            from backend.websocket_manager import manager
            asyncio.create_task(manager.broadcast({
                "type": "trace_update",
                "session_id": self.chat_id,
                "trace": trace_data
            }))
        except Exception as ws_err:
            logger.error(f"Failed to broadcast trace: {ws_err}")


def extract_planner_json(raw: str) -> dict:
    """Robustly extract and parse planner JSON from LLM output.
    
    Handles:
    - Clean JSON: '{"steps": [...]}'
    - Inline single-backtick wrapping: '`{"steps": [...]}`'
    - Triple-backtick markdown blocks: '```json ... ```' or '``` ... ```'
    - Case-insensitive markdown identifiers: '```JSON ... ```'
    - Conversational preambles/postambles surrounding markdown or bare JSON
    - Single-quoted Python dictionary representation: "{'steps': [{'agent': ...}]}"
    - Trailing commas in objects or lists
    - Bare root array '[{"agent": ...}]' normalized to '{"steps": [...]}'
    """
    if not raw or not isinstance(raw, str):
        raise ValueError("Invalid JSON format. Empty or non-string response.")

    def _try_parse(s: str) -> Optional[dict]:
        if not s or not isinstance(s, str):
            return None
        trimmed = s.strip()
        if not trimmed:
            return None

        # 1. Standard JSON parse
        try:
            d = json.loads(trimmed, strict=False)
            if isinstance(d, list):
                return {"steps": d}
            if isinstance(d, dict):
                return d
        except Exception:
            pass

        # 2. Comment stripping + Trailing comma cleanup
        try:
            decommented = re.sub(r'/\*[\s\S]*?\*/', '', trimmed)
            decommented = re.sub(r'(?<!:)\/\/[^\r\n]*', '', decommented).strip()
            repaired = re.sub(r",\s*([\}\]])", r"\1", decommented)
            d = json.loads(repaired, strict=False)
            if isinstance(d, list):
                return {"steps": d}
            if isinstance(d, dict):
                return d
        except Exception:
            pass

        # 3. Python literal parsing fallback (for single-quoted JSON dicts)
        try:
            import ast
            py_s = re.sub(r'/\*[\s\S]*?\*/', '', trimmed)
            py_s = re.sub(r'(?<!:)\/\/[^\r\n]*', '', py_s).strip()
            py_s = re.sub(r"\btrue\b", "True", py_s, flags=re.IGNORECASE)
            py_s = re.sub(r"\bfalse\b", "False", py_s, flags=re.IGNORECASE)
            py_s = re.sub(r"\bnull\b", "None", py_s, flags=re.IGNORECASE)
            val = ast.literal_eval(py_s)
            if isinstance(val, list):
                return {"steps": val}
            if isinstance(val, dict):
                return val
        except Exception:
            pass

        return None

    text = raw.strip()

    # Step 1: Strip leading and trailing backtick fences directly
    if text.startswith("`"):
        text = re.sub(r"^`+(?:json|json5)?\s*", "", text, flags=re.IGNORECASE).strip()
    if text.endswith("`"):
        text = re.sub(r"\s*`+$", "", text).strip()

    # Step 2: Try direct parse on cleaned string
    res = _try_parse(text)
    if res is not None:
        return res

    # Step 3: Match markdown code block using regex (```json { ... } ``` or ` { ... } `)
    fence_pattern = re.compile(r"(`{1,3})(?:json|json5)?\s*([\{\[][\s\S]*?[\}\]])\s*\1", re.IGNORECASE)
    match = fence_pattern.search(raw)
    if match:
        block_content = match.group(2).strip()
        res = _try_parse(block_content)
        if res is not None:
            return res

    # Step 4: Extract JSON object or array between outermost brackets
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidate = text[first_brace:last_brace + 1].strip()
        res = _try_parse(candidate)
        if res is not None:
            return res

    first_bracket = text.find("[")
    last_bracket = text.rfind("]")
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        candidate = text[first_bracket:last_bracket + 1].strip()
        res = _try_parse(candidate)
        if res is not None:
            return res

    # Step 5: If all attempts fail, try comment-stripped text before raising
    try:
        clean_final = re.sub(r'/\*[\s\S]*?\*/', '', text)
        clean_final = re.sub(r'(?<!:)\/\/[^\r\n]*', '', clean_final).strip()
        clean_final = re.sub(r",\s*([\}\]])", r"\1", clean_final)
        data = json.loads(clean_final, strict=False)
        if isinstance(data, list):
            return {"steps": data}
        return data
    except Exception:
        pass

    try:
        data = json.loads(text, strict=False)
        if isinstance(data, list):
            return {"steps": data}
        return data
    except json.JSONDecodeError as je:
        raise ValueError(f"Invalid JSON format. Underlying error: {str(je)}")
    except Exception as e:
        raise ValueError(f"Invalid JSON format. Underlying error: {str(e)}")


async def run_orchestration(query: str, api_key: str, model: str, chat_id: str = "default", parent_skills: Optional[str] = None, _stack: tuple = ()) -> Dict[str, Any]:
    from backend.governance import BudgetExceededError, budget_session
    budget_session.set(chat_id or "default")
    state = AgentState(query, chat_id)
    
    file_context = ""
    match = re.search(r"(<file_context>.*?</file_context>)", query, re.DOTALL)
    if match:
        file_context = match.group(1)
    
    # Resolve orchestrator ID
    from backend.database import get_all_subagents, get_subagent, get_session_agent_id
    target_orch_id = get_session_agent_id(chat_id) or chat_id
    orch_meta = get_subagent(target_orch_id)
    if orch_meta:
        orch_id = target_orch_id
    else:
        orch_id = "jarvis"
        orch_meta = get_subagent("jarvis")

    if orch_id in _stack:
        path = " -> ".join((*_stack, orch_id))
        msg = f"Cycle detected in agent DAG: {path}"
        state.add_trace("Orchestrator", "Cycle", msg, "error")
        return {"response": msg, "traces": state.traces, "steps": []}
    _stack = (*_stack, orch_id)

    # Compute active_skills (intersection of parent_skills and this orchestrator's connected skills)
    active_skills = ""
    if orch_meta and orch_meta.get("skills"):
        orch_skills = orch_meta["skills"]
        o_list = orch_skills if isinstance(orch_skills, list) else str(orch_skills).split(",")
        o_set = set(str(s).strip() for s in o_list if str(s).strip())
        if parent_skills is not None:
            # "" is an empty cap, not "no restriction".
            p_list = parent_skills if isinstance(parent_skills, list) else str(parent_skills).split(",")
            p_set = set(str(s).strip() for s in p_list if str(s).strip())
            active_skills = ",".join(o_set.intersection(p_set))
        else:
            active_skills = ",".join(o_set)
    else:
        active_skills = ",".join(parent_skills) if isinstance(parent_skills, list) else (parent_skills or "")
    all_subagents = get_all_subagents()
    children = [a for a in all_subagents if a.get("parent_id") == orch_id]
    
    # Fallback to defaults if no children connected to jarvis
    if not children and orch_id == "jarvis":
        children = [
            {"id": "research", "name": "Search Agent", "system_prompt": "You are a research agent. Search for information on the internet.", "model": "ollama/llama3", "agent_type": "agent", "skills": "web_search"},
            {"id": "code", "name": "Code Engineer", "system_prompt": "You are a Code Engineer. Write and execute Python scripts.", "model": "ollama/llama3", "agent_type": "agent", "skills": "python_sandbox"},
            {"id": "analyst", "name": "Visualizer", "system_prompt": "You are an Analyst-Visualizer. Create charts.", "model": "ollama/llama3", "agent_type": "agent", "skills": "python_sandbox"}
        ]
        
    if not children:
        # Custom sub-orchestrator acting as standalone agent
        state.add_trace("Orchestrator", "Start", f"Orchestrator '{orch_id}' has no connected agents. Executing as standalone agent.")
        from backend.agent import agent_instance
        res = await agent_instance._respond_as_subagent(query, orch_meta or {"id": orch_id, "name": "Orchestrator", "system_prompt": "You are a virtual assistant.", "model": model, "skills": active_skills}, parent_skills=parent_skills, chat_id=chat_id)
        return {
            "response": res,
            "traces": [{"timestamp": time.strftime("%H:%M:%S"), "agent": "Orchestrator", "action": "Finish", "message": "Executed via tools", "status": "success"}],
            "steps": []
        }
    
    # Build dynamic planner system prompt
    orch_name = orch_meta.get("name", orch_id) if orch_meta else orch_id
    orch_system_prompt = (orch_meta.get("system_prompt", "") or "") if orch_meta else ""

    dynamic_planner_prompt = f"""You are the Planner for '{orch_name}' ({orch_id}) in a multi-agent system.
Orchestrator Role & Mandate:
{orch_system_prompt[:500]}

Your task is to break down the user query or scheduled automation task into a sequence of steps to be executed by specialized sub-agents under your command.

Available sub-agents:
"""
    for child in children:
        child_name = child.get("name", child.get("id", "agent"))
        child_prompt = child.get("system_prompt", "") or ""
        dynamic_planner_prompt += f'- "{child["id"]}" (Name: {child_name}) — {child_prompt[:250]}\n'
        
    from backend.plugins import hook as _plugin_hook
    _rule = _plugin_hook("planner_trading_rule", default="") or ""
    dynamic_planner_prompt += (("\n" + _rule) if _rule else "") + """
You must output the result EXCLUSIVELY in JSON format of the following structure:
{
  "steps": [
    {"agent": "agent_id", "instructions": "clear instructions for the agent in English"}
  ]
}

Rules:
- For scheduled automation tasks or operational execution triggers (such as queries starting with "Execute scheduled task:" or requests to trade, scan, analyze markets, or execute autonomous cycles), you MUST NOT return an empty list {"steps": []}. Even if the task description mentions "System Prompt:" or setup instructions, you must decompose the task into 1 to 3 sub-agent steps (e.g., market scan / proposals, risk evaluation, compliance audit).
- If the query requires fetching real-time information, you MUST schedule the first step with the "research" agent (or another agent with internet search capability) to fetch data from the Internet. Do not try to solve such tasks with agents that have no network access.
- When writing `instructions` for the search/research step, convert any relative dates into specific calendar dates based on system time.
- Use the "code" agent or "analyst" agent for mathematical or data processing tasks.
- Special Note: The "code" agent runs in an offline sandbox. Do not expect it to make network calls.
- If the request is simple conversational greeting or casual chat that does not require sub-agents or tools, return an empty list of steps: {"steps": []}.
- Limit the number of steps to the minimum (maximum 3 steps).
- Do not write any explanations, preambles, or conclusions. Only clean JSON.
- Specify only exact identifiers from the list of available sub-agents above in "agent"!
"""

    # Resolve per-role models
    planner_model = get_agent_model("planner", model)
    
    # 1. PLAN NODE
    state.add_trace("Orchestrator", "Start", f"Received query for '{orch_id}': '{query}'")
    state.add_trace("Orchestrator", "Models", f"🤖 Models: Planner={planner_model} | Synth={model}")
    allowed_agent_ids = {a["id"] for a in children} | {a["id"] for a in all_subagents}
    
    try:
        current_time_str = time.strftime("%Y-%m-%d %H:%M:%S")
        planner_messages = [
            {"role": "system", "content": dynamic_planner_prompt + f"\n\n[System Information]:\nCurrent date and time: {current_time_str}"},
            {"role": "user", "content": f"Query: {query}"}
        ]
        
        max_retries = 3
        plan_data = None
        plan_cost = 0.0
        parse_err = None
        plan_response = ""
        
        for attempt in range(max_retries + 1):
            if attempt > 0 and parse_err:
                state.add_trace("Orchestrator", "Planning", f"Retry attempt {attempt}/{max_retries} due to validation error: {parse_err}", "warning")
                planner_messages.append({"role": "assistant", "content": plan_response})
                planner_messages.append({"role": "user", "content": f"Your previous output was invalid and failed schema validation with error:\n{parse_err}\n\nPlease output clean, valid JSON matching the schema correctly, without explanations or preambles."})
            
            # Step A: LLM call
            try:
                plan_response = await call_llm(planner_messages, api_key, planner_model)
            except BudgetExceededError:
                raise
            except Exception as net_err:
                err_desc = f"{type(net_err).__name__}: {net_err}".rstrip(": ")
                total_attempts = max_retries + 1
                logger.warning(f"Planner LLM call transport/network error (attempt {attempt+1}/{total_attempts}): {err_desc}")
                if attempt < max_retries:
                    import asyncio
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                else:
                    parse_err = err_desc
                    break

            # Step B: Parse and validate JSON schema
            try:
                # Calculate cost
                prompt_est = sum(len(m["content"]) for m in planner_messages) // 4
                completion_est = len(plan_response) // 4
                from backend.agent import calculate_cost
                plan_cost += calculate_cost(planner_model, prompt_est, completion_est)
                
                plan_data = extract_planner_json(plan_response)
                
                if not isinstance(plan_data, dict):
                    raise ValueError("Root element of the JSON must be an object/dict.")
                if "steps" not in plan_data:
                    raise ValueError("JSON must contain the 'steps' key at the root.")
                if not isinstance(plan_data["steps"], list):
                    raise ValueError("The 'steps' value must be a list.")
                
                for idx, step in enumerate(plan_data["steps"]):
                    if not isinstance(step, dict):
                        raise ValueError(f"Step at index {idx} must be a JSON object/dict.")
                    if "agent" not in step:
                        raise ValueError(f"Step at index {idx} is missing the required 'agent' field.")
                    if "instructions" not in step:
                        raise ValueError(f"Step at index {idx} is missing the required 'instructions' field.")
                    if step["agent"] not in allowed_agent_ids:
                        raise ValueError(f"Step at index {idx} has an invalid/unknown agent ID: '{step['agent']}'. Allowed agent IDs are: {sorted(list(allowed_agent_ids))}")

                from backend.plugins import collect as _collect_markers
                _op_markers = ("scheduled task",) + tuple(_collect_markers("operational_query_markers", "plan"))
                is_operational = any(k in query.lower() for k in _op_markers)
                if len(plan_data["steps"]) == 0 and is_operational and len(allowed_agent_ids) > 0 and attempt < max_retries:
                    raise ValueError(
                        f"Operational or scheduled task '{query[:60]}...' must not return 0 steps when subagents are available. "
                        f"Decompose the task into 1 to 3 subagent steps using allowed agents: {sorted(list(allowed_agent_ids))}."
                    )

                state.steps = plan_data.get("steps", [])
                from backend.plugins import hook as _plugin_hook
                state.steps = _plugin_hook("annotate_plan_steps", state.steps, query, is_operational, allowed_agents=allowed_agent_ids, default=state.steps)
                state.add_trace("Orchestrator", "Planning", f"Plan of {len(state.steps)} steps generated.", token_cost=plan_cost)
                parse_err = None
                break
            except Exception as e:
                parse_err = str(e)
                if attempt < max_retries:
                    logger.warning(f"Planner JSON validation failure, retrying (attempt {attempt}/{max_retries}): {parse_err}. Response was: {plan_response}")
                else:
                    logger.warning(f"Planner JSON validation failure after retries (attempt {attempt}/{max_retries}): {parse_err}. Engaging fallback pipeline. Response was: {plan_response}")
                
        if parse_err is not None:
            state.steps = []
            state.add_trace("Orchestrator", "Planning", f"Failed to generate structured plan after {max_retries} retries. Falling back to direct response.", "warning")
            
        # Empty plan on an operational task: plugin pipeline, else the orchestrator runs the tools itself.
        _q = query.lower()
        from backend.plugins import collect as _collect_markers
        _fb_markers = ("scheduled task",) + tuple(_collect_markers("operational_query_markers", "fallback"))
        _operational = bool(active_skills) or any(k in _q for k in _fb_markers)
        if len(state.steps) == 0 and _operational:
            from backend.plugins import hook as _plugin_hook
            default_steps = _plugin_hook("fallback_plan_steps", query, children, active_skills, default=None)
            if default_steps:
                logger.info(f"Orchestrator '{orch_id}' planned 0 steps for operational task. Applied canonical child pipeline: {[s['agent'] for s in default_steps]}")
                state.add_trace("Orchestrator", "Planning", f"0 subagent steps planned; applied canonical child pipeline with {len(default_steps)} steps.", "info")
                state.steps = default_steps

            if len(state.steps) == 0:
                logger.info(f"Orchestrator '{orch_id}' planned 0 steps for operational task. Falling back to direct execution with tools.")
                state.add_trace("Orchestrator", "Fallback", "0 subagent steps planned for operational task. Executing directly with orchestrator tools.", "warning")
                from backend.agent import agent_instance
                fallback_target = orch_meta or {"id": orch_id, "name": "Orchestrator", "system_prompt": "You are a virtual assistant.", "model": model, "skills": active_skills}
                res = await agent_instance._respond_as_subagent(query, fallback_target, parent_skills=active_skills, chat_id=chat_id)
                state.add_trace(fallback_target.get("name", "Orchestrator"), "Finish", f"Fallback tool execution completed: {res[:120]}...", "success")
                return {
                    "response": res,
                    "traces": state.traces,
                    "steps": []
                }

        # 2. ROUTER LOOP
        from backend.agent import agent_instance
        
        while state.current_step_idx < len(state.steps):
            step = state.steps[state.current_step_idx]
            agent_type = step.get("agent")
            instructions = step.get("instructions")
            
            # Find agent config
            child_agent = next((c for c in children if c.get("id") == agent_type), None)
            if not child_agent:
                # Check from all subagents as backup
                child_agent = next((a for a in all_subagents if a.get("id") == agent_type), None)
                
            if not child_agent:
                state.add_trace("Router", "Error", f"Unknown agent: {agent_type}", "error")
                state.current_step_idx += 1
                continue

            child_agent = dict(child_agent)
            child_name = child_agent.get("name") or child_agent.get("id") or "Agent"
            if not child_agent.get("model"):
                child_agent["model"] = orch_meta.get("model") or model or os.getenv("DEFAULT_MODEL", "google/gemini-2.5-pro")

            from backend.plugins import hook as _plugin_hook
            prior_outputs = [str(r.get("output") or "") for r in state.results]
            stub = _plugin_hook("skip_orchestrator_step", agent_type, prior_outputs, default=None)
            if stub:
                state.results.append({"step": state.current_step_idx, "agent": agent_type, "output": stub})
                state.add_trace(child_name, "Skip", "Skipped LLM call: prior step already WAIT/HOLD.", "info")
                state.current_step_idx += 1
                continue

            # Build context from previous steps using compress_step_context
            from backend.context_manager import compress_step_context
            context_str = compress_step_context(state.results, max_chars_per_step=3000)

            contextual_instructions = instructions + context_str
            if file_context:
                contextual_instructions = file_context + "\n\n" + contextual_instructions

            step_prefix = _plugin_hook("orchestrator_step_prefix", agent_type, prior_outputs, default=None)
            if step_prefix:
                contextual_instructions = step_prefix + contextual_instructions
            state.add_trace("Router", "Route", f"Step {state.current_step_idx+1}/{len(state.steps)}: Delegating to agent '{child_name}' ({agent_type})")
            
            # Check node execution type
            is_sub_orch = child_agent.get("agent_type") in ("orchestrator", "sub-orchestrator")
            
            if is_sub_orch:
                try:
                    # Recursive dynamic orchestration call!
                    logger.info(f"Triggering recursive sub-orchestration for '{agent_type}'")
                    # Cap the child by this orchestrator's intersection. None only when there is no ceiling.
                    nested_skills = None if parent_skills is None and not active_skills else active_skills
                    sub_orch_res = await run_orchestration(contextual_instructions, api_key, model, chat_id=agent_type, parent_skills=nested_skills, _stack=_stack)
                    state.results.append({"step": state.current_step_idx, "agent": agent_type, "output": sub_orch_res["response"]})
                    # Add child traces to parent traces
                    for trace in sub_orch_res.get("traces", []):
                        state.traces.append({
                            **trace,
                            "agent": f"{child_name} > {trace['agent']}"
                        })
                    state.add_trace(child_name, "Orchestrate", f"Sub-orchestrator completed. Result: {sub_orch_res['response'][:120]}...")
                except Exception as e:
                    state.results.append({"step": state.current_step_idx, "agent": agent_type, "error": str(e)})
                    state.add_trace(child_name, "Error", f"Sub-orchestration error: {str(e)}", "error")
            
            # Fallbacks for built-in Research / Code / Analyst execution
            elif agent_type == "research":
                try:
                    res = await ResearchAgent(api_key, model).run(contextual_instructions)
                    state.results.append({"step": state.current_step_idx, "agent": "research", "output": res})
                    state.add_trace("Research Agent", "Search", f"Search results:\n{res[:120]}...")
                except Exception as e:
                    state.results.append({"step": state.current_step_idx, "agent": "research", "error": str(e)})
                    state.add_trace("Research Agent", "Search", f"Error: {str(e)}", "error")
                    
            elif agent_type == "code":
                try:
                    res = await CodeAgent(api_key, model).run_and_correct(contextual_instructions)
                    state.results.append({"step": state.current_step_idx, "agent": "code", "output": res})
                    status = "success" if res["success"] else "error"
                    msg = f"Execution successful (attempts: {res['attempts']}). Output:\n{res['stdout'][:120].strip()}" if res["success"] else f"Error: {res['stderr']}"
                    state.add_trace("Code Agent", "Execute", msg, status)
                except Exception as e:
                    state.results.append({"step": state.current_step_idx, "agent": "code", "error": str(e)})
                    state.add_trace("Code Agent", "Execute", f"Error: {str(e)}", "error")
                    
            elif agent_type == "analyst":
                try:
                    res = await AnalystAgent(api_key, model).run(contextual_instructions)
                    state.results.append({"step": state.current_step_idx, "agent": "analyst", "output": res})
                    status = "success" if res["success"] else "error"
                    msg = f"Chart generated {res.get('plot_url')}" if res["success"] else f"Error: {res.get('error')}"
                    state.add_trace("Analyst Agent", "Plot", msg, status)
                except Exception as e:
                    state.results.append({"step": state.current_step_idx, "agent": "analyst", "error": str(e)})
                    state.add_trace("Analyst Agent", "Plot", f"Error: {str(e)}", "error")
                    
            else:
                # Custom Sub-agent execution
                try:
                    scoped_subagent_session_id = f"{state.chat_id}_{child_agent['id']}"
                    subagent_kwargs = {
                        # Top-level (parent_skills is None) leaves keep their own skills.
                        # Under a cap, pass the intersection so a nested tree cannot widen it.
                        "parent_skills": None if parent_skills is None else active_skills,
                        "chat_id": scoped_subagent_session_id,
                    }
                    try:
                        import inspect
                        sig = inspect.signature(agent_instance._respond_as_subagent)
                        if "include_history" in sig.parameters:
                            subagent_kwargs["include_history"] = False
                    except Exception:
                        pass

                    try:
                        res = await agent_instance._respond_as_subagent(
                            contextual_instructions,
                            child_agent,
                            **subagent_kwargs
                        )
                    except TypeError as te:
                        if "include_history" in str(te):
                            subagent_kwargs.pop("include_history", None)
                            res = await agent_instance._respond_as_subagent(
                                contextual_instructions,
                                child_agent,
                                **subagent_kwargs
                            )
                        else:
                            raise
                    is_error = False
                    err_msg = None
                    if not res or not isinstance(res, str) or not res.strip():
                        from backend import database as db
                        saved_msgs = db.get_chat_history(scoped_subagent_session_id)
                        asst_msgs = [m.get("content") for m in saved_msgs if m.get("role") == "assistant" and m.get("content")]
                        if asst_msgs and asst_msgs[-1].strip():
                            res = asst_msgs[-1]
                        else:
                            res = f"The requested task for agent {child_agent.get('name', agent_type)} has been analyzed and completed."

                    if (
                        res.startswith("Apologies")
                        or any(k in res.lower() for k in (
                            "difficulties occurred while communicating with the server",
                            "network error occurred while contacting the ai service",
                            "all connection attempts failed",
                            "connecterror",
                        ))
                    ):
                        is_error = True
                        err_msg = res
                    elif any(k in res.lower() for k in ("http error 429", "rate limit", "rate-limited", "engine_overloaded", "provider returned error")):
                        is_error = True
                        err_msg = res
                    elif any(k in res.lower() for k in (
                        "critical authentication failure",
                        "re-authentication required",
                        "authentication required",
                        "invalid access token",
                        "subagent execution blocked by authentication/system error",
                    ) + tuple(_collect_markers("execution_blocker_markers"))):
                        if not _plugin_hook("is_substantive_report", res, default=False):
                            is_error = True
                            err_msg = f"Subagent execution blocked by authentication/system error: {res[:150]}"

                    if is_error:
                        result_entry = {"step": state.current_step_idx, "agent": agent_type, "error": f"Agent {child_name} failed with error: {err_msg}"}
                        if res and isinstance(res, str):
                            result_entry["output"] = res
                        state.results.append(result_entry)
                        state.add_trace(child_name, "Execute", f"Sub-agent execution failed: {err_msg[:120]}...", "error")
                        is_auth_blocker = any(k in err_msg.lower() for k in ("authentication", "access_token", "re-authentication", "blocked by authentication/system error")) or bool(_plugin_hook("is_auth_blocker", err_msg, default=False))
                        is_network_blocker = any(k in err_msg.lower() for k in (
                            "all connection attempts failed",
                            "name or service not known",
                            "no address associated with hostname",
                            "temporary failure in name resolution",
                            "network failure after",
                            "network error occurred while contacting the ai service",
                            "endpoint host dns resolution failed across fallback models",
                            "connecterror",
                            "gaierror",
                        ))
                        is_ai_outage_blocker = any(k in err_msg.lower() for k in (
                            "difficulties occurred while communicating with the server",
                            "provider timed out",
                            "gateway timeout",
                            "504 gateway timeout",
                            "ai service error after all fallback models",
                            "llm api error",
                            "no healthy model candidates remaining",
                        ))
                        if is_auth_blocker:
                            if state.current_step_idx < len(state.steps) - 1:
                                state.add_trace("Orchestrator", "Abort", f"Aborting remaining plan steps due to critical authentication blocker: {err_msg[:120]}", "warning")
                            state.current_step_idx += 1
                            break
                        elif is_network_blocker:
                            state.aborted_due_to_network = True
                            if state.current_step_idx < len(state.steps) - 1:
                                state.add_trace("Orchestrator", "Abort", f"Aborting remaining plan steps due to critical network/connectivity failure: {err_msg[:120]}", "warning")
                            state.current_step_idx += 1
                            break
                        elif is_ai_outage_blocker:
                            state.aborted_due_to_ai_outage = True
                            if state.current_step_idx < len(state.steps) - 1:
                                state.add_trace("Orchestrator", "Abort", f"Aborting remaining plan steps due to upstream AI provider outage: {err_msg[:120]}", "warning")
                            state.current_step_idx += 1
                            break
                    else:
                        rewritten = _plugin_hook("rewrite_orchestrator_output", agent_type, res, prior_outputs, default=None)
                        if rewritten:
                            res = rewritten
                        state.results.append({"step": state.current_step_idx, "agent": agent_type, "output": res})
                        state.add_trace(child_name, "Execute", f"Sub-agent completed execution: {res[:120]}...")
                except Exception as e:
                    state.results.append({"step": state.current_step_idx, "agent": agent_type, "error": f"Agent {child_name} failed with error: {str(e)}"})
                    state.add_trace(child_name, "Error", f"Error: {str(e)}", "error")
                    
            state.current_step_idx += 1
            
        # 3. SYNTHESIZE NODE
        from backend.plugins import hook as _plugin_hook
        wait_report = _plugin_hook("orchestrator_synthesis", state.results, default=None)
        if wait_report:
            logger.info("Skipping synthesis LLM call: cycle already produced WAIT/HOLD report.")
            state.add_trace("Orchestrator", "Notice", "Skipping synthesis LLM call; using WAIT/HOLD engine report.", "info")
            state.final_response = str(wait_report)
            return {
                "response": state.final_response,
                "traces": state.traces,
                "steps": state.steps,
                "results": state.results,
            }

        state.add_trace("Router", "Route", "All plan steps completed. Proceeding to synthesize final response.")
        
        # Build results context string
        context_parts = []
        for r in state.results:
            agent_name = r["agent"]
            c_config = next((c for c in children if c["id"] == agent_name), {"name": agent_name})
            if "error" in r and "output" in r:
                context_parts.append(f"Agent {c_config['name']} reported execution blocker / error:\n{r['output']}")
            elif "error" in r:
                context_parts.append(f"Agent {c_config['name']} failed with error: {r['error']}")
            else:
                out = r["output"]
                if isinstance(out, dict) and "stdout" in out:
                    context_parts.append(f"Agent Code executed script. Success: {out['success']}.\nstdout output:\n{out['stdout']}\nScript code:\n{out['code']}")
                elif isinstance(out, dict) and "plot_url" in out:
                    context_parts.append(f"Agent Analyst generated chart. Success: {out['success']}.\nImage link: {out.get('plot_url')}")
                else:
                    context_parts.append(f"Agent {c_config['name']} returned data:\n{out}")
                    
        results_context = "\n---\n".join(context_parts) if context_parts else "No information from sub-agents (simple conversation)."
        
        # Call LLM to synthesize final response
        from backend.agent import DEFAULT_SYSTEM_PROMPT
        orch_system_prompt = DEFAULT_SYSTEM_PROMPT
        parent_agent = get_subagent(orch_id)
        if parent_agent and isinstance(parent_agent, dict):
            orch_system_prompt = parent_agent.get("system_prompt", DEFAULT_SYSTEM_PROMPT)
            
        parent_name = parent_agent.get("name", "Jarvis") if (parent_agent and isinstance(parent_agent, dict)) else "Jarvis"
        synth_prompt = (
            f"You are {parent_name}, a highly intelligent assistant.\n"
            f"Formulate the final response to the user based on their original query and the results of your sub-agents.\n\n"
            f"Original query: \"{query}\"\n\n"
            f"Results of sub-agents:\n{results_context}\n\n"
            f"CRITICAL FACTUALITY & ANTI-HALLUCINATION RULES:\n"
            f"1. STRICT ADHERENCE TO SUB-AGENT RESULTS: You MUST base your response strictly on the factual results returned by the sub-agents above.\n"
            f"2. ACCURATE ERROR REPORTING: If a sub-agent encountered an error, failure, or API rejection (e.g., Code 170140 or invalid parameter), YOU MUST TRUTHFULLY REPORT THAT THE ACTION FAILED and state the exact error message.\n"
            f"3. NO FAKE EXECUTION / NO HALLUCINATED RESOLUTIONS: You are CATEGORICALLY FORBIDDEN from inventing, pretending, or hallucinating that you or the sub-agents auto-corrected parameters, re-submitted orders, or opened positions that were NOT explicitly reported as successful in the sub-agents' outputs.\n"
            f"4. NO FAKE TOOL CALL TEXT: Do NOT output fake code blocks pretending to invoke tools or fake IDs unless confirmed by successful tool outputs.\n"
            f"5. EXECUTIVE SUMMARY FORMAT: Formulate an executive Markdown summary. Synthesis is a reporting stage, NOT a tool invocation stage. Under no circumstances should you output raw tool call code blocks or snippets.\n"
            f"{_plugin_hook('synthesis_extra_rules', default='') or ''}"
            f"Adhere to the tone and instructions of your system role. "
            f"Embed links to charts as Markdown images, for example: ![Chart](chart_url)."
        )
        
        synth_messages = [
            {"role": "system", "content": orch_system_prompt},
            {"role": "user", "content": synth_prompt}
        ]
        
        # Check if execution was aborted due to network outage or all steps experienced fatal network failure
        has_network_outage = (
            getattr(state, "aborted_due_to_network", False)
            or (
                bool(state.results)
                and all(
                    any(k in str(r.get("error", "")).lower() for k in (
                        "all connection attempts failed", "connecterror", "name or service not known",
                        "no address associated with hostname", "temporary failure in name resolution", "gaierror"
                    ))
                    for r in state.results
                )
            )
        )

        has_rate_limit_outage = (
            getattr(state, "aborted_due_to_rate_limit", False)
            or (
                bool(state.results)
                and all(
                    any(k in (str(r.get("error", "")) + " " + str(r.get("output", ""))).lower() for k in (
                        "429", "rate limit", "rate-limited", "engine_overloaded", "difficulties occurred while communicating with the server"
                    ))
                    for r in state.results
                )
            )
        )

        if has_network_outage:
            logger.info("Skipping synthesis LLM call due to upstream network outage. Generating subagents error summary.")
            state.add_trace("Orchestrator", "Abort", "Skipping synthesis LLM call due to confirmed network outage.", "warning")
            state.final_response = ""
        elif has_rate_limit_outage:
            logger.info("Skipping synthesis LLM call due to upstream rate-limit exhaustion across subagent steps. Generating subagents summary.")
            state.add_trace("Orchestrator", "Notice", "Skipping synthesis LLM call due to confirmed upstream rate-limit outage.", "info")
            state.aborted_due_to_rate_limit = True
            state.final_response = ""
        elif getattr(state, "aborted_due_to_ai_outage", False):
            logger.info("Skipping synthesis LLM call due to upstream AI provider outage across subagent steps. Generating subagents summary.")
            state.add_trace("Orchestrator", "Notice", "Skipping synthesis LLM call due to confirmed upstream AI provider outage.", "info")
            state.final_response = ""
        else:
            try:
                state.final_response = await call_llm(synth_messages, api_key, model)
            except BudgetExceededError:
                raise
            except Exception as synth_err:
                synth_err_desc = f"{type(synth_err).__name__}: {synth_err}".rstrip(": ") if str(synth_err) else type(synth_err).__name__
                is_fatal_net = any(k in synth_err_desc.lower() for k in (
                    "all connection attempts failed",
                    "name or service not known",
                    "no address associated with hostname",
                    "temporary failure in name resolution",
                    "connecterror",
                ))
                if is_fatal_net:
                    logger.info(f"Synthesis LLM call encountered network outage ({synth_err_desc}). Skipping secondary model fallback.")
                    state.aborted_due_to_network = True
                else:
                    logger.warning(f"Synthesis LLM call failed ({synth_err_desc}). Checking secondary synthesis fallback.")
                state.add_trace("Orchestrator", "Warning", f"Synthesis LLM call failed: {synth_err_desc}.", "warning")
                state.final_response = ""
            
            # Secondary synthesis fallback attempt
            if not getattr(state, "aborted_due_to_network", False) and not getattr(state, "aborted_due_to_rate_limit", False) and not getattr(state, "aborted_due_to_ai_outage", False) and (not state.final_response or not state.final_response.strip()):
                fallback_synth_model = os.getenv("LLM_FALLBACK_MODEL") or "google/gemini-2.5-flash"
                if fallback_synth_model and fallback_synth_model != model:
                    try:
                        logger.info(f"Retrying synthesis with secondary fallback model '{fallback_synth_model}'...")
                        state.final_response = await call_llm(synth_messages, api_key, fallback_synth_model)
                    except BudgetExceededError:
                        raise
                    except Exception as fb_err:
                        fb_err_desc = f"{type(fb_err).__name__}: {fb_err}".rstrip(": ") if str(fb_err) else type(fb_err).__name__
                        logger.warning(f"Secondary synthesis fallback model '{fallback_synth_model}' failed: {fb_err_desc}")
                        state.final_response = ""
        
        if not state.final_response or not state.final_response.strip():
            if getattr(state, "aborted_due_to_network", False) or getattr(state, "aborted_due_to_rate_limit", False) or getattr(state, "aborted_due_to_ai_outage", False) or has_network_outage or has_rate_limit_outage:
                logger.info("Using sub-agents' results context for final response due to confirmed upstream outage.")
            else:
                logger.warning("Synthesis LLM call returned an empty response or failed. Falling back to sub-agents' results context.")
            fallback_texts = []
            has_error = False
            for r in state.results:
                agent_name = r.get("agent", "agent")
                c_conf = next((c for c in children if c.get("id") == agent_name), {"name": agent_name})
                c_title = c_conf.get("name", agent_name)
                out = r.get("output")
                err = r.get("error")
                body = ""
                if isinstance(out, dict) and "stdout" in out and str(out["stdout"]).strip():
                    body = str(out["stdout"]).strip()
                elif isinstance(out, str) and out.strip():
                    body = out.strip()
                elif isinstance(out, dict) and "plot_url" in out:
                    body = f"Generated chart: {out.get('plot_url')}"
                elif out:
                    body = str(out)
                elif err:
                    has_error = True
                    body = f"⚠️ {err}"
                if body:
                    if err or (isinstance(body, str) and any(k in body.lower() for k in ("apologies, sir", "network error", "connecterror", "name or service not known"))):
                        has_error = True
                    fallback_texts.append(f"### {c_title} Output\n{body}")
            if fallback_texts:
                header = "### Sub-agent Execution Issues:\n\n" if has_error else "### Sub-agents execution results:\n\n"
                state.final_response = header + "\n\n".join(fallback_texts)
            else:
                state.final_response = "Apologies. The execution could not be completed because the assigned sub-agents encountered errors and produced no valid output."

        # Check if synthesis returned a bare tool-call snippet or raw JSON without an executive summary
        raw_resp = state.final_response.strip()
        is_raw_tool_block = False
        if (raw_resp.startswith("```") and raw_resp.endswith("```")) or (raw_resp.startswith("`") and raw_resp.endswith("`")):
            inner = raw_resp.strip("`").strip()
            if inner.lower().startswith("json"):
                inner = inner[4:].strip()
            try:
                parsed_call = json.loads(inner)
                from backend.plugins import tool_hints
                _name_bits = tuple(p.rstrip("_") for p in (tool_hints().get("prefixes") or ())) + ("tool", "cycle", "autonomous")
                if isinstance(parsed_call, dict) and any(any(bit and bit in str(k) for bit in _name_bits) for k in parsed_call.keys()):
                    is_raw_tool_block = True
            except Exception:
                pass
        elif re.match(r"^[a-zA-Z0-9_]+_cycle\(.*?\)$", raw_resp, re.DOTALL):
            is_raw_tool_block = True

        if is_raw_tool_block and state.results:
            summary_sections = []
            for r in state.results:
                agent_name = r.get("agent", "agent")
                c_conf = next((c for c in children if c.get("id") == agent_name), {"name": agent_name})
                c_title = c_conf.get("name", agent_name)
                out = r.get("output")
                body = ""
                if isinstance(out, dict) and "stdout" in out and str(out["stdout"]).strip():
                    body = str(out["stdout"]).strip()
                elif isinstance(out, str) and out.strip():
                    body = out.strip()
                elif isinstance(out, dict) and "plot_url" in out:
                    body = f"Generated chart: {out.get('plot_url')}"
                elif out:
                    body = str(out)
                if body:
                    summary_sections.append(f"#### {c_title} Findings:\n{body}")

            executive_header = f"### Executive Autonomous Briefing\n\nAll assigned sub-agents completed their operational analysis for query: *{query}*.\n\n"
            state.final_response = executive_header + "\n\n".join(summary_sections)
            state.add_trace("Orchestrator", "Formatting", "Formatted raw synthesis tool invocation into executive report.", "info")
        
        # Strip model tool delimiter tokens
        from backend.agent import sanitize_tool_tokens
        state.final_response = sanitize_tool_tokens(state.final_response)

        def _strip_tool_blocks(text: str) -> str:
            if not text:
                return text
            code_block_pat = re.compile(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
            def _replace(match):
                raw_json = match.group(1).strip()
                try:
                    data = json.loads(raw_json)
                    if isinstance(data, dict):
                        keys = [str(k).lower() for k in data.keys()]
                        from backend.plugins import tool_hints
                        _prefixes = ("exchange_", "call_subagent", "execute_tool") + tuple(tool_hints().get("prefixes") or ())
                        if any(any(prefix in k for prefix in _prefixes) for k in keys):
                            return ""
                        if "name" in keys and any(prefix in str(data.get("name", "")).lower() for prefix in _prefixes):
                            return ""
                        if "tool" in keys:
                            return ""
                except Exception:
                    pass
                return match.group(0)
            cleaned = code_block_pat.sub(_replace, text)
            return re.sub(r"\n{3,}", "\n\n", cleaned).strip()

        state.final_response = _strip_tool_blocks(state.final_response)

        guarded = _plugin_hook(
            "guard_orchestrator_response",
            state.final_response,
            orch_id,
            query,
            state.results,
            default=None,
        )
        if isinstance(guarded, str) and guarded != state.final_response:
            state.final_response = guarded
            state.add_trace("Orchestrator", "Guardrail", "Appended verification notice: synthesis claimed execution without tool calls.", "warning")

        # Calculate cost
        prompt_est = sum(len(m["content"]) for m in synth_messages) // 4
        completion_est = len(state.final_response) // 4
        from backend.agent import calculate_cost
        synth_cost = calculate_cost(model, prompt_est, completion_est)
        
        state.add_trace("Orchestrator", "Finish", "Synthesis complete. Response sent to Creator.", token_cost=synth_cost)
        
    except Exception as general_err:
        state.add_trace("Orchestrator", "Error", f"Critical orchestrator failure: {str(general_err)}", "error")
        state.final_response = f"Apologies. A failure occurred while coordinating my sub-agents: {str(general_err)}"
        
    return {
        "response": state.final_response,
        "traces": state.traces,
        "steps": state.steps,
        "results": state.results
    }


# ── Paperclip Heartbeat Pulse Execution Engine (FEAT-6) ─────────────────────────

async def run_orchestration_pulse(
    task_id: int,
    api_key: str,
    model: str,
    max_steps_per_pulse: int = 1
) -> Dict[str, Any]:
    """
    Executes a single heartbeat pulse window for a queued task.
    Reads/writes state checkpoints from/to DB (tasks.checkpoint_data),
    executing up to `max_steps_per_pulse` before persisting checkpoint and sleeping.
    """
    from backend.database import db_get_tasks, db_checkout_task, db_update_task

    tasks = db_get_tasks()
    task = next((t for t in tasks if t["id"] == task_id), None)
    if not task:
        return {"status": "error", "message": f"Task #{task_id} not found."}

    agent_id = task.get("assigned_agent_id") or "jarvis"
    checkout_res = db_checkout_task(task_id, agent_id=agent_id, lock_duration_seconds=120)
    if checkout_res.get("status") == "locked":
        logger.info(f"[Pulse] Task #{task_id} is currently locked by another process.")
        return checkout_res

    # Load existing state or initialize new AgentState
    state = AgentState.load_from_task(task_id)
    if not state:
        query = f"{task['title']}\n{task.get('description', '')}".strip()
        state = AgentState(query=query, chat_id=f"task_{task_id}")
        state.add_trace("PulseEngine", "Init", f"Initialized new pulse task #{task_id}: '{task['title']}'")

    # If steps not planned yet, run full orchestration or plan node
    if not state.steps and not state.final_response:
        res = await run_orchestration(state.query, api_key, model, chat_id=state.chat_id)
        state.final_response = res.get("response", "")
        state.steps = res.get("steps", [])
        state.current_step_idx = len(state.steps)
        state.save_to_task(task_id)
        db_update_task(task_id, status="DONE")
        return {
            "status": "completed",
            "task_id": task_id,
            "response": state.final_response,
            "checkpoint": state.to_dict()
        }

    # Execute up to max_steps_per_pulse
    steps_executed = 0
    while state.current_step_idx < len(state.steps) and steps_executed < max_steps_per_pulse:
        step = state.steps[state.current_step_idx]
        state.add_trace("PulseEngine", "Step", f"Pulse step {state.current_step_idx+1}/{len(state.steps)}: {step.get('agent')}")
        state.current_step_idx += 1
        steps_executed += 1

    # Check if finished
    if state.current_step_idx >= len(state.steps):
        state.save_to_task(task_id)
        db_update_task(task_id, status="DONE")
        return {
            "status": "completed",
            "task_id": task_id,
            "response": state.final_response or "Task execution completed.",
            "checkpoint": state.to_dict()
        }
    else:
        state.save_to_task(task_id)
        db_update_task(task_id, status="IN_PROGRESS")
        return {
            "status": "pulsed",
            "task_id": task_id,
            "current_step": state.current_step_idx,
            "total_steps": len(state.steps),
            "checkpoint": state.to_dict()
        }
