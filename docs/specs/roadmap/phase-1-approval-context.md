# Phase 1: Context for approvals (2–4 weeks)

Items: **1** Evidence bundle · **2** ApprovalsModal in the UI · **3** Immutable decision log.

Order: `canonical.py` → 1a (schema + stub capture) → 3 (decision log; needs `Principal`) → 1b (API) → 2 (UI) → 1c (in-flight context). That order puts a demoable approve button on screen in week 2.

---

## Item 1: Evidence bundle

**Design source:** `docs/specs/approval-evidence-bundle.md` on `origin/cursor/approval-evidence-bundle-84db`. This section narrows that design to code and tests. If the two disagree, this section wins, and the branch spec gets updated in the same PR.

### 1.0 Branch logistics

The spec branch is based on an older OSS `main`. `git diff trade-main...origin/cursor/approval-evidence-bundle-84db` touches 98 files, mostly unrelated drift. **Do not merge it as-is.**

```bash
git switch -c feat/approval-evidence-bundle trade-main
git checkout origin/cursor/approval-evidence-bundle-84db -- docs/specs/approval-evidence-bundle.md
git commit -m "docs: import approval evidence bundle spec"
# open PR, then stack implementation commits on top
```

### 1.1 Module layout

| File | New / changed | Responsibility |
| --- | --- | --- |
| `backend/canonical.py` | new | `canonical_json`, `sha256_hex` |
| `backend/evidence.py` | new | `EvidenceBundle` model, `evidence_ctx`, `build_bundle`, `redact_bundle`, `cap_bundle`, `bundle_hash`, `describe` |
| `backend/governance.py` | changed | `request_approval(..., bundle=None)`, `get_detail(id)`, `gate_tool` builds the bundle |
| `backend/database.py` | changed | `approval_evidence` table; `approval_requests.bundle_hash`, `.session_id` |
| `backend/orchestrator.py`, `backend/agent.py` | changed (1c) | set `evidence_ctx` around steps / ReAct turns |
| `backend/main.py` | changed | `GET /api/governance/approvals/{id}`, list summaries |

### 1.2 Data model

```sql
-- SQLite (Postgres: id SERIAL, same columns)
CREATE TABLE IF NOT EXISTS approval_evidence (
    request_id   INTEGER PRIMARY KEY REFERENCES approval_requests(id),
    bundle_json  TEXT NOT NULL,      -- redacted, capped snapshot
    bundle_hash  TEXT NOT NULL,      -- sha256(canonical(hash_view(bundle)))
    schema_ver   INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL
);
ALTER TABLE approval_requests ADD COLUMN bundle_hash TEXT;   -- guarded
ALTER TABLE approval_requests ADD COLUMN session_id  TEXT;   -- guarded
```

### 1.3 Bundle schema (v1)

```python
class UpstreamItem(BaseModel):
    kind: Literal["plan_step", "tool_result", "document"]
    name: str                    # step agent id or tool name
    excerpt: str                 # ≤ 4 KiB after redaction
    sha256: str                  # of FULL redacted body
    truncated: bool = False
    reason: Optional[str] = None # "char_cap_4k" | "step_context_3000" | "tool_result_600" | "pdf_page_stop"

class PlanRef(BaseModel):
    agent: str
    instructions: str
    step_index: int
    step_count: int

class EvidenceBundle(BaseModel):
    schema_ver: Literal[1] = 1
    description: str
    agent_id: str
    action_name: str
    inputs: dict                 # == payload (redacted copy)
    step_context: Optional[str] = None
    plan: Optional[PlanRef] = None
    upstream: list[UpstreamItem] = []
    flags: list[str] = []        # sorted, unique
    links: dict = {}             # session_id, parent_message_id, decision_log_id — NOT hashed
```

**What goes into the hash** (`hash_view`): `schema_ver, agent_id, action_name, inputs, plan, upstream[].{kind,name,sha256,truncated,reason}, flags`. Excluded: `description`, `excerpt`, `links`, `step_context` (its hash appears as an upstream item instead).

### 1.4 Core functions

