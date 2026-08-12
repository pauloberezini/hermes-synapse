import json
import time
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

async def run_orchestration(query: str, api_key: str, model: str, chat_id: str = "default", parent_skills: Optional[str] = None) -> Dict[str, Any]:
    state = AgentState(query, chat_id)
    
    import re
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
    
    # Compute active_skills (intersection of parent_skills and this orchestrator's connected skills)
    active_skills = ""
    if orch_meta and orch_meta.get("skills"):
        orch_skills = orch_meta["skills"]
        if parent_skills:
            p_set = set(s.strip() for s in parent_skills.split(",") if s.strip())
            o_set = set(s.strip() for s in orch_skills.split(",") if s.strip())
            active_skills = ",".join(o_set.intersection(p_set))
        else:
            active_skills = orch_skills
    else:
        active_skills = parent_skills or ""
    all_subagents = get_all_subagents()
    children = [a for a in all_subagents if a.get("parent_id") == orch_id]
    
    # Fallback to defaults if no children connected to jarvis
    if not children and orch_id == "jarvis":
        children = [
            {"id": "research", "name": "Search Agent", "system_prompt": "You are a research agent. Search for information on the internet.", "model": "google/gemini-2.5-flash", "agent_type": "agent", "skills": "web_search"},
            {"id": "code", "name": "Code Engineer", "system_prompt": "You are a Code Engineer. Write and execute Python scripts.", "model": "google/gemini-2.5-flash", "agent_type": "agent", "skills": "python_sandbox"},
            {"id": "analyst", "name": "Visualizer", "system_prompt": "You are an Analyst-Visualizer. Create charts.", "model": "google/gemini-2.5-flash", "agent_type": "agent", "skills": "python_sandbox"}
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
    dynamic_planner_prompt = """You are the Planner in a multi-agent system. 
Your task is to break down a complex user query into a sequence of steps to be executed by specialized sub-agents under your command.

Available sub-agents:
"""
    for child in children:
        dynamic_planner_prompt += f'- "{child["id"]}" (Name: {child["name"]}) — {child["system_prompt"][:250]}\n'
        
    dynamic_planner_prompt += """
You must output the result EXCLUSIVELY in JSON format of the following structure:
{
  "steps": [
    {"agent": "agent_id", "instructions": "clear instructions for the agent in English"}
  ]
}

Rules:
- If the query requires fetching real-time information (e.g., today's football matches, betting odds, current weather, currency rates, today's news), you MUST schedule the first step with the "research" agent (or another agent with internet search capability) to fetch data from the Internet. Do not try to solve such tasks with agents that have no network access (like the "code" agent).
- When writing `instructions` for the search/research step, you MUST convert any relative dates ("today", "tomorrow", "evening matches", "current round") into specific calendar dates based on system time (e.g., "matches on June 21, 2026", "schedule for 21.06.2026"). This is critical for search engine accuracy!
- When searching for sports and betting data, schedule a search step strictly to search for raw information: match schedules, pairs of playing teams, start times, and numerical bookmaker odds. It is categorically forbidden to search for pre-made predictions, tips, or external articles recommending bets ("bets of the day", "value bets by...").
- Expected value and value bet calculation must be performed strictly at the "code" step or by a specialized analyst agent. If using code, instruct the "code" agent to write a Python script that takes real odds and competitor pairs from search results, calculates the mathematical expected value EV = P * Odds - 1 for outcomes, and prints value bets (EV > 0).
- Special Note: The "code" agent runs in an offline sandbox. Do not expect it to make network calls.
- Agents must not be too lazy to do calculations: if exact bookmaker odds are not found in the search results, they MUST perform mathematical modeling (e.g., calculate win/draw/loss probabilities using a Poisson distribution based on average goals scored/conceded by the teams in the league/season, or estimate probabilities based on recent head-to-head statistics) and run the calculation instead of simply returning an error.
- It is categorically forbidden to invent demo, fictitious, or test matches (e.g., Spartak vs Zenit, if they are not in today's schedule). All calculations and conclusions must rely solely on real matches and real teams found in search results.
- For financial, crypto, or options queries, you MUST schedule steps to fetch REAL LIVE NUMERIC DATA (exact spot prices, staking ratio, ETF net flows, gas burn rate, IV surface metrics) via web_search or market tools. NEVER output generic textbook explanations when exact live metrics can be retrieved.
- If the request is simple and does not require sub-agents, return an empty list of steps: {"steps": []}.
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
            if attempt > 0:
                state.add_trace("Orchestrator", "Planning", f"Retry attempt {attempt}/{max_retries} due to validation error: {parse_err}", "warning")
                planner_messages.append({"role": "assistant", "content": plan_response})
                planner_messages.append({"role": "user", "content": f"Your previous output was invalid and failed schema validation with error:\n{parse_err}\n\nPlease output clean, valid JSON matching the schema correctly, without explanations or preambles."})
                
            try:
                plan_response = await call_llm(planner_messages, api_key, planner_model)
                
                # Parse plan
                json_str = plan_response.strip()
                if json_str.startswith("```json"):
                    json_str = json_str[7:]
                if json_str.endswith("```"):
                    json_str = json_str[:-3]
                json_str = json_str.strip()
                
                # Calculate cost
                prompt_est = sum(len(m["content"]) for m in planner_messages) // 4
                completion_est = len(plan_response) // 4
                from backend.agent import calculate_cost
                plan_cost += calculate_cost(planner_model, prompt_est, completion_est)
                
                try:
                    plan_data = json.loads(json_str)
                except json.JSONDecodeError as je:
                    raise ValueError(f"Invalid JSON format. Underlying error: {str(je)}")
                
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
                
                state.steps = plan_data.get("steps", [])
                state.add_trace("Orchestrator", "Planning", f"Plan of {len(state.steps)} steps generated.", token_cost=plan_cost)
                parse_err = None
                break
            except Exception as e:
                parse_err = str(e)
                logger.error(f"Failed to parse or validate planner JSON (attempt {attempt}/{max_retries}): {parse_err}. Response was: {plan_response}")
                
        if parse_err is not None:
            state.steps = []
            state.add_trace("Orchestrator", "Planning", f"Failed to generate structured plan after {max_retries} retries. Falling back to direct response.", "warning")
            
        # 2. ROUTER LOOP
        from backend.agent import agent_instance
        
        while state.current_step_idx < len(state.steps):
            step = state.steps[state.current_step_idx]
            agent_type = step.get("agent")
            instructions = step.get("instructions")
            
            # Find agent config
            child_agent = next((c for c in children if c["id"] == agent_type), None)
            if not child_agent:
                # Check from all subagents as backup
                child_agent = next((a for a in all_subagents if a["id"] == agent_type), None)
                
            if not child_agent:
                state.add_trace("Router", "Error", f"Unknown agent: {agent_type}", "error")
                state.current_step_idx += 1
                continue
                
            # Build context from previous steps using compress_step_context
            from backend.context_manager import compress_step_context
            context_str = compress_step_context(state.results, max_chars_per_step=3000)

            contextual_instructions = instructions + context_str
            if file_context:
                contextual_instructions = file_context + "\n\n" + contextual_instructions
            state.add_trace("Router", "Route", f"Step {state.current_step_idx+1}/{len(state.steps)}: Delegating to agent '{child_agent['name']}' ({agent_type})")
            
            # Check node execution type
            is_sub_orch = child_agent.get("agent_type") in ("orchestrator", "sub-orchestrator")
            
            if is_sub_orch:
                try:
                    # Recursive dynamic orchestration call!
                    logger.info(f"Triggering recursive sub-orchestration for '{agent_type}'")
                    sub_orch_res = await run_orchestration(contextual_instructions, api_key, model, chat_id=agent_type, parent_skills=active_skills)
                    state.results.append({"step": state.current_step_idx, "agent": agent_type, "output": sub_orch_res["response"]})
                    # Add child traces to parent traces
                    for trace in sub_orch_res.get("traces", []):
                        state.traces.append({
                            **trace,
                            "agent": f"{child_agent['name']} > {trace['agent']}"
                        })
                    state.add_trace(child_agent["name"], "Orchestrate", f"Sub-orchestrator completed. Result: {sub_orch_res['response'][:120]}...")
                except Exception as e:
                    state.results.append({"step": state.current_step_idx, "agent": agent_type, "error": str(e)})
                    state.add_trace(child_agent["name"], "Error", f"Sub-orchestration error: {str(e)}", "error")
            
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
                    res = await agent_instance._respond_as_subagent(contextual_instructions, child_agent, parent_skills=active_skills)
                    state.results.append({"step": state.current_step_idx, "agent": agent_type, "output": res})
                    state.add_trace(child_agent["name"], "Execute", f"Sub-agent completed execution: {res[:120]}...")
                except Exception as e:
                    state.results.append({"step": state.current_step_idx, "agent": agent_type, "error": str(e)})
                    state.add_trace(child_agent["name"], "Error", f"Error: {str(e)}", "error")
                    
            state.current_step_idx += 1
            
        # 3. SYNTHESIZE NODE
        state.add_trace("Router", "Route", "All plan steps completed. Proceeding to synthesize final response.")
        
        # Build results context string
        context_parts = []
        for r in state.results:
            agent_name = r["agent"]
            c_config = next((c for c in children if c["id"] == agent_name), {"name": agent_name})
            if "error" in r:
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
        if parent_agent:
            orch_system_prompt = parent_agent["system_prompt"]
            
        synth_prompt = (
            f"You are {parent_agent['name'] if parent_agent else 'Jarvis'}, a highly intelligent assistant.\n"
            f"Formulate the final response to the user (Sir) based on their original query and the results of your sub-agents.\n\n"
            f"Original query of Sir: \"{query}\"\n\n"
            f"Results of sub-agents:\n{results_context}\n\n"
            f"CRITICAL FACTUALITY & ANTI-HALLUCINATION RULES:\n"
            f"1. STRICT ADHERENCE TO SUB-AGENT RESULTS: You MUST base your response strictly on the factual results returned by the sub-agents above.\n"
            f"2. ACCURATE ERROR REPORTING: If a sub-agent encountered an error, failure, or API rejection (e.g., Code 170140 or invalid parameter), YOU MUST TRUTHFULLY REPORT THAT THE ACTION FAILED and state the exact error message.\n"
            f"3. NO FAKE EXECUTION / NO HALLUCINATED RESOLUTIONS: You are CATEGORICALLY FORBIDDEN from inventing, pretending, or hallucinating that you or the sub-agents auto-corrected parameters, re-submitted orders, or opened positions that were NOT explicitly reported as successful in the sub-agents' outputs.\n"
            f"4. NO FAKE TOOL CALL TEXT: Do NOT output fake code blocks pretending to invoke tools (e.g. `bybit_place_order`) or fake order IDs unless confirmed by successful tool outputs.\n\n"
            f"Adhere to the tone and instructions of your system role. "
            f"Embed links to charts as Markdown images, for example: ![Chart](chart_url)."
        )
        
        synth_messages = [
            {"role": "system", "content": orch_system_prompt},
            {"role": "user", "content": synth_prompt}
        ]
        
        state.final_response = await call_llm(synth_messages, api_key, model)
        
        if not state.final_response or not state.final_response.strip():
            logger.warning("Synthesis LLM call returned an empty response. Falling back to sub-agents' results context.")
            fallback_texts = []
            for r in state.results:
                out = r.get("output")
                if isinstance(out, dict) and "stdout" in out and out["stdout"].strip():
                    fallback_texts.append(out["stdout"].strip())
                elif isinstance(out, str) and out.strip():
                    fallback_texts.append(out.strip())
            if fallback_texts:
                state.final_response = "\n\n".join(fallback_texts)
            else:
                state.final_response = "Execution completed, but no text output was generated by sub-agents."
        
        # Calculate cost
        prompt_est = sum(len(m["content"]) for m in synth_messages) // 4
        completion_est = len(state.final_response) // 4
        from backend.agent import calculate_cost
        synth_cost = calculate_cost(model, prompt_est, completion_est)
        
        state.add_trace("Orchestrator", "Finish", "Synthesis complete. Response sent to Creator.", token_cost=synth_cost)
        
    except Exception as general_err:
        state.add_trace("Orchestrator", "Error", f"Critical orchestrator failure: {str(general_err)}", "error")
        state.final_response = f"Apologies, Sir. A failure occurred while coordinating my sub-agents: {str(general_err)}"
        
    return {
        "response": state.final_response,
        "traces": state.traces,
        "steps": state.steps
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
