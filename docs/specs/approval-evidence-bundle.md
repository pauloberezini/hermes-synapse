# Approval evidence bundle

Design spec only. No implementation in this change.

## Goal

A human who approves a high-risk tool call must approve the **evidence** that produced the call, not only the call itself.

Today the gate shows the agent, the tool name, and the exact arguments as raw JSON. The reviewer cannot see the planner step, the upstream tool results, or whether those results were truncated. After this work, Approve means: "this action, built on this evidence, may run once."

## Current behavior (verified in code)

### Gate

`execute_tool` in `backend/tools.py` calls `gate_tool(chat_id, name, arguments)` before any tool body. Only `HIGH_RISK_TOOLS` in `backend/governance.py` are gated: `execute_command`, `create_obsidian_note`, `delete_todoist_task`.

`agent_id` is the `chat_id` passed through. Orchestrator-scoped subagents use `{parent_chat_id}_{child_id}` (`orchestrator.py`).

### What the reviewer sees

`ApprovalsModal.tsx` renders `#{id} · {agent_id} → {action_name}`, then `description`, then `payload` in a `<pre>`. `gate_tool` sets `description=action_name`, so the description just repeats the tool name.

The modal is not imported by `App.tsx`. The REST surface exists (`GET /api/governance/approvals`, `GET .../count`, `POST .../{id}/resolve` in `backend/main.py`) and is behind the global Bearer middleware.

### Binding and single-use

`ApprovalQueue.find_latest` compares `agent_id`, `action_name`, and a key-sorted JSON payload (`_payload_key` / `_payload_key_stored`, `sort_keys=True`). It skips `CONSUMED` and scans the newest 20 rows.

On an `APPROVED` match, `gate_tool` calls `ApprovalQueue.consume`, which sets status `CONSUMED`. A later call with the same args creates a new request. Changed args fail the payload compare and also create a new request. A `REJECTED` match is returned as-is; it is not reused.

Covered by `test_high_risk_tool_waits_for_human_then_runs_once` in `backend/tests/test_governance_agent_wiring.py`.

### Planner traces exist, but are not linked

`AgentState.traces` (`orchestrator.py`) records Planning / Route / Finish (and PulseEngine steps). Each trace is `{timestamp, agent, action, message, status, token_cost}`. Live traces are broadcast as websocket `trace_update`. After the turn finishes, `JarvisAgent.respond` / `_respond_as_subagent` write them to `decision_logs.traces` via `save_decision_log`. Per-step outputs go to `decision_logs` with `tool_calls_log` (result capped at 600 chars) and optional `parent_message_id`.

`approval_requests` has no FK, no session column beyond `agent_id`, and no bundle columns (`database.py` SQLite and Postgres schemas). `gate_tool` does not receive a plan step, prior results, or a decision-log id.

### Why review-time lookup cannot see the current step

`save_decision_log` runs after the turn completes. `gate_tool` fires **during** the turn, before the gated tool runs. At request time the current planner step and in-flight tool results live in `AgentState` / the ReAct `messages` list, not in `decision_logs`. Prior completed turns are in `decision_logs`; prior orchestrator steps are in `state.results` (compressed by `compress_step_context` at 3000 chars with `...[truncated output]` / `...[truncated long step report]`).

PDF ingest already returns `{pages, truncated}` (`POST /api/parse-pdf`, 500 KB cap). Those flags never reach the approval row.

## What the bundle contains

One immutable snapshot attached to the request:

| Field | Source at request time | Notes |
| --- | --- | --- |
| `description` | Generated, not `action_name` | One or two sentences: who, which tool, which plan step, why. |
| `plan` | `AgentState.steps[current_step_idx]` plus the matching Planning / Route traces | Agent id, instructions, step index, step count. Empty for a non-orchestrated ReAct call. |
| `inputs` | The gated tool's `arguments` (already stored as `payload`) plus the step context string the agent was given | Same object the payload-key compare uses. |
| `upstream` | Prior `state.results` and/or earlier `tool_calls_log` / ReAct `role=tool` messages for this session | Each item: tool or step name, content excerpt, `sha256` of the full redacted body, `truncated` flag, optional `reason` (char cap, token budget, PDF page stop). |
| `flags` | Derived | e.g. `read_stopped_before_last_page`, `step_output_truncated`, `tool_result_capped_600`. |
| `links` | Optional pointers | `session_id` (`chat_id`), `parent_message_id` from `_call_context`, latest persisted `decision_logs.id` if one exists. Pointers are hints; the snapshot is the source of truth. |

