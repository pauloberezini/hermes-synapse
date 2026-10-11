# Auto-hire missing specialists — spec

Goal: when no existing agent covers a request, the core creates the specialist on the spot, wires it into the DAG and runs it in the same turn. No "create an agent" phrase from the user. The core stops acting only as a dispatcher for a fixed staff and starts adding to that staff.

## Incident (2026-10-10)

An options-chain request (AAPL calls) arrived over Telegram, session `216199859`.

1. **Routing skipped the root.** The session is bound to a domain sub-orchestrator through `get_session_agent_id`, so `run_orchestrator` started there. The root orchestrator never saw the message.
2. **No options specialist anywhere.** Root children: domain orchestrator, monitor, `knowledge_curator`, `quantum_stock_mcp`, `secretary`, `sports_analyst`. The domain orchestrator's children: quant, trading engine, risk, compliance, fundamental, macro, energy desks. None of them handles options.
3. **The planner can't create anyone.** `backend/orchestrator.py` builds the planner prompt from `children` only. It rejects any step whose `agent` is not an existing id (`allowed_agent_ids`, L365/L427). Hiring isn't part of the plan schema.
4. **`create_subagent` is out of reach.**
   - It runs only when the user explicitly asks for it (prompt rule in `backend/agent.py` L380).
   - `TOOL_SKILL_MAP` maps it to `agent_management` (`backend/database.py` L1712). No node has that skill, so any agent with an explicit `skills` list never sees the tool.
   - `create_subagent()` (`backend/tools.py` L1537) can't set `parent_id` or `skills`. Even when it runs, the new agent is orphaned and outside the DAG.
5. **The fallback hid the gap.** The planner LLM call failed inside `resolve_provider_model`. The plugin hook `fallback_plan_steps` then substituted the canonical 4-agent pipeline (quant → engine → risk → compliance) and appended the options wording to their instructions. Result: a spot `WAIT` verdict on AAPL presented as an options answer.

## Principles

- **Core, not plugin.** Gap detection and hiring live in core. Plugins can only shape it: veto, templates, extra rules.
- **Reuse before create.** Search the whole agent registry first, not only the direct children.
- **Least privilege.** A hired agent gets at most the parent's `active_skills`. It never escalates privileges.
- **Provider-agnostic.** The hired agent's model is picked with `get_agent_model` / `resolve_provider_model`, so it works with Ollama or any LiteLLM provider. No hardcoded vendor.
- **Honest output.** If no specialist exists and none can be hired, the reply says so. It never passes off another agent's answer as the specialist's.

## Design

### 1. Plan schema: `hire`

The planner may return new specialists next to the steps:

```json
{
  "hire": [
    {
      "id": "options_analyst",
      "name": "Options Analyst",
      "mandate": "Analyse option chains: IV, Greeks, skew, defined-risk spreads.",
      "skills": ["market_monitor", "web_search"],
      "reason": "No child covers options-chain analysis."
    }
  ],
  "steps": [
    {"agent": "options_analyst", "instructions": "..."}
  ]
}
```

- Validation accepts a step `agent` if it is an existing id **or** an id declared in `hire`.
- Planner prompt rule: "If no available sub-agent has the required competence, declare it in `hire` instead of forcing the task onto an unrelated agent."
- `hire` holds at most `AUTO_HIRE_MAX_PER_TURN` entries (default 1).

### 2. `backend/agent_factory.py` (new)

```python
def ensure_specialist(spec: dict, parent_id: str, parent_skills: str, *, reason: str) -> dict:
    """Return an existing matching agent or create one under parent_id."""
```

Steps:
1. **Normalize** the id: same slug rules as `create_subagent`.
2. **Dedup**, in order:
   - exact id;
   - case-insensitive name match;
   - mandate similarity against the `name` + `system_prompt` of every agent (token overlap; optional embeddings via `backend/rag.py` when it is available).

   A match under a different parent is **borrowed**: the step runs it with the current parent's skill cap. It is not cloned or re-parented.
3. **Skill cap**: `skills = requested ∩ parent_active_skills`. Never grant `agent_management`. Skills on the governance high-risk list (order execution, shell) are dropped unless `AUTO_HIRE_ALLOW_RISKY=1`.
4. **Prompt**: build `system_prompt` from `mandate` and a core template (role, boundaries, "use tools, don't simulate"). Plugins can extend it via the `hire_prompt_extra(spec, parent_id)` hook.
5. **Model**: `get_agent_model("specialist", parent.model)` → `resolve_provider_model`. Fall back to the parent's model.
6. **Persist**: `save_subagent(..., parent_id=parent_id, skills=..., agent_type="agent")` plus the new columns (see 4). Lay it out on the canvas next to its siblings (`x`, `y`).
7. **Rate limit**: `AUTO_HIRE_MAX_PER_DAY` (default 10). Over the limit, return `None` and the caller reports the gap.

### 3. Orchestrator flow (`run_orchestrator`)

```
plan → validate (existing ids ∪ hire ids)
     → for each hire: ensure_specialist(...)   # before the router loop
     → trace "🧩 Hired <name> under <orch>" / "♻️ Reused <id>"
     → router loop (unchanged)
```

- **Fallback order fix.** When the planner fails (an exception, not empty steps):
  1. Run a lightweight **gap check**: a single LLM call with the same provider chain, or a keyword fallback if that call also fails. It asks whether any child covers the query.
  2. Gap found → `ensure_specialist` from a minimal spec, then a one-step plan with the new agent.
  3. Only if there is no gap → `fallback_plan_steps` hook.
