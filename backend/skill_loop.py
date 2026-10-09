import os
import re
import json
import logging
import httpx
from typing import List, Dict, Any, Optional

logger = logging.getLogger("hermes.skill_loop")

workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
default_skills_dir = os.path.join(workspace_root, ".agents", "skills")
SKILLS_DIR = os.getenv("DISTILLED_SKILLS_DIR", default_skills_dir)


def _is_scheduled_automation_log(log_entry: Dict[str, Any]) -> bool:
    """Scheduled task logs are not reusable skills — distilling them feeds RAG and inflates the next run."""
    if not isinstance(log_entry, dict):
        return False
    if log_entry.get("is_scheduled") or log_entry.get("scheduled"):
        return True
    sid = str(log_entry.get("session_id") or "").lower()
    if sid.startswith("task_") or "scheduled" in sid:
        return True
    msg = str(log_entry.get("user_message") or "").strip().lower()
    return (
        msg.startswith("execute scheduled task:") or
        "scheduled task" in msg or
        "scheduled automation" in msg or
        "scheduled run" in msg
    )


def slugify(text: str) -> str:
    """Helper to turn a title or sentence into a safe file slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:60].strip("_") or "distilled_skill"


class SkillDistiller:
    """Core engine for observing execution outcomes, distilling trajectories into SKILL.md,

    and indexing them into RAG memory.
    """

    def __init__(
        self,
        api_base: Optional[str] = None,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_base = api_base or os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
        self.api_key = api_key or os.getenv("OPENROUTER_API_KEY")
        self.model = model or os.getenv("LLM_MODEL", "ollama/llama3")

    def distill_log_entry(self, log_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Distills a single successful decision log entry into a structured skill.

        Returns a dictionary containing skill_name, title, trigger_conditions, and content.
        """
        user_msg = log_entry.get("user_message", "")
        assistant_resp = log_entry.get("assistant_response", "")
        err_msg = str(log_entry.get("error") or "").lower()
        success = log_entry.get("success")

        # 1. Check explicit success flag
        if success is False or success == 0:
            raise ValueError(f"Log entry #{log_entry.get('id')} marked as unsuccessful, skipping skill distillation.")

        # 2. Check error messages or known failure signatures
        failure_markers = [
            "ошибка исполнения", "170140", "order value exceeded",
            "autonomous execution cycle: failed", "compliance verdict: failed",
            "execution cycle: failed", "execution halted", "cycle failed",
            "apologies, sir.", "rate limit exceeded", "too many requests",
            "trading paused", "tool seems to be unavailable", "tool unavailable",
            "blocked gate", "trades blocked", "compliance check: rejected",
            "ch_access_token_invalid", "critical authentication failure",
            "critical authentication", "authentication failure",
            "authentication expired", "authentication required",
            "re-authentication required", "trading execution blocked",
            "execution blocked", "trade execution: blocked", "trade execution blocked",
            "cannot perform a comprehensive", "api offline", "not authorized",
            "invalid access token",
            "i need to know which symbol", "please provide the symbol",
            "which symbol to run", "what symbol to run", "what instrument are you planning",
            "await the proposed trade", "awaiting proposed trade",
            "without proper input confirmation"
        ]
        try:
            from backend.plugins import collect as _collect_markers
            failure_markers.extend(_collect_markers("broker_failure_markers"))
        except Exception:
            pass
        from backend.database import match_failure_marker
        matched_marker = match_failure_marker(assistant_resp, failure_markers)
        if err_msg or matched_marker:
            raise ValueError(f"Log entry #{log_entry.get('id')} contains error or execution failure, skipping skill distillation.")

        # 3. Check traces for error status or failure text
        traces = log_entry.get("traces", [])
        if isinstance(traces, list):
            for t in traces:
                if isinstance(t, dict):
                    if t.get("status") in ("error", "failed"):
                        raise ValueError(f"Log entry #{log_entry.get('id')} contains error status in traces, skipping skill distillation.")
                    t_msg = str(t.get("message") or "").lower()
                    if any(marker in t_msg for marker in (
                        "tool seems to be unavailable", "tool unavailable", "trading paused",
                        "ch_access_token_invalid", "trades blocked", "authentication required",
                        "authentication failure", "re-authentication required", "trading execution blocked",
                        "execution blocked", "trade execution: blocked", "not authorized",
                        "cannot perform a comprehensive", "i need to know which symbol",
                        "please provide the symbol", "which symbol to run", "what symbol to run",
                        "await the proposed trade", "awaiting proposed trade"
                    )):
                        raise ValueError(f"Log entry #{log_entry.get('id')} contains tool failure, parameter stall, or trading paused in trace messages, skipping skill distillation.")

        # 4. Check if it's a scheduled automation run
        if _is_scheduled_automation_log(log_entry):
            raise ValueError(
                f"Log entry #{log_entry.get('id')} is a scheduled automation run, skipping skill distillation."
            )

        # 4. Check for minimum worker execution steps (avoid distilling 0-worker scaffolding runs)
        worker_traces = [
            t for t in traces
            if isinstance(t, dict) and (
                t.get("agent") not in ("Orchestrator", "Router") or
                t.get("action") in ("Execute", "Tool", "Search", "Plot")
            )
        ]
        if not worker_traces:
            raise ValueError(f"Log entry #{log_entry.get('id')} has 0 worker execution steps, skipping skill distillation.")

        if not self.api_key:
            logger.info("No LLM API key provided. Using heuristic skill distiller.")
            return self._heuristic_distillation(log_entry)

        traces = log_entry.get("traces", [])
        traces_str = json.dumps(traces, indent=2) if isinstance(traces, (list, dict)) else str(traces)

        prompt = (
            "You are an expert AI Capability Distiller. Your task is to observe a successful multi-step agent "
            "execution trajectory and distill it into a reusable, modular capability skill document formatted in Markdown.\n\n"
            f"### User Input Goal:\n{user_msg}\n\n"
            f"### Execution Traces / Steps Taken:\n{traces_str}\n\n"
            f"### Final Result / Output:\n{assistant_resp}\n\n"
            "--- Instructions ---\n"
            "Generate a structured SKILL.md document with EXACTLY the following sections:\n"
            "# Skill: <Short Action-Oriented Title>\n\n"
            "## Trigger Conditions\n"
            "- <When to apply this skill: specific user intent keywords or contexts>\n\n"
            "## Procedure & Pitfalls\n"
            "1. <Step-by-step procedure derived from the successful trace>\n"
            "2. <Include pitfalls or precautions to avoid failure>\n\n"
            "## Verification Checklist\n"
            "- [ ] <Verification criteria to confirm successful execution>\n\n"
            "Respond ONLY with the complete Markdown text. Do not wrap in extra commentary."
        )

        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            from backend.llm_model_manager import resolve_provider_model
            payload = {
                "model": resolve_provider_model(self.model, self.api_base),
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "max_tokens": 1500,
            }
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(f"{self.api_base}/chat/completions", json=payload, headers=headers)

            if resp.status_code == 200:
                resp_data = resp.json()
                if isinstance(resp_data, dict) and resp_data.get("choices") and len(resp_data["choices"]) > 0:
                    choice_0 = resp_data["choices"][0]
                    msg_obj = choice_0.get("message") if isinstance(choice_0, dict) else {}
                    raw_content = msg_obj.get("content") if isinstance(msg_obj, dict) else None
                    if raw_content and isinstance(raw_content, str):
                        content = raw_content.strip()
                        if content.startswith("```"):
                            content = re.sub(r"^```[a-zA-Z]*\n", "", content)
                            content = re.sub(r"\n```$", "", content)
                        return self._parse_skill_markdown(content, log_entry)
        except Exception as err:
            err_desc = f"{type(err).__name__}: {err}".rstrip(": .") if str(err) else type(err).__name__
            logger.warning(f"LLM skill distillation failed: {err_desc}. Falling back to heuristic distiller.")

        return self._heuristic_distillation(log_entry)

    def _parse_skill_markdown(self, markdown_text: str, log_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Parses generated Markdown text to extract title, triggers, and skill name."""
        title_match = re.search(r"^#\s*(?:Skill:\s*)?(.+)$", markdown_text, re.MULTILINE)
        title = title_match.group(1).strip() if title_match else f"Skill for {log_entry.get('user_message', 'Task')[:40]}"
        
        triggers_match = re.search(r"##\s*Trigger Conditions\s*\n((?:[^\n#]+\n?)+)", markdown_text, re.IGNORECASE)
        trigger_conditions = triggers_match.group(1).strip() if triggers_match else f"When handling queries related to: {log_entry.get('user_message', '')[:60]}"
        
        log_id = log_entry.get("id")
        suffix = f"_{log_id}" if log_id else ""
        skill_name = f"{slugify(title)}{suffix}"
        
        return {
            "skill_name": skill_name,
            "title": title,
            "trigger_conditions": trigger_conditions,
            "content": markdown_text,
            "decision_log_id": log_id,
            "session_id": log_entry.get("session_id", "default")
        }

    def _heuristic_distillation(self, log_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Programmatic fallback distiller when LLM API is unavailable."""
        user_msg = log_entry.get("user_message", "").strip()
        traces = log_entry.get("traces", [])
        assistant_resp = log_entry.get("assistant_response", "").strip()

        log_id = log_entry.get("id")
        suffix = f"_{log_id}" if log_id else ""
        title = f"Distilled Procedure for {user_msg[:45]}" if user_msg else "Multi-Step Procedure Skill"
        skill_name = f"{slugify(title)}{suffix}"

        steps_lines = []
        if isinstance(traces, list) and traces:
            for idx, trace in enumerate(traces, 1):
                if isinstance(trace, dict):
                    action = trace.get("action") or trace.get("agent_id") or trace.get("tool") or f"Step {idx}"
                    result = trace.get("result") or trace.get("output") or "Success"
                    steps_lines.append(f"{idx}. **Execute Action (`{action}`)**: {str(result)[:120]}")
                else:
                    steps_lines.append(f"{idx}. {str(trace)[:120]}")
        else:
            steps_lines.append("1. Parse user task parameters.\n2. Coordinate execution steps.\n3. Validate intermediate outputs.")

        steps_block = "\n".join(steps_lines)
        
        content = (
            f"# Skill: {title}\n\n"
            f"## Trigger Conditions\n"
            f"- Applies when executing tasks involving: {user_msg}\n\n"
            f"## Procedure & Pitfalls\n"
            f"{steps_block}\n\n"
            f"## Verification Checklist\n"
            f"- [ ] Target task completed successfully\n"
            f"- [ ] Final response produced: {assistant_resp[:100]}...\n"
        )

        return {
            "skill_name": skill_name,
            "title": title,
            "trigger_conditions": f"Tasks matching: {user_msg[:60]}",
            "content": content,
            "decision_log_id": log_entry.get("id"),
            "session_id": log_entry.get("session_id", "default")
        }

    def save_and_index_skill(self, skill_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Saves distilled skill markdown to disk, records in database, and indexes in memory."""
        os.makedirs(SKILLS_DIR, exist_ok=True)
        
        skill_name = skill_dict["skill_name"]
        filename = f"{skill_name}.md"
        filepath = os.path.join(SKILLS_DIR, filename)
        skill_dict["file_path"] = filepath

        from backend.database import db_save_distilled_skill
        skill_id = db_save_distilled_skill(skill_dict)
        if skill_id == -1:
            logger.warning(f"Skill '{skill_name}' rejected by database (invalid/failure markers), skipping file save and indexing.")
            skill_dict["id"] = -1
            return skill_dict

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(skill_dict["content"])

        skill_dict["id"] = skill_id

        # Index into RAG memory (Qdrant & GraphRAG)
        try:
            from backend.memory import get_memory_engine
            engine = get_memory_engine()
            doc_id = f"distilled_skill_{skill_name}"
            success = engine.index_document(
                doc_id=doc_id,
                title=skill_dict["title"],
                text=skill_dict["content"],
                source="distilled_skill",
                note_path=filepath
            )
            logger.info(f"Indexed distilled skill '{skill_dict['title']}' into RAG memory: {success}")
        except Exception as exc:
            logger.error(f"Failed to index distilled skill into memory: {exc}")

        return skill_dict

    def process_undistilled_logs(self, min_steps: int = 3, limit: int = 10) -> List[Dict[str, Any]]:
        """Scans database for successful multi-step decision logs that haven't been distilled,

        distills them, and indexes the resulting skills.
        """
        from backend.database import db_get_undistilled_successful_logs
        undistilled_logs = db_get_undistilled_successful_logs(min_steps=min_steps, limit=limit)
        
        distilled_results = []
        for log in undistilled_logs:
            if _is_scheduled_automation_log(log):
                logger.info("Skipping skill distillation for scheduled automation log #%s", log.get("id"))
                continue
            try:
                skill_dict = self.distill_log_entry(log)
                saved_skill = self.save_and_index_skill(skill_dict)
                distilled_results.append(saved_skill)
                logger.info(f"Distilled log #{log['id']} into skill '{saved_skill['skill_name']}'")
            except ValueError as e:
                logger.info(f"Skipping skill distillation for log #{log.get('id')}: {e}")
            except Exception as e:
                logger.error(f"Error distilling log #{log.get('id')}: {e}")

        return distilled_results


def get_skill_distiller() -> SkillDistiller:
    """Factory helper to obtain a SkillDistiller instance."""
    return SkillDistiller()