Missing context is explicit (`plan: null`, `upstream: []`, flags set). Do not invent a plan step for a direct `execute_tool` call.

## Design choice: snapshot at request creation

**Recommend: snapshot when `gate_tool` inserts the row. Do not resolve evidence at review time.**

| | Snapshot at request | Resolve at review |
| --- | --- | --- |
| Integrity | Reviewer sees exactly what the agent had when it asked. Bundle hash can join the approved unit. | Sources can change (note edited, feed refreshed, later tool overwrites `decision_logs`). TOCTOU. |
| Staleness | Frozen on purpose. If the world moved, that is a new request. | Fresher data, but it is not the data that produced the args. |
| Current-turn traces | Can copy in-memory `AgentState` / messages via a contextvar. | Those traces are not in `decision_logs` yet, so the plan step that led to the call is missing. |
| Storage | Pay the cost once, with size caps and hashes of omitted tails. | Cheaper (pointers only), but the interesting bytes are the in-flight ones that pointers cannot reach. |

Review-time fetch is allowed only as a **display hint** (link to Logs / SubagentTreeDrawer). It must not replace the stored bundle, and it must not be part of the approved hash.

## Data model

Keep `approval_requests` as the queue row. Store the bundle in a 1:1 sibling so `get_pending` / `get_all` stay small:

```
approval_evidence
  request_id     INTEGER PRIMARY KEY  -- FK approval_requests.id
  bundle_json    TEXT NOT NULL        -- redacted snapshot
  bundle_hash    TEXT NOT NULL        -- sha256 of canonical JSON (sort_keys, ensure_ascii=False)
  created_at     TEXT NOT NULL
```

Add nullable columns on `approval_requests` only if list/filter needs them without a join: `bundle_hash TEXT`, `session_id TEXT`. Do not put the full JSON on the list row.

Canonical hash input is the redacted bundle **minus** volatile display-only fields. Include `plan`, `inputs`, `upstream[].sha256`, `upstream[].truncated`, and `flags`. Exclude raw excerpts from the hash if they are already covered by `sha256` (keeps the hash stable if a later UI recuts the excerpt).

Size caps (starting point, tune in implementation):

- Per upstream excerpt: 4 KiB (full body hashed, tail dropped, `truncated=true`).
- Whole `bundle_json`: 64 KiB after redaction.
- If still over: drop oldest upstream excerpts first; keep their hashes and flags.

