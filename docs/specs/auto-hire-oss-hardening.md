# Auto-hire OSS hardening — spec

Goal: close the gaps the OSS review (2026-10-10) found in the auto-hire change ([auto-hire-specialists.md](auto-hire-specialists.md)). Core stays domain-free, state goes through the database layer, privileges come from explicit fields only. No behaviour change for users who keep the defaults, except `AUTO_HIRE` (see 5).

## Findings

The review passed: no vendor lock-in, every new env var has a default, migrations cover SQLite and Postgres, 261 tests green. These issues remain:

1. **Trading domain in core.** `backend/agent_factory.py` hardcodes trading stopwords (`market`, `trade`, `trading`, `купить`) in `_STOP` and an `options_analyst` / `опцион` special case in `gap_spec`. The same change removed options wording from `backend/bcm/plugin.py`. It moved into core instead of leaving. This breaks the parent spec's "Core, not plugin" principle: a community plugin can't supply its own vocabulary or names.
2. **Raw SQL outside the database layer.** `_materialize_hires` in `backend/orchestrator.py` imports the private `backend.database._execute` and writes `hire_reason` twice. "Awaiting confirmation" is encoded as a `PENDING:` string prefix inside a free-text field. The parent spec asks for a *disabled* agent in `ask` mode. A text prefix is not a state, and nothing else in the codebase (UI, `call_subagent`, router) honours it.
3. **Privilege from a naming convention.** `management_tools_for` in `backend/agent.py` grants `create_subagent` / `list_subagents` / `call_subagent` to any agent whose id ends with `_orchestrator`. An imported or marketplace agent named `foo_orchestrator` with `agent_type="agent"` gets hiring rights.
4. **Duplicated "unused" rule.** The 30-day rule is written twice: in `database.list_unused_auto_agents` and again in `frontend/src/components/NetworkTab.tsx`, with its own timestamp parsing. The two can drift (timezone, Postgres `TIMESTAMP` vs SQLite text).
5. **`AUTO_HIRE=on` by default.** A fresh clone lets the LLM create persistent agents with no confirmation. Skill caps limit the blast radius, but contributors trying the project don't expect silent DB writes.
6. **Small defects.**
   - `_materialize_hires`: `status == "cycle" or (not agent and status == "cycle")` checks the same thing twice.
   - The `hire_with_escalation` docstring mentions `_stack`; the parameter is `stack`.

## Principles

- **Core holds no domain words.** Gap detection is generic. Domain vocabulary and naming arrive through plugin hooks.
- **One owner per table.** Only `backend/database.py` writes SQL. Other modules call named functions.
- **Explicit privilege.** Rights come from `agent_type` (and `skills`), never from id or name patterns.
- **One source of truth.** Business rules are computed on the backend. The UI renders flags.
- **Safe first run.** Defaults that write to persistent state ask first.

## Design

### 1. Plugin hooks for gap vocabulary and naming

`backend/agent_factory.py`:

- `_STOP` keeps only language-generic words (`which`, `please`, `should`, `проверь`, `нужно`, greetings…). Remove `analyze`, `analysis`, `market`, `trade`, `trading`, `verify`, `check`, `купить`.
- New hook `gap_stopwords() -> Iterable[str]`, read with `collect`, so every plugin can contribute:

  ```python
  def _stopwords() -> set:
      words = set(_STOP)
      for extra in collect("gap_stopwords"):
          words.update(str(w).lower() for w in (extra or ()))
      return words
  ```

- `gap_spec` drops the options branch. It first asks plugins:

  ```python
  custom = hook("gap_spec", query, gap, parent_skills, default=None)
  if isinstance(custom, dict) and custom.get("id"):
      return custom
  # generic: slug_id(token), token.capitalize()
  ```

- `backend/bcm/plugin.py` implements both hooks. It returns the trading stopwords, and `{"id": "options_analyst", "name": "Options Analyst", ...}` when the gap token matches `option*` / `опцион*`. The incident replay keeps working with BCM installed, and core no longer knows the word.

### 2. Hire state in the data layer

Migration on `subagents` (SQLite + Postgres, same pattern as `origin`):

| column | type | default | purpose |
|---|---|---|---|
| `hire_status` | TEXT | `'active'` | `active` / `pending` |

New functions in `backend/database.py`:

```python
def set_hire_status(agent_id: str, status: str) -> None: ...   # validates status ∈ {"active", "pending"}
```

- `_subagent_from_row` / `_SUBAGENT_COLUMNS` return `hire_status`.
- `_materialize_hires` calls `set_hire_status(id, "pending")` on create in `ask` mode, and `set_hire_status(id, "active")` on confirmation. No `_execute` import outside `database.py`. `hire_reason` stays plain text.
- The router loop skips a step whose agent has `hire_status == "pending"`. It adds a trace and the "confirm new specialist" line, so a pending agent can't run through a stale plan or `call_subagent`.
- `call_subagent` returns an error for pending agents.
- Confirmation endpoint: `POST /api/subagents/{id}/confirm` → `set_hire_status(id, "active")`. Telegram inline button and UI toast call it. Wiring the UI toast is optional in this change. The endpoint and tests are required.
- One-time data fix in the migration: rows with `hire_reason LIKE 'PENDING:%'` → `hire_status='pending'`, prefix stripped.

### 3. Privilege from `agent_type` only