- `fallback_plan_steps` gets a new kwarg `gap: Optional[str]`. Plugins must return `None` when `gap` is set. They must not stuff out-of-scope intents into their canonical pipeline. The current options wording in the trading plugin hook is removed.
- **Planner crash root cause**: the `resolve_provider_model` failure on the planner path gets its own fix and regression test. Hiring must not rely on the planner being healthy, but the planner must not crash either.

### 4. Data model

Migration on `subagents`:

| column | type | default | purpose |
|---|---|---|---|
| `origin` | TEXT | `'manual'` | `manual` / `auto` |
| `hire_reason` | TEXT | `''` | planner `reason` + source query (truncated) |
| `last_used_at` | TIMESTAMP | NULL | updated by the router loop |

Both SQLite and Postgres branches in `database.py`. `get_all_subagents` / `get_subagent` return the new fields.

### 5. Session binding and escalation

A session bound to a sub-orchestrator (Telegram `set_session_agent`) still hires **under that orchestrator**. The bound orchestrator owns the conversation.

If the bound orchestrator can't hire (rate limit, or a plugin `veto_hire` hook returns a reason), it escalates once to `parent_id` (up to the root). The DAG `_stack` guard prevents cycles. If the root can't hire either, it replies with an explicit "no specialist for X" message.

### 6. Tool access (manual path)

- Agents with `agent_type == "orchestrator"` always get `agent_management` and `agent_delegation` in their effective skill set.
- `create_subagent` gains optional `parent_id` and `skills` and routes through `ensure_specialist`, so manual and automatic creation share dedup and caps.

### 7. Config (`.env.example` + getting-started)

```
AUTO_HIRE=on            # on | ask | off
AUTO_HIRE_MAX_PER_TURN=1
AUTO_HIRE_MAX_PER_DAY=10
AUTO_HIRE_ALLOW_RISKY=0
```

`ask`: the agent is created in a disabled state. The reply asks the user to confirm, via Telegram inline button or UI toast. `off`: the gap is reported, nothing is created.

### 8. Visibility

- A trace entry and one line in the final reply: `🧩 New specialist: Options Analyst (options_analyst) → <parent>`.
- The canvas shows an `auto` badge on hired nodes. Unused auto agents (no `last_used_at` within 30 days) are listed for cleanup. They are never deleted automatically.

## Tasks

- [x] **1. Planner crash** — reproduce the `resolve_provider_model` failure on the planner path, fix it, add a regression test in `test_openrouter_ollama_model.py`.
- [x] **2. Migration** — `origin`, `hire_reason`, `last_used_at` (SQLite + Postgres); getters return them.
- [x] **3. `agent_factory.ensure_specialist`** — dedup, skill cap, model resolution, rate limit, plugin hooks `hire_prompt_extra` / `veto_hire`.
- [x] **4. Plan schema** — `hire` in the prompt and validation; resolve hires before the router loop; traces.
- [x] **5. Fallback order** — gap check before `fallback_plan_steps`; `gap` kwarg; remove options stuffing from the plugin hook.
- [x] **6. Escalation** — bound orchestrator → parent → root when hiring is blocked; explicit "no specialist" reply.
- [x] **7. Manual path** — `create_subagent(parent_id, skills)` routes through the factory; orchestrators always get `agent_management`.
- [x] **8. Config & docs** — `.env.example`, `docs/guide/getting-started.md`, CHANGELOG entry.
- [x] **9. UI** — `auto` badge and unused-agents list (can ship after 1–8).

## Tests (`backend/tests/test_auto_hire.py`)

- Planner returns a `hire` plus a step on that id → the agent is created with `parent_id=orch_id`, `origin='auto'`, and the step runs.
- A second identical query → no new row; the existing agent is reused.
- Requested skills outside the parent's `active_skills` are stripped; `agent_management` is never granted.
- The planner raises → a gap is detected → the specialist is hired, and the plugin `fallback_plan_steps` is **not** called.
- The planner raises, no gap → `fallback_plan_steps` is called as before.
- `AUTO_HIRE=off` → no row created; the reply states the missing competence.
- Rate limit reached in the bound orchestrator → escalates to the parent; a cycle in `parent_id` is caught by `_stack`.
- `create_subagent(..., parent_id=..., skills=...)` goes through dedup and caps.
- Existing `test_orchestrator.py`, `test_dynamic_subagents.py` and `test_dag_cycle.py` stay green.

## Acceptance

- Replay of the incident: "AAPL options, which calls to buy" in session `216199859`.
  - An `options_analyst` (or reused equivalent) appears under the bound orchestrator.
  - The reply analyses the option chain (IV, Greeks, strikes/expiries), not a spot verdict.
  - The reply contains the "New specialist" line.
- The same query again → no duplicate agent.
- Planner outage does not produce out-of-scope pipeline answers.
- Works with `LLM_MODEL=ollama/...` and no cloud keys.
- `pytest backend/tests/ -q` and `npm --prefix frontend run build` green; `export_oss.sh` dry run: no leaks.

## Out of scope

- Auto-deleting agents.
- Hiring agents that need new tools or MCP servers which aren't installed (the gap is reported; installing is a separate flow).
- Multi-agent team hiring in one turn (`AUTO_HIRE_MAX_PER_TURN > 1` is allowed but not tuned).

## Log

- 2026-10-10 — Tasks 1–9 shipped. OSS review follow-ups tracked in [auto-hire-oss-hardening.md](auto-hire-oss-hardening.md).
