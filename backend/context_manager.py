"""
Centralized Context Window Manager for Jarvis.
Provides token counting, context budgeting, history summarization, and step output compression.
"""

import re
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("hermes.context_manager")

DEFAULT_MAX_SUBAGENT_TOKENS = 16000
DEFAULT_MAX_STEP_OUTPUT_CHARS = 3000

def estimate_tokens(text: str) -> int:
    """Estimates token count for a string using a hybrid length heuristic."""
    if not text:
        return 0
    non_ascii_count = len(re.findall(r'[^\x00-\x7F]', text))
    ascii_count = len(text) - non_ascii_count
    estimated = int((ascii_count / 4.0) + (non_ascii_count / 1.8))
    return max(1, estimated)

def compress_step_context(results: List[Dict[str, Any]], max_chars_per_step: int = DEFAULT_MAX_STEP_OUTPUT_CHARS) -> str:
    """
    Compresses previous sub-agent execution outputs so they don't bloat the prompt window.
    """
    if not results:
        return ""
        
    context_parts = []
    for prev_res in results:
        step_num = prev_res.get("step", 0) + 1
        agent_name = prev_res.get("agent", "subagent")
        
        if "error" in prev_res:
            context_parts.append(f"[Step {step_num} ({agent_name}) Error]: {prev_res['error']}")
            continue
            
        out = prev_res.get("output", "")
        if isinstance(out, dict):
            if "stdout" in out:
                stdout_str = str(out["stdout"]).strip()
                if len(stdout_str) > max_chars_per_step:
                    stdout_str = stdout_str[:max_chars_per_step] + "\n...[truncated output]"
                context_parts.append(f"[Step {step_num} (Code Agent stdout)]:\n{stdout_str}")
            elif "plot_url" in out:
                context_parts.append(f"[Step {step_num} (Analyst Agent Chart)]: {out.get('plot_url')}")
            else:
                out_str = str(out)
                if len(out_str) > max_chars_per_step:
                    out_str = out_str[:max_chars_per_step] + "\n...[truncated]"
                context_parts.append(f"[Step {step_num} ({agent_name}) Output]:\n{out_str}")
        else:
            out_str = str(out).strip()
            if len(out_str) > max_chars_per_step:
                out_str = out_str[:max_chars_per_step] + "\n...[truncated long step report]"
            context_parts.append(f"[Step {step_num} ({agent_name}) Output]:\n{out_str}")

    return "\n\nData from previous steps:\n" + "\n---\n".join(context_parts)

def build_subagent_messages(
    system_prompt: str,
    system_info: str,
    lang_directive: str,
    history: List[Dict[str, str]],
    user_content: str,
    max_tokens: int = DEFAULT_MAX_SUBAGENT_TOKENS
) -> List[Dict[str, str]]:
    """
    Dynamically constructs subagent prompt messages ensuring total tokens remain under max_tokens budget.
    """
    base_messages = [{"role": "system", "content": system_prompt + system_info + lang_directive}]
    base_tokens = estimate_tokens(base_messages[0]["content"])
    
    user_tokens = estimate_tokens(user_content)
    
    max_user_tokens = int(max_tokens * 0.5)
    if user_tokens > max_user_tokens:
        max_user_chars = max_user_tokens * 3
        user_content = user_content[:max_user_chars] + "\n...[truncated for token budget]"
        user_tokens = estimate_tokens(user_content)

    remaining_budget = max_tokens - base_tokens - user_tokens
    
    history_messages = []
    if history and remaining_budget > 500:
        for msg in reversed(history):
            content = msg.get("content") or ""
            msg_tokens = estimate_tokens(content)
            
            if msg_tokens > 500:
                content = content[:1500] + "\n...[truncated history entry]"
                msg_tokens = estimate_tokens(content)
                
            if remaining_budget - msg_tokens < 0:
                break
                
            history_messages.insert(0, {"role": msg.get("role", "user"), "content": content})
            remaining_budget -= msg_tokens
            
    final_messages = base_messages + history_messages + [{"role": "user", "content": user_content}]
    total_est = estimate_tokens("".join([m["content"] for m in final_messages]))
    logger.debug(f"Built subagent payload: {len(final_messages)} messages, ~{total_est} est tokens (budget: {max_tokens})")
    return final_messages