`backend/agent.py`:

```python
_ORCHESTRATOR_TYPES = ("orchestrator", "sub-orchestrator")

def management_tools_for(subagent: dict) -> set:
    if (subagent or {}).get("agent_type") in _ORCHESTRATOR_TYPES:
        return {"create_subagent", "list_subagents", "call_subagent"}
    return set()
```

- The `web_search` grant at the call site uses the same check.
- Drop the `id.endswith("_orchestrator")` branch everywhere it was added.
- If existing seed/marketplace data relies on the suffix, fix the data: set `agent_type='orchestrator'` in the seed or migration. Don't keep the heuristic.

### 4. "Unused" computed on the backend

- `_subagent_from_row` adds `unused: bool`, computed by one helper `_is_unused_auto(origin, last_used_at, days=30)`. `list_unused_auto_agents` uses the same helper.
- The helper handles both `str` (SQLite) and `datetime` (Postgres) values.
- `NetworkTab.tsx` filters on `a.unused` and removes its own `Date.parse` logic.
- `AUTO_HIRE_UNUSED_DAYS` (default 30) in `.env.example`.

### 5. Default `AUTO_HIRE=ask`

- `.env.example`: `AUTO_HIRE=ask`, with a comment that `on` is the hands-free mode.
- Code default `os.getenv("AUTO_HIRE", "ask")` in `agent_factory.py` and `orchestrator.py`. Read it through one helper `auto_hire_mode()` in `agent_factory.py` so the default lives in one place.
- `docs/guide/getting-started.md`: list `ask` first.
- CHANGELOG under `[Unreleased]`: note the default change.

### 6. Small fixes

- `if status == "cycle":` in `_materialize_hires`.
- `hire_with_escalation` docstring: "`stack` stops a parent_id cycle."

## Tasks

- [x] **1. Domain out of core** — trim `_STOP`; `gap_stopwords` + `gap_spec` hooks; BCM plugin implements them; remove the options branch from `gap_spec`.
- [x] **2. `hire_status`** — migration (SQLite + Postgres, PENDING data fix); `set_hire_status`; getters; `_materialize_hires` without `_execute`; router and `call_subagent` refuse pending; `POST /api/subagents/{id}/confirm`.
- [x] **3. Explicit privilege** — `management_tools_for` and the `web_search` grant use `agent_type` only; fix seed data if needed.
- [x] **4. `unused` flag** — backend helper + field; `NetworkTab.tsx` reads it; `AUTO_HIRE_UNUSED_DAYS`.
- [x] **5. Safe default** — `auto_hire_mode()` defaulting to `ask`; `.env.example`, getting-started, CHANGELOG.
- [x] **6. Small fixes** — duplicate condition, docstring.
- [x] **7. Code map** — `python3 scripts/generate_code_map.py`.

## Tests

Extend `backend/tests/test_auto_hire.py`:

- With no plugin loaded, `gap_spec(q, "options", "")` returns a generic slug (`options`), not `options_analyst`. `keyword_gap` treats `market` as a normal token.
- With a stub plugin returning `gap_spec` / `gap_stopwords`, the plugin result wins and plugin stopwords are skipped.
- BCM plugin: `gap_spec(..., "options", ...)` → `options_analyst` (incident replay still passes).
- `AUTO_HIRE=ask`: a created agent has `hire_status='pending'` and `hire_reason` has no `PENDING:` prefix. The router does not run it. `call_subagent` refuses it. After `POST /api/subagents/{id}/confirm`, it runs.
- Migration: a row with `hire_reason='PENDING: x'` becomes `hire_status='pending'`, `hire_reason='x'`.
- `grep`-style test: no `from backend.database import _execute` outside `backend/database.py` (add to `test_public_hygiene.py`).
- `management_tools_for({"id": "x_orchestrator", "agent_type": "agent"})` → empty set. `{"agent_type": "sub-orchestrator"}` → management tools.
- `unused` is true for `origin='auto'` with `last_used_at=None` or older than N days, false for `manual`. Covered for `str` and `datetime` inputs.
- Unset `AUTO_HIRE` → `ask` behaviour.
- Existing `test_orchestrator.py`, `test_dynamic_subagents.py`, `test_dag_cycle.py`, `test_openrouter_ollama_model.py` stay green.

## Acceptance

- `rg -n "option|опцион|trade|market" backend/agent_factory.py` → no matches.
- `rg -n "_execute" backend --glob '!backend/database.py'` → no imports of the private helper.
- `rg -n "endswith\(\"_orchestrator\"\)" backend` → no matches.
- `NetworkTab.tsx` has no date math for the unused list.
- Fresh clone with defaults: a gap query creates a pending agent and asks for confirmation. Nothing runs until confirmed.
- `backend/.venv/bin/python -m pytest backend/tests/ -q` and `npm --prefix frontend run build` green; `export_oss.sh` dry run: no leaks.

## Out of scope

- Embedding-based dedup (still token overlap, see `ponytail` note in `agent_factory.py`).
- Full UI flow for confirming pending agents beyond the endpoint and an optional toast.
- Changing `AUTO_HIRE_MAX_PER_DAY` semantics.

## Log

- 2026-10-10 — Tasks 1–7 shipped. Default is `ask`. Telegram button and UI toast left unwired; the confirm endpoint is the contract.