```python
evidence_ctx: ContextVar[Optional["EvidenceContext"]]

@dataclass
class EvidenceContext:
    plan: Optional[PlanRef] = None
    step_context: Optional[str] = None
    upstream: list[UpstreamItem] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)
    def add_tool_result(self, name: str, body: str, *, capped_at: int | None = None) -> None: ...
    def add_step_result(self, agent: str, body: str, *, truncated: bool) -> None: ...

def build_bundle(agent_id, action_name, payload, ctx: EvidenceContext | None) -> EvidenceBundle
def redact_bundle(b: EvidenceBundle) -> EvidenceBundle   # PIIGuard.mask_pii on every str; MemoryGuard on documents
def cap_bundle(b: EvidenceBundle, *, per_item=4096, total=65536) -> EvidenceBundle
def hash_view(b: EvidenceBundle) -> dict
def bundle_hash(b: EvidenceBundle) -> str
def describe(b: EvidenceBundle) -> str                   # deterministic template, no LLM
```

`describe` template (deterministic, so it can be tested):

```
"{agent_id} wants to run {action_name}" + (" for step {i+1}/{n} ({plan.agent})" if plan) + (": " + first 140 chars of plan.instructions if plan) + "."
```

Pipeline order inside `gate_tool` (new-request branch only): `build → redact → cap → hash → insert`. **Redaction runs before hashing**, so the hash binds what the reviewer can actually see.

### 1.5 Gate changes

```python
def gate_tool(agent_id, action_name, payload) -> Optional[str]:
    ...
    else:
        bundle = cap_bundle(redact_bundle(build_bundle(agent_id, action_name, payload, evidence_ctx.get())))
        request_id = ApprovalQueue.request_approval(
            agent_id=agent_id, action_name=action_name, payload=payload,
            description=bundle.description, bundle=bundle,
        )
```

`find_latest` stays payload-keyed. A retry while the row is `PENDING` or `APPROVED` reuses the **original** snapshot. The bundle is never refreshed.

### 1.6 API

| Method | Path | Change |
| --- | --- | --- |
| GET | `/api/governance/approvals` | Each item gains `bundle_hash`, `flags` (≤ 5), `description`. No `bundle_json`. |
| GET | `/api/governance/approvals/{id}` | **New.** Request fields + `bundle` (redacted) + `bundle_hash` + `decisions` (from item 3). 404 if missing. |
| POST | `/api/governance/approvals/{id}/resolve` | Body unchanged. The server reads the stored hash. **A client-supplied `bundle_hash` in the body is ignored.** |

### 1.7 Test plan (write first)

**`backend/tests/test_canonical_unit.py`**

```python
from backend.canonical import canonical_json, sha256_hex

def test_key_order_does_not_change_hash():
    assert sha256_hex(canonical_json({"b": 1, "a": 2})) == sha256_hex(canonical_json({"a": 2, "b": 1}))

def test_unicode_kept_not_escaped():
    assert canonical_json({"t": "שלום"}) == '{"t":"שלום"}'

def test_no_whitespace():
    assert " " not in canonical_json({"a": [1, 2]})
```

**`backend/tests/test_evidence_unit.py`**

