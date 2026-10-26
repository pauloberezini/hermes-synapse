# Phase 2: Less approval fatigue (1–2 months)

Items: **4** Risk tiers for tools · **5** Read-only by default at the connection level · **6** Intent records for multi-step actions.

The goal of this phase is fewer prompts that matter more. **Every MCP tool is gated today** (`_requires_approval` returns True for anything in `mcp_tool_to_server`), so a read like `get_spot_prices` interrupts the human as often as `place_order` does. With few prompts, people read them.

Order: 4 → 5 → 6. Item 5 uses item 4's classifier as the second line of defence. Item 6 uses tiers to find the irreversible step.

---

## Item 4: Risk tiers for tools

### 4.1 Tiers and categories

```python
class Tier(IntEnum):
    READ = 0       # auto-pass, logged
    WRITE = 1      # approval required
    CRITICAL = 2   # approval + written reason (≥ 10 chars), never auto-approved, never batched

class Category(StrEnum):
    MONEY = "money"            # payments, orders, transfers, trades
    DELETE = "delete"          # irreversible removal
    EXTERNAL_SEND = "external_send"   # email, message, post, webhook to a third party
    EXEC = "exec"              # shell / code execution
    NONE = "none"

CRITICAL_CATEGORIES = {Category.MONEY, Category.DELETE, Category.EXTERNAL_SEND}
```

Rule: `tier = CRITICAL if category in CRITICAL_CATEGORIES else declared_tier`. A tool cannot be marked `money` and also `READ`. The classifier raises `PolicyConflict`, and startup fails loudly.

### 4.2 Classification sources (precedence high → low)

