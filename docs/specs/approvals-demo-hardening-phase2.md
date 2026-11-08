# Approvals Demo Hardening, Phase 2 — Spec

**Status:** G1–G4, G6, G8, G9 implemented (PR #14, PR #15; public `main` `f4f92d5`). G5 and G7 declined in §1. Everything still open from `FIX-SPEC-demo-v3.md` is in **§6**.
**Date:** 2026-10-29 (reviewed against code the same day)
**Scope:** Close the items from `FIX-SPEC-demo.md` that Phase 1 did not fix, plus two honest corrections to Phase 1's own claims.
**Related precedent:** `docs/specs/approvals-demo-hardening.md` (Phase 1, merged in PR #13), `docs/specs/roadmap/phase-1-approval-context.md`, `docs/guide/approvals.md`

### Implementation status (code review)

| Item | Verdict | Evidence in the tree |
|---|---|---|
| G1 `export.zip` alias | Done | `backend/main.py:966` |
| G2 one broadcast, `onResolved` fallback | Done | route has no `manager.broadcast`; queue emits at `governance.py:424`; `App.tsx:2134` |
| G3 agent name, session stays the key | Done | `agent_name_ctx` `agent.py:22`; `links.agent` `governance.py:701:709`; `agent_name` in read paths `governance.py:458, 493, 524` |
| G4 direct-route evidence | Done | `agent.py:30:51` sets the 1/1 plan and `direct_route` |
| G5 auto-resume | **Open** (Option C, retry step documented) | see R2-1 |
| G6 evidence guard, in-DB verify, `--pin` | Done, plus R1-1 `evidence missing` | trigger `database.py:318, 338`; `decision_log.py:212:218`; `scripts/verify_decision_log.py` |
| G7 sticky `REJECTED` | **Open** (declined, no TTL) | `governance.py:694` |
| G8 collapsed badge | Done | `ApprovalsBadge.tsx:58` |
| G9 `VERIFY.md` and guide | Done | `decision_log.py` `_VERIFY_MD`; `docs/guide/approvals.md:100:142` |
| `FIX-SPEC-demo-v3` R0-1 sync | Code done; **tag and demo deploy open** | `scripts/export_oss.sh` dry run: "nothing to publish (in sync with main)". Latest tag is still `v1.4.3` (`d49ebfc`, 2026-10-11), older than the fixes |

---

## 1. Context & Objective

### Trigger point / Problem

Phase 1 fixed payload masking, the worker-thread broadcast, the `CONSUMED` colour, and the false guide claims. A line-by-line review of `FIX-SPEC-demo.md` against `main` shows nine items still open. Each is traced to code below.

| # | Source item | Symptom today | Root cause |
|---|---|---|---|
| G1 | P0-1 | `GET /api/governance/decisions/export.zip` returns 404; the curl example has no `-f`, so an error body is saved as `.zip` | No route at that path. Only `/export` exists (`backend/main.py:965`) |
| G2 | P1-1 (rest) | `APPROVED` is broadcast twice. The modal is mounted without `onResolved` | `ApprovalQueue.resolve` broadcasts, and so does the route (`backend/main.py:998:1006`). `App.tsx:2131:2134` passes no callback |
| G3 | P1-2 | CLAIM shows the session id (`dashboard`, `demo_orch_sysops`), not the agent | `gate_tool(chat_id, ...)` receives the session id as `agent_id` |
| G4 | P1-3 | A direct chat has `plan: null` and SOURCE says "No planner step attached" | `evidence_ctx` is set only on the orchestrator custom-sub-agent path (`backend/orchestrator.py:658:674`) |
| G5 | P1-4 | Nothing runs after Approve until the operator re-sends | `gate_tool` is retry-based; no continuation state exists |
| G6 | P1-5 | Tail truncation plus a rewritten `manifest.json` verifies; editing an `approval_evidence` row leaves `/decisions/verify` at `ok:true` | The manifest is unsigned; `approval_evidence` has no guard; `verify()` checks only the hash chain |
| G7 | P2-1 | A rejected call is blocked for ever in the same session | `gate_tool` returns the `REJECTED` row with no expiry |
| G8 | P2-2 | The count pill is clipped in the collapsed sidebar | The sidebar is `68px` with `overflow: hidden`; the badge renders a plain `<span>Approvals</span>` instead of a `sidebar-label` |
| G9 | P2-3 | Export `VERIFY.md` names a script that is not in the zip; the guide omits three facts | Text in `_VERIFY_MD`; guide gaps |

**G3 — the agent identity is the match key.** `gate_tool` keys the same-call lookup on `agent_id`, and that value is the session id:

```1926:1929:backend/tools.py
    from backend.governance import gate_tool
    blocked = gate_tool(chat_id, name, arguments or {})
    if blocked is not None:
        return blocked
```

The orchestrator builds a scoped session per step, so two sessions never share an approval:

```733:737:backend/orchestrator.py
                    scoped_subagent_session_id = f"{state.chat_id}_{child_agent['id']}"
                    subagent_kwargs = {
                        "parent_skills": step.get("skill_cap") if step.get("skill_cap") is not None else (None if parent_skills is None else active_skills),
                        "chat_id": scoped_subagent_session_id,
                    }
```

That scoping is a security property: an approval granted in one chat cannot be spent in another. `FIX-SPEC-demo.md` suggests passing the sub-agent id as `agent_id`. That would widen the match to every session that uses the same agent, so this spec does **not** do that. The key stays the session. The agent name is carried separately for display.

**G4 — where the direct route runs.** Tool dispatch happens in two places in `backend/agent.py`: `respond()` (default agent, dispatch at line 1262) and `_respond_as_subagent()` (dispatch at line 2434). Both reach `_dispatch_execute_tool_async`, which runs `execute_tool` in a worker thread via `asyncio.to_thread` (`backend/agent.py:39:68`). A `ContextVar` set before that call is visible in the thread, which is how `evidence_ctx` already works.

**G6 — what verification can and cannot prove.** `verify()` walks `approval_decisions` only:

```148:167:backend/decision_log.py
def verify(tenant_id: str = "default") -> VerifyResult:
    """Recompute the chain. The first broken seq fails the walk."""
    from backend.database import _execute

    placeholders = ", ".join(_COLUMNS)
    rows = _execute(
        f"SELECT {placeholders} FROM approval_decisions WHERE tenant_id = ? ORDER BY seq",
        (tenant_id,),
    )
    prev = GENESIS
    for raw in rows:
        row = dict(zip(_COLUMNS, raw))
        seq = int(row["seq"])
        if row["prev_hash"] != prev:
            return VerifyResult(False, 0, seq, "prev_hash mismatch", "")
        digest = entry_hash(row)
        if row["entry_hash"] != digest:
            return VerifyResult(False, 0, seq, "entry_hash mismatch", "")
        prev = digest
    return VerifyResult(True, len(rows), None, "", prev if rows else "")
```

It never reads `approval_evidence`. The offline script does check each bundle hash. The chain guard is a pair of triggers; `approval_evidence` has none:

```299:312:backend/database.py
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS approval_decisions_no_update
        BEFORE UPDATE ON approval_decisions
        BEGIN
            SELECT RAISE(ABORT, 'approval_decisions is append-only');
        END
    """)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS approval_decisions_no_delete
        BEFORE DELETE ON approval_decisions
        BEGIN
            SELECT RAISE(ABORT, 'approval_decisions is append-only');
        END
    """)
```

### Corrections to Phase 1 and to the review

| Claim made earlier | Truth |
|---|---|
| "`broadcast_sync` records the loop at the first connect, not at startup, so an early broadcast is dropped" | Not a gap. With zero clients `ConnectionManager.broadcast` returns early anyway, and a client that connects later loads state by fetch. No startup hook is needed. `FIX-SPEC-demo.md` item P1-1.1 asked for one; this spec declines it. |
| "`onResolved` missing is a P1 gap" | Minor. The badge already refreshes from the WebSocket event. `onResolved` only matters when the socket is down. It is kept as a one-line fallback. |
| Phase 1 acceptance: "exactly one event per transition" | Not met: `APPROVED` is sent twice (G2). |

### Objective

- `export.zip` works, and following the guide verbatim exits 0.
- One WebSocket event per transition; the badge also moves with the socket down.
- CLAIM shows the agent name; the match key stays the session.
- SOURCE is never empty, and a reviewer can tell when no planner chose the step.
- A truncated export is detectable, and an edited evidence row is rejected and detected.
- Every guide claim is true again.

### Explicit scope decisions (please confirm before implementation)

| Decision | Rationale |
|---|---|
| Add a `/export.zip` alias that calls the same handler. | One decorator. Old links and the original guide keep working. Phase 1 chose docs-only; the alias costs less than a support question. |
| Remove the route's own `APPROVED` broadcast; keep the one in `ApprovalQueue.resolve`. | The queue is the single place every transition already emits from (`REQUESTED`, `CONSUMED`). `resolve` is called inside the request loop, so its event is delivered. |
| Keep `agent_id` as the session-scoped match key. Show the agent via `bundle.links.agent`, returned as `agent_name` in the list and detail responses. | Preserves per-session approval scope. `links` is already excluded from the bundle hash, so no hash change. No schema change. |
| Set the agent name and a direct-route evidence context with `ContextVar`s, in the two agent entry points. Do not touch `gate_tool`'s signature. | `ContextVar` already carries `evidence_ctx` into the worker thread. `gate_tool` stays callable from tests with no context. |
| Direct route gets a one-step plan and the flag `direct_route`, not `plan_missing`. | SOURCE shows the user's instruction. The flag tells the reviewer no planner chose the step, instead of looking like missing data. |
| Do not gate `CodeAgent`. Document it. | Unchanged from Phase 1. Gating the sandbox is a product decision. |
| **Do not sign the manifest.** Add `--pin <entry_hash>` to the offline verifier. | A stdlib-only verifier cannot check an asymmetric signature (no Ed25519 in the standard library). HMAC needs a shared secret, which defeats third-party verification. A pinned `entry_hash` that must appear in the chain detects tail truncation with zero crypto and zero dependencies. |
| Add an `UPDATE` trigger on `approval_evidence`. Do **not** add a `DELETE` trigger. | A delete trigger also blocks the `ON DELETE CASCADE` from `approval_requests`, which tests and operators rely on for cleanup (`backend/database.py:749`). Deleted evidence is already caught: the verifier reports `evidence missing`. |
| `verify()` recomputes each evidence bundle hash. | Closes the in-database blind spot. Reuses `backend.evidence.bundle_hash`. |
| No `REJECTED` TTL. Document it. | In a new session the same call already opens a new request, because the match key is the session. Within one session, "a human said no" staying final stops a model from re-asking. Add a TTL only when a customer asks. |
| Auto-resume stays out of the ordered steps. See the Open Question. | It needs a product choice, and persisted continuation state or a replay path. |
| Do not fix OTP/Telegram or in-memory login sessions here. | Auth concerns, not approvals. Listed under known constraints. |

### Scope

**In scope**
- `backend/main.py` (alias route, remove duplicate broadcast)
- `backend/agent.py` (agent name and direct-route evidence context)
- `backend/governance.py` (`agent_name` in read paths)
- `backend/decision_log.py` (`verify()` evidence check, `VERIFY.md` text)
- `backend/database.py` (evidence `UPDATE` trigger, SQLite and Postgres)
- `scripts/verify_decision_log.py` (`--pin`)
- `frontend/src/App.tsx`, `ApprovalsBadge.tsx`, `ApprovalsModal.tsx`
- `docs/guide/approvals.md`
- Tests for each item

**Out of scope** (for Phase 2; the open ones are picked up in §6)
- Signing or encrypting exports
- Auto-resume (pending the Open Question)
- Gating `CodeAgent`
- A `REJECTED` TTL
- OTP delivery, persistent login sessions
- Secrets at rest in `approval_requests.payload`

---

## 2. Architecture Diagram

See [`approvals-demo-hardening-phase2.dot`](./approvals-demo-hardening-phase2.dot) for the Graphviz source.

```dot
digraph ApprovalsHardeningPhase2 {
  graph [fontname="Helvetica" rankdir=LR splines=ortho]
  node  [fontname="Helvetica" shape=box style=rounded]
  edge  [fontname="Helvetica"]

  subgraph cluster_frontend {
    label="Frontend (React)" style=dashed color=gray
    UI_app    [label="App.tsx\n(changed: onResolved fallback)"]
    UI_badge  [label="ApprovalsBadge\n(changed: icon + count when collapsed)"]
    UI_modal  [label="ApprovalsModal\n(changed: shows agent_name)"]
  }

  subgraph cluster_agents {
    label="Agent runtime" style=dashed color=purple
    AG_resp   [label="respond()\n(changed: sets context)" shape=component]
    AG_sub    [label="_respond_as_subagent()\n(changed: sets context)" shape=component]
    AG_ctx    [label="ContextVars\nagent name, evidence_ctx" shape=component]
    AG_orch   [label="Orchestrator\nsets evidence_ctx (unchanged)" shape=component]
    AG_thread [label="asyncio.to_thread" shape=component]
  }

  subgraph cluster_api {
    label="FastAPI (/api/governance/*)" style=dashed color=steelblue
    EP_list   [label="GET approvals\nGET approvals/{id}\n(changed: agent_name)" shape=component]
    EP_res    [label="POST approvals/{id}/resolve\n(changed: no own broadcast)" shape=component]
    EP_exp    [label="GET decisions/export\n(+ alias export.zip)" shape=component]
    EP_ver    [label="GET decisions/verify\n(changed: checks evidence)" shape=component]
  }

  subgraph cluster_gov {
    label="Governance core" style=dashed color=darkgreen
    GV_gate   [label="gate_tool\n(unchanged signature)" shape=component]
    GV_queue  [label="ApprovalQueue\nsole broadcaster" shape=component]
    GV_log    [label="decision_log\nverify + export_zip" shape=component]
  }

  subgraph cluster_db {
    label="SQLite / Postgres" style=dashed color="#336699"
    T_req [shape=record, label="{ approval_requests | agent_id (session key) | payload (raw) }"]
    T_ev  [shape=record, label="{ approval_evidence | bundle_json | (new: UPDATE trigger) }"]
    T_dec [shape=record, label="{ approval_decisions | entry_hash | prev_hash }"]
  }

  subgraph cluster_tools {
    label="Offline + docs" style=dashed color=darkorange
    SC_ver  [label="scripts/verify_decision_log.py\n(changed: --pin)"]
    DOC     [label="docs/guide/approvals.md\n(changed)"]
  }

  AG_resp -> AG_ctx
  AG_sub -> AG_ctx
  AG_orch -> AG_sub
  AG_ctx -> AG_thread -> GV_gate
  GV_gate -> GV_queue
  GV_queue -> T_req
  GV_queue -> T_ev
  GV_queue -> T_dec
  GV_queue -> UI_app [label="approval_update (once)"]
  UI_app -> UI_badge
  UI_modal -> EP_res -> GV_queue
  UI_modal -> EP_list -> T_req
  EP_list -> T_ev [label="links.agent"]
  EP_ver -> GV_log
  GV_log -> T_dec
  GV_log -> T_ev [label="recompute bundle hash"]
  EP_exp -> GV_log
  SC_ver -> EP_exp [style=dotted label="export zip"]
  DOC -> EP_exp [style=dotted]
  DOC -> SC_ver [style=dotted]
}
```

### Data flow summary

```
Request (fixed):
  respond() / _respond_as_subagent()
    -> set agent-name ContextVar; if evidence_ctx is empty, set a 1/1 plan from the user message
       + flag direct_route
    -> asyncio.to_thread(execute_tool) -> gate_tool(session_id, ...)   [match key unchanged]
    -> build_bundle -> redact_bundle -> bundle.links.agent = name
    -> request_approval -> approval_requests (raw), approval_evidence (masked), REQUESTED
    -> broadcast_sync("approval_update", PENDING)    [one event]

Review:
  GET approvals[/{id}] -> masked payload + agent_name (from bundle.links.agent)
    -> modal CLAIM: "Sys Ops" + session id; SOURCE: plan (planner or direct_route)

Approve:
  POST .../resolve -> ApprovalQueue.resolve -> APPROVED -> broadcast (one event)
    -> window event -> badge refetch.  onResolved also fires the window event (socket-down fallback)
  Operator re-sends -> gate_tool -> APPROVED -> consume -> CONSUMED -> tool runs once

Export / verify:
  GET decisions/export | export.zip -> zip
    -> python3 scripts/verify_decision_log.py <zip> [--pin <entry_hash>]
         ok checked=N head=H            (exit 0)
         FAIL seq=N <reason>            (stderr, exit 1)   incl. "pinned entry missing"
  GET decisions/verify -> chain walk + evidence bundle hash recompute
  UPDATE approval_evidence -> trigger ABORT
```

---

## 3. API / Interface Contracts

No new endpoints. One alias, one behaviour change per read path, one verifier flag.

### 3.1 Export alias — `GET /api/governance/decisions/export.zip`

| Field | Value |
|---|---|
| Method | `GET` |
| Path | `/api/governance/decisions/export.zip` (same handler as `/export`) |
| Auth | Bearer token, same as `/export` |
| Request | Same query: `from`, `to`, `tenant` |
| Response | `200 application/zip`, identical bytes shape to `/export` |
| Errors | Same as `/export` |
| Delivery pattern | Synchronous in-memory zip |

**Frontend trigger:** none. Documentation and `curl` only. The guide example adds `-f`, so a 401 or 404 fails the command instead of saving JSON as a `.zip`.

### 3.2 Approval transition events — WebSocket `approval_update`

| Field | Value |
|---|---|
| Type | WebSocket server push |
| Path | `/api/ws` |
| Request | n/a |
| Response | `{ "type": "approval_update", "id": <int>, "status": "PENDING" \| "APPROVED" \| "REJECTED" \| "CONSUMED" }` |
| Errors | Best-effort |
| Delivery pattern | Fire-and-forget. **Exactly one event per transition.** The route no longer emits its own. |

**Frontend trigger:** `App.tsx` re-emits as a `window` event. `ApprovalsModal` `onResolved` also dispatches that event, so the badge refreshes with the socket down.

### 3.3 Approval read endpoints — `GET /api/governance/approvals`, `GET /api/governance/approvals/{id}`

| Field | Value |
|---|---|
| Method | `GET` |
| Path | unchanged |
| Auth | unchanged |
| Response | Same shape plus `agent_name` (string, may be empty). `agent_id` is still the session-scoped key. |
| Errors | unchanged |
| Delivery pattern | Synchronous. `agent_name` comes from the already-joined `bundle_json`. |

**Frontend trigger:** `ApprovalsModal` renders `agent_name` when present, else `agent_id`, and shows the session id beside it.

### 3.4 Offline verifier — `scripts/verify_decision_log.py`

| Field | Value |
|---|---|
| Type | CLI |
| Path | `python3 scripts/verify_decision_log.py <zip> [--pin <entry_hash>]` |
| Auth | n/a |
| Request | `--pin`: an `entry_hash` the operator recorded earlier |
| Response | `ok checked=N head=H` on stdout, exit 0 |
| Errors | `FAIL seq=<n> <reason>` on stderr, exit 1. New reason: `pinned entry missing`. Unchanged: usage error exits 1. |
| Delivery pattern | Local, standard library only |

**Invariant:** `--pin` is optional. Without it, behaviour is identical to today. With it, the chain must contain a row whose `entry_hash` equals the pin. A truncated tail that drops the pinned row fails, even when `manifest.json` was rewritten to match.

### 3.5 DTO shapes

**`ApprovalSummary` (after)**
```json
{
  "id": 7,
  "agent_id": "chat42_sysops",
  "agent_name": "Sys Ops",
  "action_name": "execute_command",
  "payload": "{\"command\":\"uname -a\"}",
  "status": "PENDING",
  "bundle_hash": "…",
  "flags": ["direct_route"]
}
```

**Direct-route bundle (after)**
```json
{
  "plan": { "agent": "jarvis", "instructions": "<user message, masked>", "step_index": 0, "step_count": 1 },
  "flags": ["direct_route"],
  "links": { "session_id": "chat42", "agent": "Jarvis" }
}
```

### Open Question — auto-resume after Approve (G5)

Pick one before implementation. Neither is in the ordered steps.

| Option | How | Gain | Cost |
|---|---|---|---|
| A. Re-prompt | On `APPROVED`, call `agent.respond(<parent chat>, "Approval #N granted. Retry with identical arguments.")` | No new state. The model synthesises the answer. | Relies on the model repeating identical arguments. Needs the parent chat id (the orchestrator scopes sessions as `<chat>_<agent>`), so `links` must carry it. |
| B. Replay | On `APPROVED`, run `consume` then `execute_tool` with the stored raw payload, post the result into the parent chat | Runs exactly what the human approved. No model variance. | The result lands without model synthesis. Needs the parent chat id. Executes from the stored raw args, so it is a new trust path to review. |
| C. Defer | Keep the documented retry step | Zero work. | Operators expect a resume. |

Recommendation: **C now, B when a customer asks.** B is the only option that keeps the "that exact call" guarantee without relying on the model.

---

## 4. Data Model & Implementation Plan

### 4.1 Entities

No new table or column.

| Object | Change | Notes |
|---|---|---|
| `approval_evidence` | New `BEFORE UPDATE` trigger raising `approval_evidence is append-only`. SQLite and Postgres twins. | `DELETE` stays allowed for the cascade. |
| `approval_evidence.bundle_json` | `links.agent` added to new bundles | `links` is excluded from the hash; old rows lack it and return an empty `agent_name`. |
| Bundle flags | New flag value `direct_route` | Replaces `plan_missing` only when a direct-route plan is set. |
| `approval_requests.agent_id` | Unchanged | Remains the session-scoped match key. Document that it is not an agent id. |

### 4.2 Implementation steps (ordered, no code)

Each step starts with a failing test, then the smallest change.

1. **Export alias (G1)** — `backend/main.py`: register `/api/governance/decisions/export.zip` on the existing `export_decisions_api` handler. Extend `backend/tests/test_decision_log_api.py` so both URLs return `200` with `application/zip` and the same verifiable archive.
2. **One broadcast per transition (G2)** — `backend/main.py`: delete the `manager.broadcast` block in `resolve_approval_api`. Test: resolve a request while a fake client is connected; assert exactly one `APPROVED` event. Extend `backend/tests/test_approval_ws_events.py`.
3. **`onResolved` fallback (G2)** — `frontend/src/App.tsx`: pass `onResolved` that dispatches the `approval_update` window event. Test in `App.test.tsx` or `ApprovalsModal.test.tsx`: after Approve with no socket event, the badge refetches.
4. **Agent name** — `backend/agent.py`: add one module-level `ContextVar` for the display name. Set it in `respond()` and `_respond_as_subagent()` before tool dispatch; reset in `finally`. `backend/governance.py` `gate_tool`: write it to `bundle.links["agent"]`; `get_pending`, `get_all`, `get_detail` return `agent_name` from `bundle_json`. `ApprovalsModal.tsx`: show it. Tests: a Sys Ops request returns `agent_name == "Sys Ops"` and `agent_id` still equals the session id; an approval in session A is not consumable in session B (regression guard).
5. **Direct-route evidence (G4)** — `backend/agent.py`: in the same two entry points, when `evidence_ctx.get()` is `None`, set an `EvidenceContext` with a 1/1 `PlanRef` from the user message and the flag `direct_route`; reset afterwards. Tests: a direct tool call yields a non-empty `plan` and `direct_route`, no `plan_missing`; an orchestrator step still carries the planner plan. `backend/tests/test_evidence_gate_wiring.py` calls `gate_tool` with no context and keeps asserting `plan is None`, so it is unaffected.
6. **Evidence guard (G6)** — `backend/database.py`: add `install_approval_evidence` for SQLite and a Postgres twin beside `install_approval_decisions`; call both where the table is created (`:750`, `:1274`). `backend/tests/conftest.py`: drop the new trigger in the same loop that drops the decision triggers. Test: `UPDATE approval_evidence` raises.
7. **In-DB verify (G6)** — `backend/decision_log.py` `verify()`: after the chain walk, recompute `bundle_hash` for each row that has one and compare with the stored evidence. Mismatch returns `VerifyResult(False, …, "bundle_hash mismatch")`. Test: tamper an evidence row (drop the trigger as the existing fixture does) and assert `ok: false`.
8. **Pin (G6)** — `scripts/verify_decision_log.py`: parse an optional `--pin`; after the walk, fail with `pinned entry missing` if no row has that `entry_hash`. Keep the no-`backend` import rule (`test_verify_script_has_no_backend_imports`). Test: drop the last two rows and rewrite the manifest; without `--pin` exit 0, with the pin of a dropped row exit 1.
9. **Collapsed badge (G8)** — `ApprovalsBadge.tsx`: give the "Approvals" span the `sidebar-label` class so it fades with the other labels; keep the icon and count pill outside it. Test: the count pill is in the DOM and not inside a `sidebar-label` element.
10. **Docs and export text (G9)** — `backend/decision_log.py` `_VERIFY_MD`: say the script lives in the repository at `scripts/verify_decision_log.py` and is not bundled; document `--pin`. `docs/guide/approvals.md`: add `export.zip` and `-f`; CLAIM shows the agent name; `direct_route`; the `CONSUMED` actor is `system` and `APPROVED` is the operator subject; identical calls share one `bundle_hash` because it binds content, not the request; a rejected call stays blocked in the same session and opens a new request in a new one; pinning a head hash. Update the guard test (`test_approvals_guide_drops_false_security_claims`) so it expects `export.zip` to appear and still bans `chain intact`, `encrypted`, `signed manifest`.
11. **Public export check** — run `scripts/export_oss.sh` in dry mode. All touched files are core paths.

### Known constraints carried over from investigation

| Issue | Location | Relevance here |
|---|---|---|
| Raw tool args are logged at INFO | `backend/tools.py:1931` | Still a second secret path, to logs. Not fixed. |
| Login sessions are in memory | `backend/auth.py:14` | A backend restart logs the browser out. Not approvals. |
| `/api/auth/request-code` reports an error without a Telegram bot, though the OTP is still logged | `backend/auth.py`, `backend/main.py` | Demo hygiene: have the bot configured, or read the emergency OTP file. Not fixed. |
| `CodeAgent` runs generated code with no approval | `backend/orchestrator.py:708:710` | Intentional. Document in the guide. |
| `PIIGuard` masks known formats only | `backend/governance.py` | Unknown key shapes pass through. Demo hygiene still applies. |
| Export is tamper-evident, not authenticated | `backend/decision_log.py:181:228` | `--pin` narrows the gap; an attacker who rewrites everything and the pin store still wins. |
| `resolver_note` is stored unmasked in `approval_requests` | `backend/governance.py` `resolve` | The decision log masks it; the request row does not. |
| Old evidence rows have no `links.agent` | `approval_evidence` | `agent_name` is empty for them; the modal falls back to `agent_id`. |
| `.sidebar-collapsed` CSS has no matching class in `App.tsx` | `frontend/src/index.css:675:680` | Dead rule. The collapsed state is the `68px` aside (`:110:120`). Not removed here. |

---

## 5. Verification

Unit and component tests carry items G1–G4, G6, G8, G9. A live-model run is still needed for the parts a stub cannot prove.

| # | Scenario | Pass condition |
|---|---|---|
| W1 | Follow the guide verbatim: `curl -f` on `export.zip`, then the verifier. | HTTP 200, `ok checked=N head=H`, exit 0. |
| W2 | Trigger a request, Approve, and watch the WebSocket. | One `PENDING`, one `APPROVED`, one `CONSUMED` per request. |
| W3 | Trigger a request from a direct chat and from an orchestrator Sys Ops step. | CLAIM shows the agent name and the session id. SOURCE is non-empty in both. Direct has `direct_route`. |
| W4 | Approve in chat A, repeat the same call in chat B. | Chat B opens a new `PENDING` request. |
| W5 | Export, record the head hash, drop the last two rows, rewrite the manifest, verify with and without `--pin`. | Without: `ok`. With: `FAIL … pinned entry missing`, exit 1. |
| W6 | Edit an `approval_evidence` row in the database. | The `UPDATE` is rejected. If the trigger is dropped and the row edited, `/decisions/verify` returns `ok:false`. |
| W7 | Collapsed sidebar with one pending request. | The count pill is visible without hover. |

---

## 6. Remaining work (from `FIX-SPEC-demo-v3.md`, reviewed 2026-10-29)

Status: Draft. Every item below was checked against the tree and is **not implemented**, except where noted.

### 6.1 Context

| ID | Item | State | Finding |
|---|---|---|---|
| R0-1 | Release and demo deploy | Half done | Public `main` already holds the fixes. No release tag covers them. The demo instance is unverified. |
| R1-2 | Gate `CodeAgent` | Open | `gate_tool` cannot work here. See the design problem below. |
| R2-1 | Auto-resume after Approve | Open | Needs the Open Question in §3. |
| R2-2 | Sticky `REJECTED` | Open | `gate_tool` returns the old row with no expiry (`governance.py:694`). |
| R2-3 | Signed manifest | Open | Optional. |
| R2-4 | Raw secret at rest | Open | `request_approval` stores `json.dumps(payload)` unmasked (`governance.py:275`). `find_latest` compares the raw JSON (`governance.py:586`). |
| R2-5 | Agent name in the chain | Open | `_HASH_FIELDS` has no agent field. `schema_ver` is `1` (`decision_log.py:275`). The name exists only in the unhashed `links.agent`. |
| R2-6 | Persistent login sessions | Open | `active_sessions` is a module-level `set` (`auth.py:14`), read in `auth.py:90, 156` and imported directly in `identity.py:40`. |
| R3-1 | Env leak in `test_agent.py` | Open, reproduced | `COMPLEXITY_ROUTING=always_agent pytest backend/tests/test_agent.py` fails `test_respond_http_error` and `test_respond_openmodel_success`. With `auto` all 12 pass. `agent.py:125` runs `load_dotenv()` at import. |
| Tooling | `ruff`, `black`, `mypy` | Not installed | No venv in the repo; `python3 -m ruff` fails. R1-1 is still unchecked by them. |

**R1-2 design problem: retry-based gating does not fit generated code.** `gate_tool` approves an exact call: same session, action, and payload. The `code` agent writes new Python on every LLM call, so the "identical arguments" retry never matches and the request never consumes. The orchestrator also has no user re-send step. A real gate needs the *replay* path (run the stored, approved code). That is Option B in §3, not a one-line `gate_tool` call. Two more facts:

- `execute_code` has exactly two callers, both inside `CodeAgent.run_and_correct` (`subagents.py:731, 743`).
- `AnalystAgent.run` reuses `CodeAgent.run_and_correct` (`subagents.py:780`). A guard in `run_and_correct` covers the `code` step and the analyst chart step with one change.

### 6.2 Explicit scope decisions (please confirm)

| Decision | Rationale |
|---|---|
| R1-2: ship the demo switch, not a gate. `DISABLE_CODE_AGENT` (default `false`), checked at the top of `CodeAgent.run_and_correct`. | One guard covers both callers. A gate is Option B and shares its cost. This reverses nothing in Phase 2: "do not gate `CodeAgent`" still holds. |
| R1-2 acceptance changes to "refused, no sandbox call, no `PENDING` row". | "Creates a `PENDING` approval" is not reachable with the retry gate. |
| R2-4: store the masked payload and match on a hash. No encryption by default. | Encryption is only needed to run the raw args later, which only Option B does. Hash-and-mask removes the secret with no key to manage and no new dependency. |
| R2-4: if Option B is chosen, store an encrypted payload next to the hash, key from an env var or a local file. | No cloud KMS. The repo has no `cryptography` pin to reuse; adding one is part of that decision. |
| R2-5: add a nullable `agent_name` column, hashed only when not `NULL`. | Old rows keep their hash. New rows bind the name. Mixed chains verify. See §6.4. |
| R2-2: `APPROVAL_REJECT_COOLDOWN_S`, default `0`, meaning never expires (today's behaviour). | Opt-in, no UI. `resolved_at` already exists on `approval_requests`. |
| R2-3: defer. | `--pin` already detects truncation with no key. A signature adds authenticity, and the stdlib verifier would have to shell out to `ssh-keygen`. Add on request. |
| R2-6: a DB table of hashed tokens, with an expiry. No Redis. | The app DB exists on both SQLite and Postgres. Hashing keeps a DB leak from handing out live tokens. |
| Bundle R2-1, R1-2 gating, and R2-4 encryption as one phase, only if Option B is chosen. | All three need "run the stored, approved call". Build the replay path once. |

### 6.3 Architecture diagram

```dot
digraph ApprovalsPhase3 {
  graph [fontname="Helvetica" rankdir=LR]
  node  [fontname="Helvetica" shape=box style=rounded]

  subgraph cluster_agents {
    label="Agent runtime" style=dashed color=purple
    CA   [label="CodeAgent.run_and_correct\n(new: DISABLE_CODE_AGENT guard)" shape=component]
    ORC  [label="orchestrator 'code' step" shape=component]
    ANA  [label="AnalystAgent.run" shape=component]
  }

  subgraph cluster_gov {
    label="Governance core" style=dashed color=darkgreen
    GT   [label="gate_tool\n(new: reject cooldown, hash match)" shape=component]
    AQ   [label="ApprovalQueue.find_latest\n(new: compare payload_hash)" shape=component]
    DL   [label="decision_log.append\n(new: agent_name)" shape=component]
  }

  subgraph cluster_auth {
    label="Auth" style=dashed color=steelblue
    AU   [label="auth.create/validate/destroy_session\n(new: DB-backed)" shape=component]
    ID   [label="identity.py\n(new: calls validate_session)" shape=component]
  }

  subgraph cluster_db {
    label="SQLite / Postgres" style=dashed color="#336699"
    T_req [shape=record, label="{ approval_requests | payload (masked) | payload_hash (new) | resolved_at }"]
    T_dec [shape=record, label="{ approval_decisions | agent_name (new, nullable) | entry_hash }"]
    T_ses [shape=record, label="{ auth_sessions (new) | token_hash | expires_at }"]
  }

  SC [label="scripts/verify_decision_log.py\n(new: reads schema_ver 1 and 2)"]

  ORC -> CA
  ANA -> CA
  GT -> AQ -> T_req
  GT -> DL -> T_dec
  AU -> T_ses
  ID -> AU
  SC -> T_dec [style=dotted label="export zip"]
}
```

Data flow summary:

```
Code step:   orchestrator 'code' | AnalystAgent -> CodeAgent.run_and_correct
               -> DISABLE_CODE_AGENT=true: return {success: false, stderr: "CodeAgent disabled"}, no LLM call, no sandbox
Gate:        gate_tool -> find_latest(agent_id, action, sha256(canonical(payload)))
               -> REJECTED and age < cooldown: refuse; age >= cooldown (or cooldown 0 = never): see rule in 6.4
               -> new request stores masked payload + payload_hash
Log:         ApprovalQueue -> decision_log.append(agent_name from bundle links) -> hashed when not NULL
Verify:      verify_decision_log.py: per row, hash fields + agent_name only if the key is present and not null
Login:       create_session -> INSERT hash(token) | validate_session -> SELECT, check expiry | restart keeps rows
```

### 6.4 API / Interface contracts

No new HTTP endpoint. Config, schema, and one verifier rule change.

| Item | Contract |
|---|---|
| `DISABLE_CODE_AGENT` | Env, default `false`, documented in `.env.example`. When `true`, `CodeAgent.run_and_correct` returns the existing result shape with `success: false`, `attempts: 0`, `code: ""`, `stdout: ""`, `display_data: []`, and `stderr: "CodeAgent disabled (DISABLE_CODE_AGENT)"`. `AnalystAgent.run` reads `res["success"]` first, so its existing failure branch applies. |
| `APPROVAL_REJECT_COOLDOWN_S` | Env integer, default `0`. `0` keeps a `REJECTED` row final. `N > 0`: a `REJECTED` row whose `resolved_at` is older than `N` seconds is ignored by `gate_tool`, so the same call opens a new `PENDING` request. The old row and its log entries stay. |
| `approval_requests.payload` | Holds `PIIGuard`-masked JSON. `ApprovalSummary.payload` is unchanged in shape. |
| `approval_requests.payload_hash` | `sha256` of `canonical_json(payload)`, the same function the log uses for `payload_hash`. `find_latest` matches on it. Rows with `NULL` fall back to hashing the stored payload. |
| `approval_decisions.agent_name` | Nullable `TEXT`. Hashed only when not `NULL`. Present as a key in `decisions.jsonl` for new rows. |
| Export `manifest.schema_ver` | `2` for new exports. The verifier accepts `1` and `2`. |
| Verifier rule | `entry_hash` body = `_HASH_FIELDS`, plus `agent_name` when the row has that key with a non-null value. Dropping the key from a new row changes the hash, so it fails. Old exports have no key and still return `ok`. |
| Login session | Token is returned as today. The server stores only `sha256(token)`, `created_at`, `expires_at`. `SESSION_TTL_HOURS`, default `168` (proposal). Expired or missing rows return `401`, which the client already turns into the login screen (`utils.tsx:461`, `App.tsx:509`). |

**Open Question: session TTL.** Today sessions never expire. Persisting them without an expiry would make a stolen token valid for ever across restarts. Pick a default before implementation; `168` hours is a proposal.

**Open Question: R2-1 (see §3).** Choosing B pulls in R1-2 gating and R2-4 encryption. Choosing C leaves the switch, the hash-and-mask change, and everything else here as is.

### 6.5 Data model & implementation plan

| Object | Change | Notes |
|---|---|---|
| `approval_requests` | Add `payload_hash TEXT` | Same `ALTER TABLE ... ADD COLUMN` loop as `bundle_hash` and `session_id` (`database.py:775`), plus the Postgres twin. |
| `approval_decisions` | Add `agent_name TEXT` | Add `ALTER` for both backends. The append-only triggers block `UPDATE` and `DELETE`, not `ADD COLUMN`. No backfill is possible or wanted. |
| `auth_sessions` | New: `token_hash TEXT PRIMARY KEY`, `created_at TEXT`, `expires_at TEXT` | Create beside the other tables in `database.py`, SQLite and Postgres. |

Ordered steps. Each starts with a failing test, then the smallest change.

1. **R0-1 release.** Run `TAG=v1.4.4 scripts/export_oss.sh --push`. The dry run shows nothing to commit, so this pushes `main` unchanged and adds the tag. `release.yml` makes the release. Then on the demo host: `git pull && docker compose up -d --build`. Acceptance: tag `v1.4.4` exists on the public repo and W1, W2, W5 from §5 pass on the demo instance.
2. **R3-1 env leak.** `backend/tests/test_agent.py`: an autouse fixture that calls `monkeypatch.delenv("COMPLEXITY_ROUTING", raising=False)`. Tests that need a mode already use `patch.dict`. Check: run the file with `COMPLEXITY_ROUTING=always_agent` and with `auto`; 12 pass in both. Run the rest of `backend/tests` with `always_agent` once to find other leaks.
3. **R1-2 demo switch.** `backend/subagents.py` `CodeAgent.run_and_correct`: return the disabled result before the first `call_llm`. `.env.example`: document `DISABLE_CODE_AGENT=false`. Tests in `backend/tests/test_subagents.py`: with the flag set, `execute_code` and `call_llm` are not called, and the result has `success: false`; `AnalystAgent.run` returns its failure result; the `code` orchestrator step records an error trace. Unset: behaviour unchanged. Guide: say when to set it.
4. **R2-5 agent name in the chain.** `database.py`: add the column. `decision_log.py`: add an `agent_name` argument to `append`, hash it only when not `NULL`, include it in `_COLUMNS` reads and `_public_row`, write `schema_ver: 2` in `export_zip`. `governance.py`: pass `ApprovalQueue._agent_name(...)` from `request_approval`, `resolve`, and `consume`. `scripts/verify_decision_log.py`: apply the verifier rule above and accept `schema_ver` `1` and `2`, keeping the no-`backend`-import rule. Tests: a new export verifies; an old fixture export still returns `ok`; removing `agent_name` from a new row, or editing it, fails with `entry_hash mismatch`; a mixed chain verifies. **Challenge:** the name already ships in `evidence/<id>.json` as `links.agent`, unhashed. Do this step only if an auditor needs the name inside the chain.
5. **R2-6 persistent sessions.** `backend/auth.py`: route `create_session`, `validate_session`, `destroy_session`, and the role lookup at `auth.py:156` through one DB helper keyed by `sha256(token)`. `backend/identity.py:40`: call `validate_session` instead of importing the set. Remove `active_sessions`. Tests: create a session, drop any in-process state, validate still passes; an expired row fails; destroy removes the row; `test_auth` and `identity` tests still pass.
6. **R2-4 raw secret at rest.** `governance.py` `request_approval`: write the masked payload and `payload_hash`. `find_latest`: compare hashes, with the `NULL` fallback. The Phase 1 read-path masking stays as a second layer. Tests: a request whose payload holds an `sk-…` key leaves no `sk-…` in `approval_requests.payload`; the same call after Approve still consumes (the match now uses the hash of the raw call); an old row with `NULL` hash still matches. **Limit:** `PIIGuard` masks known formats only. The raw args are also logged at INFO (`tools.py:1931`); fix that line in the same step or the acceptance is only half true.
7. **R2-2 rejected cooldown.** `governance.py`: have `find_latest` also return `resolved_at`; in `gate_tool`, a `REJECTED` row older than the cooldown is skipped. `.env.example`: document it. Tests: default `0` keeps the row blocking; with a cooldown and an aged `resolved_at`, the same call opens a new `PENDING` row.
8. **R2-1, R1-2 gate, R2-4 encryption (only if Option B).** Not specified here. Write a separate spec for the replay path first: parent chat id in `links`, a `consume`-then-run path from the stored payload, and the trust review that goes with it.
9. **R2-3 signed manifest (on request).** Detached signature file in the zip, checked by an optional `--sig` flag that runs `ssh-keygen -Y verify`. `--pin` stays the default.
10. **Tooling.** Create a venv, install `ruff`, `black`, and `mypy`, and run them with the full `pytest` suite on the R1-1 change before the next release. Run `scripts/export_oss.sh` dry before every push; all paths here are core paths.

### 6.6 Known constraints carried over

| Issue | Location | Relevance |
|---|---|---|
| Fresh `/tmp` clone is cached | `scripts/export_oss.sh` (`DEST`) | A stale clone can hide a diff. `git fetch` ran fine today; delete `/tmp/hermes-synapse-oss` if the dry run looks wrong. |
| Raw tool args logged at INFO | `backend/tools.py:1931` | Second secret path. Handled in step 6. |
| OTP delivery without a Telegram bot | `backend/auth.py` | Not approvals. Demo hygiene: configure the bot or read the emergency OTP file. |
| Demo instance state | outside the repo | Not verifiable from here. Step 1 acceptance covers it. |

### 6.7 Order

R0-1, R3-1, R1-2 switch (all before the Keil call), then R2-6, R2-4, R2-5, R2-2, then the Option B bundle and R2-3 when asked.

This differs from `FIX-SPEC-demo-v3.md` in two places. R2-6 and R2-4 move ahead of R2-5, because R2-5 is optional and the other two remove a restart logout and a secret at rest. R1-2 is the switch only.

### 6.8 Verification

| # | Scenario | Pass condition |
|---|---|---|
| X1 | On the demo instance after the `v1.4.4` deploy, run the guide's `curl -f` export and the verifier. | `ok checked=N head=H`, exit 0. |
| X2 | Run `backend/tests/test_agent.py` with `COMPLEXITY_ROUTING=always_agent`. | 12 pass. |
| X3 | Set `DISABLE_CODE_AGENT=true` and ask the orchestrator for "a script that deletes X". | The step reports "CodeAgent disabled"; no sandbox call; no `PENDING` row. |
| X4 | Log in, restart the backend, call any API. | `200`, not `401`. |
| X5 | Put a known-format key in a gated tool call; read `approval_requests.payload`. | No raw key. Approve and re-send still runs the tool once. |
| X6 | Verify an export made before R2-5, and one made after. | Both `ok`. Editing `agent_name` in the new one fails. |
| X7 | Reject a call with `APPROVAL_REJECT_COOLDOWN_S=1`, wait, repeat it. | A new `PENDING` request appears. With `0`, it stays rejected. |

---

## Demo script changes

- Say: "tamper-evident decision log; pin the head hash and truncation is detected". Do not say signed, encrypted, or tamper-proof.
- Show: orchestrator → Sys Ops → CLAIM with agent name and session → Approve → re-send → export → verify → verify with `--pin`.
- Say "now I ask it again" at the retry step, until the Open Question is decided.
- Do not show: backend logs, the `code` agent, a prompt that contains a key, or a login right after a backend restart.

---

## Storage

Save this spec to `docs/specs/approvals-demo-hardening-phase2.md` (+ `docs/specs/approvals-demo-hardening-phase2.dot`) before uploading anywhere.
