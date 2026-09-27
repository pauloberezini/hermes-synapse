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
    if not isinstance(text, str):
        text = str(text)
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
            from backend.agent import sanitize_tool_tokens
            out_str = sanitize_tool_tokens(out_str)
            if len(out_str) > max_chars_per_step:
                out_str = out_str[:max_chars_per_step] + "\n...[truncated long step report]"
            context_parts.append(f"[Step {step_num} ({agent_name}) Output]:\n{out_str}")

    return "\n\nData from previous steps:\n" + "\n---\n".join(context_parts)

def _clean_unverified_history_content(content: str) -> str:
    """
    Strips unverified indicator, position, and balance simulation notices and their accompanying
    simulated markdown tables from historical assistant messages so they do not
    pollute future ReAct turns with hallucinated data.
    """
    has_unverified = any(marker in content for marker in (
        "⚠️ Notice: Technical indicators",
        "⚠️ Notice: Live broker position",
        "⚠️ Notice: Live broker account",
        "unverified simulations",
        "Simulated / Live Broker Tool Not Triggered",
        "⚠️ **Simulated Positions",
        "⚠️ Simulated Positions",
    ))
    if not has_unverified:
        return content

    # Strip the warning notices
    content = re.sub(r"⚠️ Notice: [^\n]*\n*", "", content)
    content = re.sub(r"\*?\(⚠️ Unverified Simulation[^\n]*\)?\*?\n*", "", content)

    # Strip unverified markdown tables (headers, separators, and rows)
    table_pattern = r"(?:###\s+[^\n]*\n+)?\|[^\n]*(?:RSI|ATR|Remizov|Signal|Position|P/?L|Instrument|Asset)[^\n]*\|\n\|[-:\s|]+\|\n(?:\|[^\n]+\|\n*)+"
    content = re.sub(table_pattern, "", content, flags=re.IGNORECASE)

    return re.sub(r"\n{3,}", "\n\n", content).strip()


def sanitize_chat_history(history: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """
    Sanitizes conversation history:
    - Filters empty content and non-user/assistant roles.
    - Prevents consecutive messages with the same role (collapses runs of assistant messages,
      retaining only the latest).
    - Ensures history doesn't start with orphan assistant messages.
    - Strips unverified simulation notices and hallucinated tables from assistant history.
    - Ensures valid alternating sequence for LLM chat completions.
    """
    if not history:
        return []

    cleaned: List[Dict[str, str]] = []
    for msg in history:
        role = msg.get("role", "user")
        content = (msg.get("content") or "").strip()
        if not content or role not in ("user", "assistant"):
            continue

        if role == "assistant":
            content = _clean_unverified_history_content(content)
            if not content:
                continue

        if cleaned and cleaned[-1]["role"] == role:
            if role == "assistant":
                # Replace with the latest assistant message
                cleaned[-1] = {"role": "assistant", "content": content}
            else:
                cleaned[-1] = {"role": "user", "content": content}
        else:
            cleaned.append({"role": role, "content": content})

    # Drop leading assistant message if there was no preceding user message
    while cleaned and cleaned[0]["role"] == "assistant":
        cleaned.pop(0)

    return cleaned


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
    sanitized_history = sanitize_chat_history(history)
    if sanitized_history and remaining_budget > 500:
        for msg in reversed(sanitized_history):
            content = msg.get("content") or ""
            msg_tokens = estimate_tokens(content)
            
            if msg_tokens > 500:
                content = content[:1500] + "\n...[truncated history entry]"
                msg_tokens = estimate_tokens(content)
                
            if remaining_budget - msg_tokens < 0:
                break
                
            history_messages.insert(0, {"role": msg.get("role", "user"), "content": content})
            remaining_budget -= msg_tokens
            
    # If history ends with user and user_content is next, drop to prevent consecutive user messages
    while history_messages and history_messages[-1]["role"] == "user":
        history_messages.pop()

    final_messages = base_messages + history_messages + [{"role": "user", "content": user_content}]
    total_est = estimate_tokens("".join([str(m.get("content", "")) for m in final_messages]))
    logger.debug(f"Built subagent payload: {len(final_messages)} messages, ~{total_est} est tokens (budget: {max_tokens})")
    return final_messages