```python
from backend.evidence import (EvidenceContext, PlanRef, build_bundle, redact_bundle,
                              cap_bundle, bundle_hash, describe)

def _ctx():
    c = EvidenceContext(plan=PlanRef(agent="code", instructions="Run ls in /tmp", step_index=0, step_count=2))
    c.add_tool_result("web_search", "result body", capped_at=None)
    return c

def test_bundle_without_context_flags_plan_missing():
    b = build_bundle("chat1", "execute_command", {"cmd": "ls"}, None)
    assert b.plan is None and b.upstream == []
    assert "plan_missing" in b.flags

def test_hash_stable_across_excerpt_recut():
    b1 = build_bundle("c", "execute_command", {"cmd": "ls"}, _ctx())
    b2 = b1.model_copy(deep=True); b2.upstream[0].excerpt = "different cut"
    assert bundle_hash(b1) == bundle_hash(b2)

def test_hash_changes_when_upstream_body_changes():
    c1, c2 = _ctx(), _ctx()
    c2.upstream[0].sha256 = "0" * 64
    assert bundle_hash(build_bundle("c", "x", {}, c1)) != bundle_hash(build_bundle("c", "x", {}, c2))

def test_description_is_not_tool_name():
    b = build_bundle("chat1", "execute_command", {"cmd": "ls"}, _ctx())
    assert b.description != "execute_command"
    assert "step 1/2" in b.description and "code" in b.description

def test_pii_redacted_in_inputs_and_upstream():
    c = EvidenceContext(); c.add_tool_result("read", "mail me at a@b.com key sk-abcdefghijklmnopqrstu")
    tok = "eyJhbGciOiJIUzI1NiJ9.payloadpart.signature"   # ≥20 chars: PIIGuard BEARER_TOKEN
    b = redact_bundle(build_bundle("c", "execute_command", {"cmd": f"curl -H 'Authorization: Bearer {tok}'"}, c))
    dumped = b.model_dump_json()
    assert "a@b.com" not in dumped and "sk-abcdefghijklmnop" not in dumped and tok not in dumped

def test_excerpt_capped_and_flagged():
    c = EvidenceContext(); c.add_tool_result("read", "x" * 10_000)
    b = cap_bundle(build_bundle("c", "x", {}, c))
    assert len(b.upstream[0].excerpt.encode()) <= 4096
    assert b.upstream[0].truncated and b.upstream[0].reason == "char_cap_4k"

def test_total_cap_drops_oldest_but_keeps_hashes():
    c = EvidenceContext()
    for i in range(40): c.add_tool_result(f"t{i}", "y" * 4000)
    b = cap_bundle(build_bundle("c", "x", {}, c))
    assert len(b.model_dump_json().encode()) <= 65536
    assert "upstream_dropped" in b.flags
    assert all(u.sha256 for u in b.upstream)

def test_tool_result_600_cap_flag_propagates():
    c = EvidenceContext(); c.add_tool_result("t", "z" * 600, capped_at=600)
    assert "tool_result_capped_600" in build_bundle("c", "x", {}, c).flags
```

**`backend/tests/test_evidence_gate_wiring.py`**

```python
import json
from backend.evidence import evidence_ctx, EvidenceContext, PlanRef
from backend.governance import ApprovalQueue
from backend.tools import execute_tool

def test_pending_request_has_bundle_and_hash():
    out = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev1"))
    detail = ApprovalQueue.get_detail(out["request_id"])
    assert detail["bundle_hash"] and len(detail["bundle_hash"]) == 64
    assert detail["bundle"]["inputs"] == {"command": "echo hi"}

def test_retry_while_pending_reuses_snapshot():
    a = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev2"))
    tok = evidence_ctx.set(EvidenceContext(plan=PlanRef(agent="code", instructions="new", step_index=0, step_count=1)))
    try:
        b = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev2"))
    finally:
        evidence_ctx.reset(tok)
    assert a["request_id"] == b["request_id"]
    assert ApprovalQueue.get_detail(a["request_id"])["bundle"]["plan"] is None

def test_consumed_then_new_snapshot():
    a = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev3"))
    ApprovalQueue.resolve(a["request_id"], "APPROVED")
    execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev3")  # runs, consumes
    c = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev3"))
    assert c["request_id"] != a["request_id"]

def test_bundle_row_is_not_updatable_via_queue_api():
    a = json.loads(execute_tool("execute_command", {"command": "echo hi"}, chat_id="ev4"))
    h = ApprovalQueue.get_detail(a["request_id"])["bundle_hash"]
    ApprovalQueue.resolve(a["request_id"], "APPROVED")
    assert ApprovalQueue.get_detail(a["request_id"])["bundle_hash"] == h
```

**`backend/tests/test_evidence_api.py`**: `TestClient` + `create_session()`:

- `test_list_items_have_hash_and_no_bundle_json`
- `test_get_by_id_returns_redacted_bundle`
- `test_get_by_id_404`
- `test_resolve_ignores_client_supplied_hash` (POST body includes `bundle_hash: "evil"`; stored hash unchanged)
- `test_unauthenticated_get_by_id_401`

**1c in-flight context, `backend/tests/test_evidence_orchestrator_cross.py`**