SQLite and Postgres `init_db` paths both need the table (same split as today's `approval_requests`).

## API

Existing routes stay. Additive only.

- `GET /api/governance/approvals` and `get_pending` / `get_all`: each item gains `bundle_hash`, `description` (the generated sentence), and a short `flags` list. Not the full JSON.
- `GET /api/governance/approvals/{id}` (new): full redacted bundle plus the existing request fields. Modal uses this when a row is expanded.
- `POST /api/governance/approvals/{id}/resolve`: unchanged body. Server records that the stored `bundle_hash` was part of the decision. Do not accept a client-supplied bundle.

`gate_tool` / `request_approval` grow an optional `bundle` (or build it internally from a contextvar). `description` is the generated sentence, not `action_name`.

Auth stays on the global `/api/*` Bearer middleware. No new public route.

## Binding to the existing single-use gate

The approved unit becomes:

```
(agent_id, action_name, payload_key, bundle_hash)
```

`payload_key` remains key-sorted JSON of the tool arguments. That keeps today's contract: changed args need a new approval.

`bundle_hash` is stored on insert and is immutable. `find_latest` still keys on payload so an identical retry while `PENDING` or `APPROVED` reuses the same row (same snapshot). After `CONSUMED`, a new row is created and a new snapshot is taken.

If capture is incomplete (no plan context), hash that incomplete bundle anyway. Do not silently refresh it later; that would unbind what the human approved.

`consume` is unchanged: one `APPROVED` row authorizes one `execute_tool` run.

## UI (`ApprovalsModal`)

Claim-next-to-source: the claim and the evidence sit on one row, not a JSON dump above a mystery description.

1. **Claim** (left or top): agent, tool, human `description`, formatted args (pretty JSON is fine). Status badge stays.
2. **Source** (right or immediately below): plan step (agent + instructions + index), then upstream items with name, excerpt, content hash, and truncation chips (`truncated`, `read stopped before the last page`, `tool result capped at 600 chars`).
3. Empty source: show "No planner step attached" / "No upstream results" rather than hiding the panel.
4. Mount the modal from `App.tsx` (header or Task Engine) with the existing `/api/governance/approvals/count` badge. Today the component is orphaned.

Resolver note and Approve / Reject stay as they are. Approving without expanding the source is allowed; the stored hash still binds the evidence.

## Security and redaction

Bundles are operator-visible and persisted. Treat them as untrusted agent output.

- Run `PIIGuard.mask_pii` (`governance.py`) on every string before persist and before the GET-by-id response: emails, phones, `sk-` / `gh*_` keys, bearer tokens, cards, SSN.
- Run `MemoryGuard.audit_text` on upstream excerpts from web/upload sources; keep the `clean_text`, record a flag if threats were stripped.
- Redact the displayed `payload` with the same pass (a command string can embed a token).
- Do not store raw env values or auth headers.
- Caps above are also an exfil brake: the hash proves completeness without shipping the whole scrape.

The review UI is already authenticated. Do not add an unauthenticated bundle URL.

## Phased rollout

1. **Schema + capture stub.** Create `approval_evidence`. `gate_tool` writes a bundle with `description`, `inputs` (= payload), empty `plan` / `upstream`, and `bundle_hash`. Existing payload-only tests stay green.
2. **API + modal.** GET-by-id, list summaries, claim-next-to-source layout, mount in `App.tsx`. `description` stops repeating the tool name.
3. **In-flight context.** Contextvar (same pattern as `_call_context.parent_message_id` in `backend/tools.py`) set by `run_orchestration` / `_respond_as_subagent` so `gate_tool` can snapshot the current step, recent traces, and prior tool results. Include truncation flags from `compress_step_context` and PDF `{pages, truncated}`.
4. **Bind `bundle_hash`.** Include it on the request row and in API responses. Keep `find_latest` payload-keyed; document the approved unit as payload + hash.
5. **Tests.** Extend `test_governance_agent_wiring.py`: pending request has a hash; consume is still single-use; changed args new request; PII does not appear in `bundle_json`; truncated upstream sets the flag.

Out of scope for v1: changing `HIGH_RISK_TOOLS`, Telegram approval, plugin-defined risk tools.

## Open questions

1. How far back should `upstream` go? Last N tool results in this session, or only prior steps in the current `AgentState.results`? Recommendation: current-plan `state.results` plus the current ReAct turn's tool messages. Not the whole session history.
2. Should a later `decision_logs` row (written after the turn) be back-linked onto the evidence row for Logs navigation, without changing `bundle_hash`? Lean yes, as a pointer only.
3. Retention: delete `bundle_json` for `CONSUMED` / `REJECTED` after N days, keep `bundle_hash`? Needed once volume is real; not a v1 blocker.
4. If contextvar is unset (direct `execute_tool` in tests or a plugin), is an inputs-only bundle acceptable? Yes; flags should say `plan_missing`.
5. Should Approve be disabled until the source panel has been opened once? Recommendation: no. The hash binds regardless. Optional later.

## Acceptance (when implemented)

- Reviewer sees the plan step and upstream excerpts next to the tool args.
- Truncation / partial-read is visible, not silent.
- Approval remains payload-bound and single-use (`CONSUMED` after one run).
- The stored `bundle_hash` is what was shown (redacted snapshot), not a live lookup.
- Secrets match `PIIGuard` tokens in stored and served bundles.
- `docs/specs/bcm-*` style private plugins stay out of this public spec (`export_oss.sh` already excludes those paths).