| # | Source | Example | Can lower a tier? |
| --- | --- | --- | --- |
| 1 | Operator policy (`tool_policies` table / `data/tool_policy.yaml`) | `example_broker.place_order: {tier: CRITICAL, category: money}` | **Yes, except below a CRITICAL category** |
| 2 | Plugin hook `classify_tool(name, schema) -> ToolRisk \| None` | A plugin marks its broker tools | No |
| 3 | MCP tool annotations (spec 2025-03-26: `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) | `readOnlyHint: true` → READ; `destructiveHint: true` → CRITICAL/delete | No (hints are untrusted, so they can only **raise** a tier, except the `readOnlyHint` path below) |
| 4 | Built-in table in `backend/risk.py` | `execute_command: WRITE/exec`, `delete_todoist_task: CRITICAL/delete`, `get_weather: READ` | — |
| 5 | Name heuristics | `^(get_|list_|search_|read_|fetch_)` → READ candidate; `(delete|remove|drop|send|pay|transfer|order|buy|sell)` → CRITICAL candidate | No |
| 6 | Default | — | **WRITE (fail closed)** |

**`readOnlyHint` trust rule.** An MCP server's `readOnlyHint: true` sets READ **only if** that server's connection is `access: read` (item 5) **or** an operator policy confirms it. Otherwise the tool stays WRITE. This stops a malicious server from labelling `transfer_funds` as read-only.

### 4.3 Module

```python
# backend/risk.py
@dataclass(frozen=True)
class ToolRisk:
    tier: Tier
    category: Category
    source: str          # "policy" | "plugin" | "mcp_annotation" | "builtin" | "heuristic" | "default"
    requires_reason: bool

def classify(name: str, *, server: str | None = None, schema: dict | None = None,
             annotations: dict | None = None, tenant_id: str = "default") -> ToolRisk
def policy_version(tenant_id: str = "default") -> int     # monotonically increasing; used by item 9
```

`backend/governance.py`:

```python
def _requires_approval(action_name) -> bool          # REMOVED
def gate_tool(agent_id, action_name, payload):
    risk = classify(action_name, server=mcp_tool_to_server.get(action_name), annotations=_annotations(action_name))
    if risk.tier is Tier.READ:
        record_tool_call(agent_id, action_name, payload, tier=risk.tier)  # call log (item 10), not the decision log
        return None
    ...  # existing approval path; request row stores tier + category + requires_reason
```

`record_tool_call` writes to a minimal `tool_calls` table (`id, tenant_id, agent_id, tool_name, server, tier, payload_hash, started_at`), which is introduced here. Item 10 extends that same table into the full gateway call log. A READ call skips the approval, but it still leaves a record.

`HIGH_RISK_TOOLS` stays as a deprecated alias for one release. Each name in it is seeded into the built-in table at WRITE or higher.

### 4.4 Data model

```sql
ALTER TABLE approval_requests ADD COLUMN tier TEXT;              -- READ|WRITE|CRITICAL
ALTER TABLE approval_requests ADD COLUMN category TEXT;
ALTER TABLE approval_requests ADD COLUMN requires_reason INTEGER DEFAULT 0;
ALTER TABLE approval_requests ADD COLUMN expires_at TEXT;        -- PENDING TTL (default 24h; CRITICAL 1h)

CREATE TABLE IF NOT EXISTS tool_policies (
    tenant_id   TEXT NOT NULL DEFAULT 'default',
    tool_name   TEXT NOT NULL,            -- exact, or "server.*" glob
    tier        TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'none',
    note        TEXT,
    updated_by  TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    PRIMARY KEY (tenant_id, tool_name)
);
CREATE TABLE IF NOT EXISTS policy_versions (tenant_id TEXT PRIMARY KEY, version INTEGER NOT NULL);
```

Every write to `tool_policies` bumps `policy_versions.version` in the same transaction, and appends a `POLICY_CHANGED` row to the decision log (item 3). The `event` column is free text, so it can take this new value.

### 4.5 Resolve rule for CRITICAL

`POST /resolve` with `decision=APPROVED` on a `requires_reason` row and a `resolver_note` stripped to fewer than 10 chars → **422** `{"error":"written_reason_required"}`. A rejection never needs a reason.

### 4.6 TTL sweeper

A `scheduler.py` job runs every minute. It moves `PENDING` rows past `expires_at` to `EXPIRED` and appends an `EXPIRED` decision. A later identical tool call creates a new request.

### 4.7 API and UI

- `GET /api/governance/tools/risk`: the classified inventory `[{name, server, tier, category, source}]`.
- `PUT /api/governance/tools/{name}/policy`: set the override. Phase 3 requires `policy:write`.
- Modal: tier chip (`READ` grey, `WRITE` amber, `CRITICAL` red). CRITICAL rows show a required "Written reason" textarea, and Approve stays disabled until it has 10 or more chars.
- New **Tools → Risk** table in `ToolsTab.tsx`, with an inline override dropdown.

### 4.8 Test plan (write first)

**`backend/tests/test_risk_classifier_unit.py`**

```python
import pytest
from backend.risk import classify, Tier, Category, PolicyConflict

@pytest.mark.parametrize("name,tier", [
    ("get_weather", Tier.READ), ("get_system_stats", Tier.READ),
    ("execute_command", Tier.WRITE), ("create_obsidian_note", Tier.WRITE),
    ("delete_todoist_task", Tier.CRITICAL),
])
def test_builtin_table(name, tier):
    assert classify(name).tier is tier

def test_unknown_tool_defaults_to_write():
    r = classify("frobnicate"); assert r.tier is Tier.WRITE and r.source == "default"

@pytest.mark.parametrize("cat", [Category.MONEY, Category.DELETE, Category.EXTERNAL_SEND])
def test_critical_categories_force_reason(cat, set_policy):
    set_policy("x_tool", tier="WRITE", category=cat.value)
    r = classify("x_tool"); assert r.tier is Tier.CRITICAL and r.requires_reason

def test_policy_cannot_mark_money_as_read(set_policy):
    with pytest.raises(PolicyConflict):
        set_policy("pay", tier="READ", category="money")

def test_mcp_readonly_hint_ignored_on_write_connection():
    r = classify("transfer_funds", server="bank", annotations={"readOnlyHint": True})
    assert r.tier is not Tier.READ

def test_mcp_readonly_hint_trusted_on_read_connection(read_only_server):
    read_only_server("feeds")
    assert classify("list_items", server="feeds", annotations={"readOnlyHint": True}).tier is Tier.READ

def test_destructive_hint_raises_to_critical():
    r = classify("purge", server="s", annotations={"destructiveHint": True})
    assert r.tier is Tier.CRITICAL and r.category is Category.DELETE

def test_heuristic_never_lowers_policy(set_policy):
    set_policy("get_secret_and_send", tier="CRITICAL", category="external_send")
    assert classify("get_secret_and_send").tier is Tier.CRITICAL

def test_policy_write_bumps_version(set_policy):
    from backend.risk import policy_version
    v0 = policy_version(); set_policy("a", tier="WRITE"); assert policy_version() == v0 + 1
```

**`backend/tests/test_risk_gate_wiring.py`**

- `test_read_tool_runs_without_request`: `get_weather` makes no `approval_requests` row.
- `test_mcp_read_tool_no_longer_prompts`: register a fake MCP tool with `readOnlyHint` on a read connection, then call `execute_tool` and see no request.
- `test_mcp_unknown_tool_still_prompts`: a regression guard for today's safety.
- `test_critical_request_row_has_requires_reason`
- `test_existing_single_use_contract_holds`: rerun the existing `test_high_risk_tool_waits_for_human_then_runs_once` scenario.

**`backend/tests/test_risk_api.py`**

- `test_approve_critical_without_reason_422`
- `test_approve_critical_with_reason_ok_and_logged` (the decision row `reason` holds the text)
- `test_reject_critical_without_reason_ok`
- `test_inventory_lists_tier_and_source`
- `test_ttl_sweeper_expires_and_logs` (freeze time via `monkeypatch` on `datetime`)

**Frontend `ApprovalsModal.test.tsx` additions**

- `critical row disables Approve until reason ≥ 10 chars`
- `tier chip renders with accessible label`

### 4.9 Acceptance

- In a recorded 1-hour BCM desk session, the approval prompt count drops by 80 % or more compared with the baseline, and no WRITE or CRITICAL call slips through. Count it from `approval_requests` before and after.

---

## Item 5: Read-only by default at the connection level

### 5.1 Principle

**The prompt is not a security boundary.** Write capability must be:

1. **Off by default** for every new connection.
2. **Explicitly enabled** per tool by an operator (audited).
3. **Enforced below the LLM**: by Hermes refusing to register or execute the tool, **and** by the downstream service through scoped credentials.

### 5.2 Config schema (`backend/data/mcp_config.json`, backwards compatible)

```jsonc
{
  "mcpServers": {
    "example_broker": {
      "url": "https://mcp.example.test/trading",
      "headers": { "Authorization": "Bearer ${MCP_READ_TOKEN}" },
      "access": "read",                         // NEW: "read" (default) | "write"
      "write_tools": [],                        // NEW: explicit allowlist when access=write
      "write_headers": { "Authorization": "Bearer ${MCP_WRITE_TOKEN}" }   // NEW: optional separate creds
    }
  }
}
```

- `${VAR}` interpolation happens at load time. A missing variable makes the server fail to start with a clear error, and the secret is never logged. **This also removes the committed token flagged in the README.**
- A missing `access` key is treated as `"read"`. *Migration:* on first start after upgrade, existing servers get `access: "write"` with `write_tools: ["*"]` **and** a startup banner plus a UI warning. Users are not silently broken, but they see a warning until they narrow the list. Set `HERMES_STRICT_CONNECTIONS=1` to skip that grace step.

### 5.3 Enforcement layers

| Layer | Mechanism | Test |
| --- | --- | --- |
| L1 Registration | `init_mcp_servers` registers a tool into `TOOLS_SCHEMA` only if `classify(...).tier is READ` **or** the tool is in `write_tools`. Unregistered tools are invisible to the LLM. | unit |
| L2 Execution | `execute_tool` → `connection_guard(name)` returns `{"error":"write_disabled","tool":…}` **before** `gate_tool`, even if the LLM invents the name. Approval cannot override it. | unit + wiring |
| L3 Credentials | Read calls use `headers`, and writes use `write_headers` (if set). With no write creds, a write call fails at the service. | wiring with fake HTTP server |
| L4 Service | Docs plus a reference: Postgres `CREATE ROLE hermes_ro … GRANT SELECT`, a GitHub fine-grained token with read-only scope, an IMAP read-only account. `docs/guide/connections.md` has a recipe table. | docs |

Built-in (non-MCP) tools get the same treatment through `data/builtin_connections.yaml`. For example, `obsidian: {access: write, write_tools: [create_obsidian_note]}`. Defaults keep today's behaviour for built-ins, so nothing regresses. New built-in integrations ship as `read`.

### 5.4 Audit

Enabling or disabling a write tool goes through `PUT /api/governance/connections/{server}`. It persists to config through an atomic write (temp file + rename), appends `CONNECTION_CHANGED` to the decision log, and bumps `policy_version`, which item 9 uses.

### 5.5 Module

```python
# backend/connections.py
@dataclass(frozen=True)
class ConnectionPolicy:
    server: str
    access: Literal["read", "write"]
    write_tools: frozenset[str]        # "*" allowed only during migration grace
def load_policies(config: dict) -> dict[str, ConnectionPolicy]
def interpolate_env(obj, env=os.environ) -> obj           # raises MissingEnv(var)
def is_write_allowed(server: str, tool: str) -> bool
def connection_guard(tool_name: str) -> Optional[str]     # JSON error or None
```

### 5.6 Test plan (write first)

**`backend/tests/test_connections_unit.py`**

```python
import pytest
from backend.connections import interpolate_env, load_policies, MissingEnv

def test_env_interpolation():
    assert interpolate_env({"h": "Bearer ${T}"}, env={"T": "abc"}) == {"h": "Bearer abc"}

def test_missing_env_raises_without_leaking():
    with pytest.raises(MissingEnv) as e:
        interpolate_env({"h": "${NOPE}"}, env={})
    assert "NOPE" in str(e.value)

def test_missing_access_defaults_to_read_in_strict_mode(monkeypatch):
    monkeypatch.setenv("HERMES_STRICT_CONNECTIONS", "1")
    p = load_policies({"mcpServers": {"s": {"url": "x"}}})["s"]
    assert p.access == "read" and not p.write_tools

def test_legacy_server_gets_grace_write_star(monkeypatch):
    monkeypatch.delenv("HERMES_STRICT_CONNECTIONS", raising=False)
    p = load_policies({"mcpServers": {"s": {"url": "x"}}})["s"]
    assert p.access == "write" and "*" in p.write_tools

def test_write_tools_ignored_when_access_read():
    p = load_policies({"mcpServers": {"s": {"url": "x", "access": "read", "write_tools": ["place_order"]}}})["s"]
    assert not p.write_tools
```

**`backend/tests/test_connections_mcp_wiring.py`**: fake `MCPServerClient` with tools `list_positions` (`readOnlyHint`) and `place_order`:

- `test_read_connection_registers_only_read_tools` (checks `TOOLS_SCHEMA`)
- `test_execute_unregistered_write_tool_returns_write_disabled`
- `test_write_disabled_beats_approval` (pre-insert an APPROVED request for `place_order`; it is still blocked, and no `CONSUMED`)
- `test_write_call_uses_write_headers` (a fake HTTP transport captures the header)
- `test_enable_write_tool_via_api_logs_and_bumps_version`

**`backend/tests/test_no_committed_secrets.py`**: scans `backend/data/*.json` and `*.yaml` for `Bearer [A-Za-z0-9._-]{20,}` with no `${`. This guards the regression.

### 5.7 Acceptance

- With a fresh install and strict mode on, adding any MCP server exposes **zero** write tools until an operator enables one.
- The committed cTrader token is gone from git HEAD. It must also be **rotated**, because history still holds it.

---

## Item 6: Intent records for multi-step actions

### 6.1 Problem

A multi-step action ("close position A, open B, notify client") can fail halfway. A retry can then double-charge, and the irreversible step can run before a reversible one fails. Today nothing records the sequence: each `execute_tool` call is independent.

### 6.2 Model

```sql
CREATE TABLE IF NOT EXISTS intents (
    id            TEXT PRIMARY KEY,         -- uuid4
    tenant_id     TEXT NOT NULL DEFAULT 'default',
    session_id    TEXT NOT NULL,
    agent_id      TEXT NOT NULL,
    goal          TEXT NOT NULL,            -- human sentence
    status        TEXT NOT NULL,            -- DRAFT|AWAITING_APPROVAL|RUNNING|SUCCEEDED|FAILED|COMPENSATING|COMPENSATED|CANCELLED
    plan_hash     TEXT NOT NULL,            -- canonical hash of steps (tool+payload_key+order)
    approval_id   INTEGER,                  -- one approval for the whole intent (WRITE/CRITICAL steps)
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS intent_steps (
    intent_id        TEXT NOT NULL REFERENCES intents(id),
    idx              INTEGER NOT NULL,
    tool_name        TEXT NOT NULL,
    payload          TEXT NOT NULL,
    tier             TEXT NOT NULL,
    irreversible     INTEGER NOT NULL DEFAULT 0,
    idempotency_key  TEXT NOT NULL UNIQUE,
    compensation     TEXT,                  -- JSON {tool_name, payload} or NULL
    status           TEXT NOT NULL,         -- PENDING|RUNNING|SUCCEEDED|FAILED|SKIPPED|COMPENSATED
    result           TEXT,                  -- redacted, capped 4 KiB
    attempts         INTEGER NOT NULL DEFAULT 0,
    started_at       TEXT, finished_at TEXT,
    PRIMARY KEY (intent_id, idx)
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key          TEXT PRIMARY KEY,
    tool_name    TEXT NOT NULL,
    status       TEXT NOT NULL,             -- IN_FLIGHT|DONE
    result       TEXT,
    created_at   TEXT NOT NULL
);
```

### 6.3 Rules

1. **Idempotency key.** `sha256(canonical([intent_id, idx, tool_name, payload_key]))`. Every step whose category is `money`, or whose tool name matches create / charge / order / send, **must** carry one. The executor reserves the key (`INSERT … IF NOT EXISTS` as `IN_FLIGHT`) before calling the tool:
   - key `DONE` → return the stored result, no call.
   - key `IN_FLIGHT` (crash mid-call) → step `FAILED` with `needs_reconciliation`. **No automatic retry** for money/irreversible steps; a human must decide.
   - The key is forwarded downstream: MCP `params._meta.idempotencyKey`. A built-in tool gets it through an `idempotency_key` kwarg if its signature accepts one. Plugin brokers map it to their native client order id.
2. **Irreversible last.** `validate_plan(steps)` rejects any plan where an `irreversible=True` step is followed by another step, and rejects more than one irreversible step. A step is irreversible if its tier is CRITICAL with category `money`, `delete` or `external_send`, or if the operator policy says so.
3. **One approval per intent.** The WRITE/CRITICAL steps are summarised into one approval request, with `action_name="intent"` and `payload={intent_id, plan_hash, steps:[…]}`. Its evidence bundle (item 1) lists every step. Approving binds `plan_hash`. Any change to the plan (args, order) means a new hash and a new approval. Inside an approved intent, `gate_tool` sees `intent_ctx`, and lets the call through only if `(tool, payload_key)` matches the next PENDING step of the approved `plan_hash`.
4. **Compensation.** If step *k* fails, the executor runs `compensation` for steps *k-1 … 0* in reverse, but only for SUCCEEDED steps that define one. Compensation calls also go through the gate. They are pre-approved as part of the intent, and they are logged.
5. **Each step status change** appends to the decision log as `INTENT_STEP` with `{intent_id, idx, status}`.

### 6.4 Module and agent surface

```python
# backend/intents.py
def create_intent(session_id, agent_id, goal, steps: list[StepSpec]) -> Intent        # validates + hashes
def validate_plan(steps) -> None                                                    # raises PlanError
async def run_intent(intent_id) -> Intent                                           # resumable
def resume_incomplete() -> list[str]                                                # called at startup
intent_ctx: ContextVar[Optional[IntentCursor]]
```

The new agent tool `propose_intent(goal, steps[])` is **READ tier**, because it only drafts. The orchestrator uses it when the plan has two or more WRITE+ tool calls. A single WRITE call still goes through the plain gate, so simple flows stay as they are.

UI: in the Task Board, an intent card lists its steps with status icons. The approval modal renders an intent request as a numbered step list, with the irreversible step marked "⚠ runs last, cannot be undone".

### 6.5 Test plan (write first)

**`backend/tests/test_intents_unit.py`**

```python
import pytest
from backend.intents import validate_plan, PlanError, StepSpec, idem_key

def S(tool, irr=False, **p): return StepSpec(tool_name=tool, payload=p, irreversible=irr)

def test_irreversible_must_be_last():
    with pytest.raises(PlanError, match="irreversible step must be last"):
        validate_plan([S("transfer", irr=True), S("notify")])

def test_only_one_irreversible():
    with pytest.raises(PlanError):
        validate_plan([S("a", irr=True), S("b", irr=True)])

def test_valid_plan_passes():
    validate_plan([S("reserve"), S("charge", irr=True)])

def test_idem_key_deterministic_and_order_sensitive():
    assert idem_key("i", 0, "charge", {"a": 1, "b": 2}) == idem_key("i", 0, "charge", {"b": 2, "a": 1})
    assert idem_key("i", 0, "charge", {}) != idem_key("i", 1, "charge", {})

def test_plan_hash_changes_on_arg_change():
    from backend.intents import plan_hash
    assert plan_hash([S("a", x=1)]) != plan_hash([S("a", x=2)])
```

**`backend/tests/test_intents_executor_wiring.py`**: fake tools registered via the `execute_named_tool` plugin hook with call counters:

- `test_happy_path_runs_in_order_and_succeeds`
- `test_single_approval_for_whole_intent` (exactly one `approval_requests` row, `action_name='intent'`)
- `test_changed_args_after_approval_requires_new_approval`
- `test_gate_blocks_out_of_plan_call_inside_intent` (the agent tries an extra tool mid-intent and is blocked)
- `test_retry_after_success_returns_cached_result_no_second_call` (counter == 1)
- `test_crash_in_flight_marks_needs_reconciliation_no_auto_retry` (simulate `IN_FLIGHT` key, then call `resume_incomplete()`)
- `test_failure_triggers_reverse_compensation_only_for_succeeded_steps`
- `test_irreversible_not_executed_when_prior_step_fails`
- `test_idempotency_key_forwarded_to_mcp_meta` (fake MCP client captures `params`)
- `test_every_step_transition_in_decision_log`

**`backend/tests/test_intents_orchestrator_cross.py`**

- `test_planner_with_two_writes_creates_intent`
- `test_planner_with_one_write_uses_plain_gate`

### 6.6 Acceptance

- Kill the backend between step 1 and step 2 of a two-step money intent and restart it. Step 1 is not repeated, and step 2 waits for reconciliation. Verify against a fake broker in the cross test.

---

## Phase 2 exit criteria

- [ ] Prompt volume is cut (metric in 4.9) with zero unsafe pass-through.
- [ ] Fresh installs expose no write tools by default (strict mode).
- [ ] Multi-step money flows are idempotent and ordered, with the irreversible step last, as proven by the cross tests.