- `test_orchestrated_step_attaches_plan_ref`: patch the planner LLM to return 2 steps. The step-2 agent calls `execute_command`. Assert `bundle.plan.step_index == 1` and `step_count == 2`.
- `test_prior_step_result_in_upstream_with_truncation_flag`: the step-1 output is longer than 3000 chars, so `compress_step_context` truncates it. Assert an upstream item with `reason == "step_context_3000"` and flag `step_output_truncated`.
- `test_contextvar_does_not_leak_between_concurrent_turns`: `asyncio.gather` two turns with different plans. Each request's plan matches its own turn.

### 1.8 Acceptance

- Every new `approval_requests` row has a matching `approval_evidence` row and a non-null `bundle_hash`.
- No PII token class from `PIIGuard.PATTERNS` appears in `bundle_json` or in the GET response.
- `test_high_risk_tool_waits_for_human_then_runs_once` still passes.

---

## Item 2: ApprovalsModal in the UI

### 2.1 Current state

The component exists and is not mounted. Its styles are inline. It uses `localStorage.jarvis_auth_token`. It renders raw `payload`.

### 2.2 Design

| File | Change |
| --- | --- |
| `frontend/src/api/governance.ts` | **new**: typed client `listApprovals`, `getApproval(id)`, `resolveApproval(id, decision, note, reason?)`, `pendingCount()` |
| `frontend/src/types.ts` | `ApprovalSummary`, `ApprovalDetail`, `EvidenceBundle`, `UpstreamItem`, `DecisionEntry` |
| `frontend/src/components/ApprovalsModal.tsx` | Claim / source split. Lazy-load detail on expand. Filter tabs `Pending · All`. |
| `frontend/src/components/ApprovalsBadge.tsx` | **new**: header button with a count. Polls `/count` every 10 s, and refreshes immediately on websocket `approval_update` |
| `frontend/src/App.tsx` | mount badge + modal |
| `backend/main.py` / `websocket_manager.py` | broadcast `{"type":"approval_update","id","status"}` on create / resolve / consume |
| `frontend/src/index.css` | move inline styles into `.approvals-*` classes (glass panel, status chips) |

Layout of one expanded row:

```
┌ CLAIM ─────────────────────────────┬ SOURCE ─────────────────────────────┐
│ #42  code_agent → execute_command  │ Plan step 2/3 · code                 │
│ "code_agent wants to run …"        │   "Run the migration script…"        │
│ args (pretty JSON)                 │ Upstream                             │
│ hash 3f9a…c1 (copy)                │   web_search  [truncated] sha 9b…   │
│ [PENDING]                          │   excerpt…                           │
│ note: [__________]  ✓ Approve ✗ Reject                                    │
└────────────────────────────────────┴──────────────────────────────────────┘
```

Rules:

- With no plan, the panel shows **"No planner step attached"**. With no upstream, it shows **"No upstream results"**. The panel is never hidden.
- Truncation chips: `truncated`, `read stopped before the last page`, `tool result capped at 600 chars`.
- A **CRITICAL** tier (item 4) keeps Approve disabled until the reason field has 10 or more chars. The field is shown only when `detail.requires_reason`, so Phase 1 does not need it yet.
- Keyboard: `A` approves and `R` rejects the focused pending row. `Esc` closes. Uses `<dialog>` + `showModal()` so the browser handles focus trapping.

### 2.3 Test plan (write first)

**`frontend/src/components/ApprovalsModal.test.tsx`**

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ApprovalsModal } from './ApprovalsModal';

const summary = [{ id: 7, agent_id: 'code', action_name: 'execute_command', description: 'code wants to run execute_command for step 1/2 (code).',
  status: 'PENDING', created_at: '2026-10-21T06:00:00Z', bundle_hash: 'a'.repeat(64), flags: ['tool_result_capped_600'], payload: '{"command":"ls"}' }];
const detail = { ...summary[0], bundle: { plan: { agent: 'code', instructions: 'List files', step_index: 0, step_count: 2 },
  inputs: { command: 'ls' }, upstream: [{ kind: 'tool_result', name: 'web_search', excerpt: 'hello', sha256: 'b'.repeat(64), truncated: true, reason: 'tool_result_600' }], flags: [] }, decisions: [] };

beforeEach(() => {
  globalThis.fetch = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith('/approvals')) return new Response(JSON.stringify(summary));
    if (url.endsWith('/approvals/7')) return new Response(JSON.stringify(detail));
    if (url.endsWith('/approvals/7/resolve')) return new Response(JSON.stringify({ status: 'success' }));
    return new Response('{}', { status: 404 });
  }) as any;
});

