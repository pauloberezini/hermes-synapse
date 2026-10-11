"""Hire a specialist under an orchestrator, or reuse one that already exists."""

import os
import re
from datetime import datetime, timezone
from backend.database import get_all_subagents, get_subagent, save_subagent
from backend.plugins import collect, hook
from backend.subagents import get_agent_model

# ponytail: token overlap, not embeddings. Swap in rag search if false hires show up.
_NEVER = {"agent_management", "agent_delegation"}
_RISKY = {"shell_execution", "python_sandbox"}
_STOP = {
    "which", "where", "about", "please", "should", "would", "could",
    "using", "needs", "today", "their", "there", "these", "those",
    "проверь", "нужно", "надо", "какие",
    "привет", "hello", "thanks", "thank",
}


def auto_hire_mode() -> str:
    return os.getenv("AUTO_HIRE", "ask").strip().lower()


def _stopwords() -> set:
    words = {w.lower() for w in _STOP}
    for extra in collect("gap_stopwords"):
        blob = extra if isinstance(extra, (list, tuple, set)) else (extra,)
        words.update(str(w).lower() for w in blob if w)
    return words


def slug_id(raw: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", (raw or "")).lower()[:48] or "specialist"


def _tokens(text: str) -> set:
    return set(re.findall(r"[a-z0-9]{4,}", (text or "").lower()))


def cap_skills(requested, parent_skills: str) -> str:
    parent = {s.strip() for s in (parent_skills or "").split(",") if s.strip()}
    if isinstance(requested, list):
        asked = [str(s).strip() for s in requested if str(s).strip()]
    else:
        asked = [s.strip() for s in str(requested or "").split(",") if s.strip()]
    allow_risky = os.getenv("AUTO_HIRE_ALLOW_RISKY", "0") == "1"
    kept = []
    for skill in asked:
        if skill in _NEVER or skill not in parent:
            continue
        if skill in _RISKY and not allow_risky:
            continue
        if skill not in kept:
            kept.append(skill)
    return ",".join(kept)


def keyword_gap(query: str, children) -> str | None:
    """Competence token no child covers, or None when someone already can."""
    stop = _stopwords()
    tokens = [
        t for t in re.findall(r"[a-zA-Zа-яё]{5,}", (query or "").lower())
        if t not in stop
    ]
    if not tokens:
        return None
    blob = " ".join(
        f"{c.get('id', '')} {c.get('name', '')} {c.get('system_prompt', '')}"
        for c in (children or [])
    ).lower()
    missing = [t for t in tokens if t not in blob]
    if len(missing) != len(tokens):
        return None
    return max(missing, key=len)


def gap_spec(query: str, gap: str, parent_skills: str) -> dict:
    custom = hook("gap_spec", query, gap, parent_skills, default=None)
    if isinstance(custom, dict) and custom.get("id"):
        return custom
    token = (gap or "specialist").strip()
    sid = slug_id(token)
    name = token[:1].upper() + token[1:] if token.isascii() else token
    skills = [s.strip() for s in (parent_skills or "").split(",") if s.strip()]
    return {
        "id": sid,
        "name": name,
        "mandate": f"Cover {token}. Query: {(query or '')[:200]}",
        "skills": skills,
        "reason": f"No child covers {token}.",
    }


def _find_existing(spec: dict):
    agents = get_all_subagents()
    sid = slug_id(spec.get("id") or spec.get("name") or "")
    for agent in agents:
        if agent["id"] == sid:
            return agent
    name = (spec.get("name") or "").strip().lower()
    if name:
        for agent in agents:
            if (agent.get("name") or "").strip().lower() == name:
                return agent
    mandate = _tokens(spec.get("mandate") or "")
    if not mandate:
        return None
    for agent in agents:
        blob = _tokens(f"{agent.get('name', '')} {agent.get('system_prompt', '')}")
        if blob and len(mandate & blob) / len(mandate) >= 0.6:
            return agent
    return None


def _hires_today(parent_id: str) -> int:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return sum(
        1 for agent in get_all_subagents()
        if agent.get("origin") == "auto"
        and agent.get("parent_id") == parent_id
        and str(agent.get("created_at") or "").startswith(day)
    )


def _layout(parent_id: str) -> tuple:
    siblings = [a for a in get_all_subagents() if a.get("parent_id") == parent_id]
    if siblings:
        return max(a.get("x") or 100 for a in siblings), max(a.get("y") or 100 for a in siblings) + 120
    parent = get_subagent(parent_id) or {}
    return (parent.get("x") or 100) + 350, parent.get("y") or 100


def _model_for(spec: dict, parent_id: str) -> str:
    parent = get_subagent(parent_id) or {}
    fallback = spec.get("model") or parent.get("model") or os.getenv("LLM_MODEL") or "ollama/llama3"
    chosen = spec.get("model") or get_agent_model("specialist", fallback)
    try:
        from backend.llm_model_manager import resolve_provider_model
        chosen = resolve_provider_model(chosen) or chosen
    except (ImportError, AttributeError):
        pass
    return chosen


def ensure_specialist(spec: dict, parent_id: str, parent_skills: str, *, reason: str, origin: str = "auto") -> dict | None:
    """Return an existing matching agent or create one under parent_id."""
    mode = auto_hire_mode()
    if origin == "auto" and mode == "off":
        return None
    if hook("veto_hire", spec, parent_id, default=None):
        return None
    existing = _find_existing(spec)
    if existing:
        borrowed = dict(existing)
        borrowed["reused"] = True
        return borrowed
    limit = int(os.getenv("AUTO_HIRE_MAX_PER_DAY", "10") or "10")
    if origin == "auto" and parent_id and _hires_today(parent_id) >= limit:
        return None
    sid = slug_id(spec.get("id") or spec.get("name") or "specialist")
    skills = cap_skills(spec.get("skills") or "", parent_skills)
    extra = hook("hire_prompt_extra", spec, parent_id, default=None) or ""
    mandate = spec.get("mandate") or reason or "Handle the assigned request."
    name = spec.get("name") or sid
    prompt = (
        f"You are {name}.\n"
        f"Mandate: {mandate}\n"
        "Use tools to fetch data. Do not simulate results you did not retrieve.\n"
        "Stay inside this mandate."
    )
    if extra:
        prompt += "\n" + str(extra)
    x, y = _layout(parent_id) if parent_id else (450, 100)
    hire_reason = (reason or spec.get("reason") or "")[:300]
    save_subagent(
        sid, name, prompt, _model_for(spec, parent_id),
        agent_type="agent", parent_id=parent_id or None, skills=skills,
        x=x, y=y, origin=origin, hire_reason=hire_reason,
    )
    row = get_subagent(sid) or {"id": sid, "name": name, "parent_id": parent_id, "skills": skills, "origin": origin}
    row["reused"] = False
    return row


def hire_with_escalation(spec: dict, start_id: str, stack: tuple) -> dict:
    """Try start_id, then each parent. `stack` stops a parent_id cycle."""
    mode = auto_hire_mode()
    if mode == "off":
        return {"agent": None, "status": "off"}
    seen = tuple(stack)
    current = start_id
    first = True
    while current:
        if not first and current in seen:
            return {"agent": None, "status": "cycle"}
        if not first:
            seen = (*seen, current)
        first = False
        parent = get_subagent(current) or {}
        agent = ensure_specialist(
            spec, current, parent.get("skills") or "", reason=spec.get("reason") or "",
        )
        if agent:
            return {
                "agent": agent,
                "status": "reused" if agent.get("reused") else "created",
                "parent_id": agent.get("parent_id") or current,
            }
        nxt = parent.get("parent_id")
        if not nxt or nxt in seen:
            return {"agent": None, "status": "cycle" if nxt else "limit"}
        current = nxt
    return {"agent": None, "status": "limit"}