describe('ApprovalsModal', () => {
  it('shows description, not just the tool name', async () => {
    render(<ApprovalsModal isOpen onClose={() => {}} />);
    expect(await screen.findByText(/wants to run execute_command for step 1\/2/)).toBeInTheDocument();
  });

  it('lazy-loads evidence on expand and shows plan + truncation chip', async () => {
    render(<ApprovalsModal isOpen onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: /show evidence #7/i }));
    expect(await screen.findByText('List files')).toBeInTheDocument();
    expect(screen.getByText(/tool result capped at 600 chars/i)).toBeInTheDocument();
  });

  it('shows explicit empty state when plan is missing', async () => {
    (detail.bundle as any).plan = null;
    render(<ApprovalsModal isOpen onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: /show evidence #7/i }));
    expect(await screen.findByText('No planner step attached')).toBeInTheDocument();
  });

  it('approve posts decision + note and calls onResolved', async () => {
    const onResolved = vi.fn();
    render(<ApprovalsModal isOpen onClose={() => {}} onResolved={onResolved} />);
    fireEvent.change(await screen.findByPlaceholderText(/resolver note/i), { target: { value: 'ok' } });
    fireEvent.click(screen.getByRole('button', { name: /approve/i }));
    await waitFor(() => expect(onResolved).toHaveBeenCalled());
    const call = (fetch as any).mock.calls.find((c: any[]) => c[0].endsWith('/resolve'));
    expect(JSON.parse(call[1].body)).toEqual({ decision: 'APPROVED', resolver_note: 'ok' });
  });

  it('never sends bundle_hash from the client', async () => {
    render(<ApprovalsModal isOpen onClose={() => {}} />);
    fireEvent.click(await screen.findByRole('button', { name: /reject/i }));
    const call = (fetch as any).mock.calls.find((c: any[]) => c[0].endsWith('/resolve'));
    expect(JSON.parse(call[1].body)).not.toHaveProperty('bundle_hash');
  });
});
```

**`frontend/src/components/ApprovalsBadge.test.tsx`**

- `renders count from /count`
- `hides number when zero`
- `refreshes on approval_update websocket message` (inject a fake WS through props or context)
- `click opens modal`

**`backend/tests/test_approval_ws_events.py`**: patch `websocket_manager.broadcast`, then assert it is called with `approval_update` on create, resolve and consume.

### 2.4 Acceptance

- In a demo, an operator who triggers `execute_command` from chat sees the badge go to 1 within 10 s, opens it, reads the plan step and approves. A retry of the agent's tool call then runs once.
- `npm --prefix frontend run build` is clean, with no `tsc` errors.

---

## Item 3: Immutable decision log

### 3.1 Goal

An append-only, tamper-evident record of **who** decided **what**, **when**, **on which evidence** (`bundle_hash`). It is exportable for legal and compliance review, and anyone can verify it offline.

### 3.2 Design

**Hash chain, one chain per tenant.** In Phase 1 there is one chain, `"default"`.

```sql
CREATE TABLE IF NOT EXISTS approval_decisions (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,  -- Postgres: BIGSERIAL
    tenant_id     TEXT NOT NULL DEFAULT 'default',
    request_id    INTEGER NOT NULL,
    event         TEXT NOT NULL,       -- REQUESTED | APPROVED | REJECTED | CONSUMED | EXPIRED
    actor_subject TEXT NOT NULL,       -- Principal.subject, or "agent:<agent_id>" / "system"
    actor_roles   TEXT NOT NULL,       -- canonical JSON list
    auth_method   TEXT NOT NULL,
    action_name   TEXT NOT NULL,
    payload_hash  TEXT NOT NULL,       -- sha256(_payload_key(payload))
    bundle_hash   TEXT,                -- from approval_evidence
    reason        TEXT,                -- resolver note / written reason (redacted)
    occurred_at   TEXT NOT NULL,       -- UTC ISO-8601, server clock
    prev_hash     TEXT NOT NULL,       -- entry_hash of previous row in same tenant chain, or 64 zeros
    entry_hash    TEXT NOT NULL UNIQUE -- sha256(canonical(row minus seq, entry_hash))
);
CREATE INDEX IF NOT EXISTS idx_decisions_request ON approval_decisions(request_id);
CREATE INDEX IF NOT EXISTS idx_decisions_tenant_seq ON approval_decisions(tenant_id, seq);

-- SQLite: block UPDATE/DELETE at the storage layer
CREATE TRIGGER IF NOT EXISTS approval_decisions_no_update BEFORE UPDATE ON approval_decisions
BEGIN SELECT RAISE(ABORT, 'approval_decisions is append-only'); END;
CREATE TRIGGER IF NOT EXISTS approval_decisions_no_delete BEFORE DELETE ON approval_decisions
BEGIN SELECT RAISE(ABORT, 'approval_decisions is append-only'); END;
```

Postgres uses an equivalent `CREATE OR REPLACE FUNCTION … RAISE EXCEPTION` trigger, plus `REVOKE UPDATE, DELETE ON approval_decisions FROM <app_role>`. The REVOKE goes in the deploy docs, because the app role may not own the grant.

> [!IMPORTANT]
> `conftest.py` truncates tables with `DELETE`, and the trigger blocks that. Tests need a fixture that drops the triggers, deletes and re-creates them (`_reset_decision_log()`), or a fresh DB file per test module. Production code never drops the triggers.

**Writer**, `backend/decision_log.py`:

```python
GENESIS = "0" * 64

def append(event: str, *, request_id: int, actor: Principal | str, action_name: str,
           payload: dict, bundle_hash: str | None, reason: str = "", tenant_id: str = "default") -> str:
    """Serialised per tenant (process lock + BEGIN IMMEDIATE on SQLite / pg_advisory_xact_lock on PG)."""

def verify(tenant_id: str = "default") -> VerifyResult        # ok, checked, first_bad_seq, error
def export_jsonl(tenant_id: str, since: str | None, until: str | None) -> Iterator[str]
def history(request_id: int) -> list[dict]
```

**Write points.** These are the only writers, enforced by a grep test:

| Event | Called from | Actor |
| --- | --- | --- |
| `REQUESTED` | `ApprovalQueue.request_approval` | `agent:<agent_id>` |
| `APPROVED` / `REJECTED` | `ApprovalQueue.resolve(..., principal)` | the human `Principal` |
| `CONSUMED` | `ApprovalQueue.consume` | `system` |
| `EXPIRED` | Phase 2 TTL sweeper | `system` |

`ApprovalQueue.resolve` gains a required keyword `principal: Principal`, and the REST handler passes `current_principal(request)`. For backward compatibility the internal default is `Principal("system", ("admin",))`, and it logs a warning.

**State update and log append share one transaction.** If the append fails, the status change rolls back.

**Resolve-once rule:** `resolve` only changes a row whose status is `PENDING`. Today any status can be overwritten, so this is a behaviour fix. Approving an already-`REJECTED` row returns 409.

**Export bundle** (`GET /api/governance/decisions/export?from=&to=&format=jsonl`):

```
hermes-decisions-<tenant>-<from>-<to>.zip
├── decisions.jsonl          # one canonical JSON row per line, in seq order
├── evidence/<request_id>.json   # redacted bundle_json for every referenced request
├── manifest.json            # {tenant, from, to, count, first_seq, last_seq, head_hash, exported_at, exported_by, schema_ver}
└── VERIFY.md                # how to run the verifier
```

**Offline verifier**, `scripts/verify_decision_log.py` (stdlib only, so an auditor can run it without Hermes):

- recomputes every `entry_hash` and checks the `prev_hash` linkage
- recomputes every evidence file's `bundle_hash` and checks it against the decision rows
- exit code 0 or 1, and prints the first broken seq

**Head anchoring (optional, off by default).** `DECISION_LOG_ANCHOR_CMD` runs a command with `head_hash` once a day, for example `git commit`, an RFC 3161 TSA client, or a write to WORM storage. It is pluggable and has no vendor lock-in.

### 3.3 API

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/governance/approvals/{id}` | adds `decisions: history(id)` |
| GET | `/api/governance/decisions?limit=&before_seq=` | paginated |
| GET | `/api/governance/decisions/verify` | `{ok, checked, head_hash, first_bad_seq}` |
| GET | `/api/governance/decisions/export` | zip stream. In Phase 3 it requires `audit:export`. |

### 3.4 Test plan (write first)

**`backend/tests/test_decision_log_unit.py`**

```python
import pytest, sqlite3
from backend import decision_log as dl
from backend.identity import Principal

ADMIN = Principal(subject="alice", roles=("admin",))

def _append(i, event="REQUESTED"):
    return dl.append(event, request_id=i, actor="agent:a", action_name="execute_command",
                     payload={"command": f"echo {i}"}, bundle_hash="b" * 64)

def test_first_entry_links_to_genesis():
    _append(1)
    rows = list(dl.history(1))
    assert rows[0]["prev_hash"] == dl.GENESIS

def test_chain_links():
    h1 = _append(1); _append(2)
    assert dl.history(2)[0]["prev_hash"] == h1

def test_verify_ok_on_clean_chain():
    for i in range(5): _append(i)
    r = dl.verify()
    assert r.ok and r.checked == 5

def test_update_blocked_by_storage():
    _append(1)
    with pytest.raises(Exception, match="append-only"):
        from backend.database import _execute
        _execute("UPDATE approval_decisions SET reason='x'")

def test_delete_blocked_by_storage():
    _append(1)
    with pytest.raises(Exception, match="append-only"):
        from backend.database import _execute
        _execute("DELETE FROM approval_decisions")

def test_verify_detects_tamper(tamper_decision_row):   # fixture drops trigger, edits row 3, restores trigger
    for i in range(5): _append(i)
    tamper_decision_row(seq=3, reason="forged")
    r = dl.verify()
    assert not r.ok and r.first_bad_seq == 3

def test_concurrent_appends_keep_linear_chain():
    import threading
    ts = [threading.Thread(target=_append, args=(i,)) for i in range(20)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert dl.verify().ok

def test_reason_is_pii_redacted():
    dl.append("REJECTED", request_id=1, actor=ADMIN, action_name="x", payload={}, bundle_hash=None,
              reason="call me +1 415 555 0100")
    assert "555" not in dl.history(1)[0]["reason"]
```

**`backend/tests/test_decision_log_wiring.py`**

- `test_gate_request_writes_REQUESTED_with_bundle_hash`
- `test_resolve_writes_APPROVED_with_principal_subject`
- `test_consume_writes_CONSUMED`
- `test_full_lifecycle_order_is_REQUESTED_APPROVED_CONSUMED`
- `test_resolve_twice_returns_false_and_logs_once`
- `test_status_and_log_atomic`: patch `dl.append` to raise, then assert the status is still `PENDING`.
- `test_only_governance_writes_decisions`: grep test. `INSERT INTO approval_decisions` appears only in `backend/decision_log.py`.

**`backend/tests/test_decision_log_api.py`**

- `test_resolve_records_local_admin_subject` (an OTP session gives subject `local-admin`)
- `test_resolve_records_jwt_sub` (signed HS256 JWT with `sub=bob`, using `JWT_SECRET` via monkeypatch)
- `test_resolve_rejected_then_approve_409`
- `test_export_zip_contains_manifest_and_verifies`: unzip, then run `scripts/verify_decision_log.py` through `subprocess` and expect exit 0.
- `test_export_respects_date_range`

**`backend/tests/test_verify_script_unit.py`**: the verifier runs on a hand-made JSONL fixture with no backend import. This guarantees the stdlib-only promise.

### 3.5 Acceptance

- Every status transition of an approval has exactly one decision row.
- `UPDATE` / `DELETE` on `approval_decisions` fails at the storage layer on SQLite and Postgres.
- A third party can verify an export with `python3 verify_decision_log.py export.zip` and no network.

---

## Phase 1 exit criteria

- [ ] PR 1: `canonical.py` + item 1a (schema, stub capture, hash), with tests.
- [ ] PR 2: `identity.py` + item 3, with tests.
- [ ] PR 3: item 1b API + item 2 UI + WS events, with tests.
- [ ] PR 4: item 1c in-flight context, with tests.
- [ ] Demo script in `docs/guide/approvals.md`: trigger, review evidence, approve, run once, export, verify.
