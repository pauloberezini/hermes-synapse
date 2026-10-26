# Phase 3: Team readiness (2–3 months)

Items: **7** RBAC · **8** Multi-tenant isolation · **9** Access revocation mid-session.

Builds on `backend/identity.py::Principal` (Phase 1), `risk.policy_version` (Phase 2) and the decision log (Phase 1).

---

## Item 7: RBAC (role-based access control)

### 7.1 Current state

- `backend/auth.py` has `ROLE_HIERARCHY` (admin 100 / editor 50 / operator 30 / viewer 10), `get_user_roles`, and `check_rbac_permission`. **No route calls `check_rbac_permission`.** The global middleware only checks that *some* valid session exists.
- Local OTP sessions are hard-wired to `["admin"]`.
- A plain hierarchy cannot express "may approve but not change policy". Approvers and admins need **separate** permissions, not just a higher number.

### 7.2 Design: permissions, not levels

```python
# backend/rbac.py
class Perm(StrEnum):
    APPROVALS_READ     = "approvals:read"
    APPROVALS_RESOLVE  = "approvals:resolve"
    APPROVALS_RESOLVE_CRITICAL = "approvals:resolve_critical"
    AUDIT_READ         = "audit:read"
    AUDIT_EXPORT       = "audit:export"
    POLICY_READ        = "policy:read"
    POLICY_WRITE       = "policy:write"          # tool tiers, connections
    AGENTS_WRITE       = "agents:write"          # create/edit subagents
    CHAT               = "chat:use"
    SETTINGS_WRITE     = "settings:write"
    TENANT_ADMIN       = "tenant:admin"          # manage members/roles within tenant
    PLATFORM_ADMIN     = "platform:admin"        # cross-tenant (operator of the install)

ROLE_PERMS: dict[str, frozenset[Perm]] = {
    "viewer":   {APPROVALS_READ, AUDIT_READ, POLICY_READ, CHAT},
    "operator": viewer | {AGENTS_WRITE},
    "approver": {APPROVALS_READ, APPROVALS_RESOLVE, AUDIT_READ, POLICY_READ, CHAT},
    "senior_approver": approver | {APPROVALS_RESOLVE_CRITICAL},
    "auditor":  {APPROVALS_READ, AUDIT_READ, AUDIT_EXPORT, POLICY_READ},
    "admin":    everything except PLATFORM_ADMIN and APPROVALS_RESOLVE*,   # separation of duties
    "owner":    admin | {APPROVALS_RESOLVE, APPROVALS_RESOLVE_CRITICAL, TENANT_ADMIN},
    "platform_admin": {PLATFORM_ADMIN, TENANT_ADMIN, AUDIT_READ},
}
LEGACY_ROLE_MAP = {"editor": "operator"}

def perms_for(principal: Principal) -> frozenset[Perm]
def require(perm: Perm) -> Callable   # FastAPI dependency; 403 {"error":"forbidden","perm":perm}
```

**Separation of duties (configurable, on by default):**

- `admin` can change policy but **cannot approve**. Approving a request needs `approver` or `owner`.
- **No self-approval:** the principal who triggered the turn that produced the request (`approval_requests.requested_by`, set from the chat session principal) cannot resolve it. 403 `self_approval_forbidden`.
- **CRITICAL** tier needs `approvals:resolve_critical`. Optional `HERMES_CRITICAL_QUORUM=2` requires two distinct approvers. The request stays `PENDING` until the second one, and each approval is logged.

**Single-user local mode (must keep working, for OSS reproducibility):** the OTP session maps to `Principal("local-admin", ("owner",))`. `owner` holds every permission, so solo users see no change. A self-approval of their own chat is allowed only when `auth_method == "otp"` and `HERMES_SOLO_MODE` is unset or 1. Multi-user deployments set `HERMES_SOLO_MODE=0`.

### 7.3 Role storage

```sql
CREATE TABLE IF NOT EXISTS role_bindings (
    tenant_id  TEXT NOT NULL DEFAULT 'default',
    subject    TEXT NOT NULL,          -- JWT sub or email
    role       TEXT NOT NULL,
    granted_by TEXT NOT NULL,
    granted_at TEXT NOT NULL,
    PRIMARY KEY (tenant_id, subject, role)
);
ALTER TABLE approval_requests ADD COLUMN requested_by TEXT;
ALTER TABLE approval_requests ADD COLUMN approvals_needed INTEGER DEFAULT 1;
```

Effective roles = JWT claim roles ∪ `role_bindings` for (tenant, subject). An operator can therefore grant `approver` without touching the IdP. Role changes append `ROLE_CHANGED` to the decision log.

### 7.4 Route permission map

| Route | Perm |
| --- | --- |
| `GET /api/governance/approvals*` | `approvals:read` |
| `POST /api/governance/approvals/{id}/resolve` | `approvals:resolve` (+ `resolve_critical` for CRITICAL) |
| `GET /api/governance/decisions*` | `audit:read` |
| `GET /api/governance/decisions/export` | `audit:export` |
| `PUT /api/governance/tools/*`, `/connections/*` | `policy:write` |
| `POST /api/governance/budget/*` | `settings:write` |
| `POST/PUT/DELETE /api/subagents*` | `agents:write` |
| `/api/chat`, websocket chat | `chat:use` |
| `/api/admin/roles*` (new) | `tenant:admin` |

**Every** `/api/*` route must be in the map. A test walks `app.routes` and fails on any unmapped route, so a new endpoint cannot ship without a permission.

### 7.5 UI

- `GET /api/me` → `{subject, roles, perms, tenant_id}`. The frontend hides or disables controls by `perms`. **The server still enforces everything.**
- Approve/Reject is hidden without `approvals:resolve`. A CRITICAL row shows "needs senior approver" when the permission is missing.
- New **Settings → Members** page (tenant:admin) lists role bindings and lets an admin add or remove them.

### 7.6 Test plan (write first)

**`backend/tests/test_rbac_unit.py`**

```python
import pytest
from backend.identity import Principal
from backend.rbac import perms_for, Perm

P = lambda *roles, **kw: Principal(subject=kw.get("sub", "u"), roles=roles, auth_method=kw.get("am", "jwt"))

def test_admin_cannot_resolve():
    assert Perm.APPROVALS_RESOLVE not in perms_for(P("admin"))

def test_approver_cannot_write_policy():
    assert Perm.POLICY_WRITE not in perms_for(P("approver"))

def test_critical_requires_senior():
    assert Perm.APPROVALS_RESOLVE_CRITICAL not in perms_for(P("approver"))
    assert Perm.APPROVALS_RESOLVE_CRITICAL in perms_for(P("senior_approver"))

def test_legacy_editor_maps_to_operator():
    assert perms_for(P("editor")) == perms_for(P("operator"))

def test_unknown_role_grants_nothing():
    assert perms_for(P("superhero")) == frozenset()

def test_local_otp_is_owner():
    from backend.identity import principal_from_token
    from backend.auth import create_session
    p = principal_from_token(create_session())
    assert "owner" in p.roles and p.subject == "local-admin"
```

**`backend/tests/test_rbac_api.py`** (signed JWTs per role, `JWT_SECRET` via monkeypatch):

- `test_viewer_resolve_403`
- `test_approver_resolve_200_and_logged_with_sub`
- `test_admin_resolve_403_separation_of_duties`
- `test_self_approval_403_in_team_mode` (`HERMES_SOLO_MODE=0`)
- `test_self_approval_allowed_in_solo_otp_mode`
- `test_critical_needs_senior_403_for_approver`
- `test_quorum_two_requires_distinct_approvers` (the same sub approving twice → still PENDING)
- `test_role_binding_grants_approver_without_idp_claim`
- `test_every_api_route_has_permission` (walks `app.routes`, compares to `ROUTE_PERMS`)
- `test_me_endpoint_returns_perms`

**Frontend `ApprovalsModal.test.tsx`**

- `hides approve buttons without approvals:resolve`
- `shows needs-senior notice on critical without perm`

### 7.7 Acceptance

- A 3-person pilot (owner, approver, viewer) can run end to end, and every forbidden action returns 403 and leaves no state change.

---

## Item 8: Multi-tenant isolation

### 8.1 Model

A **tenant** is a team or customer. Each tenant has its own policies, approvals, decision log chain, agents, sessions, memory and connections. One install can host many tenants. A solo install has a single tenant, `default`.

Isolation level for v1: **shared database, `tenant_id` column, enforced in one repository layer.** On Postgres, also use **Row-Level Security**. Database-per-tenant is out of scope, but the `DatabaseBackend` abstraction leaves room for it later.

### 8.2 Tenant resolution

```python
# backend/tenancy.py
tenant_ctx: ContextVar[str] = ContextVar("hermes_tenant", default="default")

def resolve_tenant(principal: Principal, request: Request) -> str:
    """JWT claim `tenant` / `org_id` → X-Hermes-Tenant header (only if principal is member) → 'default'."""

@contextmanager
def as_tenant(tenant_id: str): ...   # for scheduler, telegram bot, mesh inbound
```

- The middleware sets `tenant_ctx` per request. Websocket connections set it once at connect.
- Background jobs (`scheduler.py`, `bcm` session scheduler, Telegram `bot.py`) **must** wrap work in `as_tenant(...)`. A job definition row stores its `tenant_id`.
- Telegram: map `chat_id → tenant_id` in a `channel_bindings` table. An unbound chat falls back to `default` only in solo mode. Otherwise the bot refuses.

### 8.3 Tables that gain `tenant_id TEXT NOT NULL DEFAULT 'default'`

`approval_requests, approval_evidence (via request), approval_decisions (already), tool_policies (already), policy_versions (already), role_bindings (already), intents, intent_steps (via intent), idempotency_keys, tool_calls, messages, session_metadata, subagents, subagent_memory, decision_logs, tasks, app_settings, distilled_skills, graph_nodes, graph_edges, rss_*`, plus connection config, which moves from a file to the `connections` table with `tenant_id` while `mcp_config.json` stays as the seed for `default`.

Composite indexes start with `tenant_id`. Unique constraints become `(tenant_id, <old key>)`.

### 8.4 Enforcement: one choke point

Raw SQL is spread across `database.py`, `governance.py`, `mesh.py` and others. Adding `WHERE tenant_id = ?` by hand in every place will miss some. Enforcement therefore works in three layers:

1. **`TenantScopedBackend`.** A wrapper around `DatabaseBackend.connect()`. On Postgres it runs `SET LOCAL app.tenant_id = %s` on each connection, and **RLS policies** do the filtering:
   ```sql
   ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY;
   CREATE POLICY tenant_isolation ON approval_requests
     USING (tenant_id = current_setting('app.tenant_id'))
     WITH CHECK (tenant_id = current_setting('app.tenant_id'));
   ```
   The app role is not the table owner and has no `BYPASSRLS`.
2. **SQLite (dev / solo).** It has no RLS, so code-level scoping applies: every repository function takes its tenant from `tenant_ctx`, and **a static test** (below) fails the build on any `SELECT|UPDATE|DELETE` against a tenant table without `tenant_id` in the WHERE clause.
3. **Per-tenant hash chains.** `decision_log.append` links within `tenant_id`, and `verify(tenant)` checks one chain. An export contains exactly one tenant.

Caches and in-memory registries keyed by `session_id` (`mcp_clients`, `agent_factory` caches, Qdrant collections) are keyed by `(tenant_id, …)`. RAG / Qdrant gets either one collection per tenant or a `tenant_id` payload filter that is **always** applied. A wrapper enforces it, and there is a test for it.

### 8.5 Migration

- One idempotent migration adds the columns with default `'default'`, backfills existing rows, and adds the indexes.
- Postgres RLS is enabled behind `HERMES_RLS=1` for one release, then on by default.

### 8.6 Test plan (write first)

**`backend/tests/test_tenancy_unit.py`**

- `test_default_tenant_when_no_claim`
- `test_jwt_tenant_claim_wins`
- `test_header_tenant_rejected_if_not_member` (403)
- `test_as_tenant_restores_previous`
- `test_contextvar_isolated_across_asyncio_tasks`

**`backend/tests/test_tenancy_isolation_api.py`** (two JWTs: `tenant=A`, `tenant=B`)

```python
def test_tenant_b_cannot_see_tenant_a_approvals(client, jwt_for):
    a, b = jwt_for(sub="alice", tenant="A", roles=["owner"]), jwt_for(sub="bob", tenant="B", roles=["owner"])
    with as_tenant("A"):
        rid = json.loads(execute_tool("execute_command", {"command": "ls"}, chat_id="s"))["request_id"]
    assert client.get("/api/governance/approvals", headers=auth(b)).json() == []
    assert client.get(f"/api/governance/approvals/{rid}", headers=auth(b)).status_code == 404   # not 403: no existence leak
    assert client.post(f"/api/governance/approvals/{rid}/resolve", json={"decision": "APPROVED"}, headers=auth(b)).status_code == 404
```

- `test_policies_are_per_tenant` (the same tool is READ in A and WRITE in B)
- `test_decision_chains_independent_and_each_verifies`
- `test_export_contains_only_one_tenant`
- `test_scheduler_job_runs_in_its_tenant`
- `test_telegram_unbound_chat_refused_in_team_mode`
- `test_rag_search_never_returns_other_tenant_docs`

**`backend/tests/test_tenancy_sql_static.py`**: parses every SQL string literal in `backend/**/*.py` except `bcm/` and tests (`ast` walk over `Constant` nodes containing SELECT/UPDATE/DELETE). For each statement that touches a table in `TENANT_TABLES`, it asserts `tenant_id` appears. An allowlist covers migrations.

**`backend/tests/test_tenancy_rls_pg.py`**: `@pytest.mark.postgres`, skipped without `TEST_DATABASE_URL`. It runs a raw `SELECT * FROM approval_requests` with `app.tenant_id='B'` and expects only B's rows. This proves RLS works even when code-level scoping is bypassed.

### 8.7 Acceptance

- Two pilot customers on one install cannot see each other's approvals, logs, agents or memory. This is proven both by the API tests and by the Postgres RLS test with code-level scoping bypassed.

---

## Item 9: Access revocation mid-session

### 9.1 Problem

An agent session can run for hours. If a permission is revoked mid-session (a connection is set back to read-only, a document is unshared, a user loses a role, a tool is re-tiered), data already pulled into the context window stays there, and the agent keeps acting on it.

### 9.2 Design: provenance-tagged context chunks

Every piece of content that enters an LLM prompt from outside the system prompt is wrapped in a chunk:

```python
# backend/provenance.py
@dataclass(frozen=True)
class ContextChunk:
    chunk_id: str
    tenant_id: str
    source_kind: Literal["tool_result", "rag_doc", "upload", "mcp_resource", "mesh_peer", "user"]
    source_ref: str            # e.g. "mcp:example_broker/get_positions", "rag:doc/123", "upload:sha256…"
    principal_subject: str     # on whose authority it was fetched
    policy_version: int        # risk/connection policy version at fetch time (tenant-scoped)
    acl_epoch: int             # source ACL epoch at fetch time (see 9.3)
    fetched_at: str
    content: str

class ProvenanceLedger:            # per session, in memory, persisted to session_chunks for resume
    def add(self, chunk: ContextChunk) -> None
    def recheck(self, principal: Principal) -> RecheckResult   # -> kept, revoked: list[chunk_id], reasons
    def render(self) -> list[dict]                              # messages with revoked chunks replaced
```

### 9.3 What "still allowed" means: the `is_allowed(chunk, principal)` predicate

A chunk stays only if **all** of these hold now:

1. `principal` still has `chat:use` in `chunk.tenant_id` (item 7).
2. The source connection still allows the tool that produced it. `connections.is_allowed(server, tool)` is checked for reads too: a server that was **removed or disabled** revokes its chunks.
3. `acl_epoch` is still current for that source. Sources that can be unshared (RAG docs, Obsidian notes, uploads) carry an `acl_epoch` in a `source_acl` table, and revoking access increments it.
4. If `policy_version` changed: re-run `classify` for the producing tool. A chunk is revoked only if the change **removed access**: the connection was disabled, or the tool became blocked for this principal. A tier change from READ to WRITE does not revoke data that was already read lawfully. It does stop future calls, and that is the gate's job.

Fast path: if `policy_version` and every `acl_epoch` are unchanged since the last check, `recheck` costs O(1). It compares one integer per source.

### 9.4 Where the recheck runs

- **Every turn**, before the LLM call, in `JarvisAgent.respond`, `_respond_as_subagent` and each orchestrator step, right after `BudgetGuard.check`.
- **Every gated tool call**: `gate_tool` calls `ledger.recheck` too, so an approval cannot be built on revoked evidence. If evidence was revoked, the pending request is auto-`REJECTED` with reason `evidence_revoked`, and that is logged.

### 9.5 What revocation does

- The content of a revoked chunk is replaced in the rendered prompt with `[content removed: access to {source_ref} was revoked at {ts}]`. The marker is kept so the LLM knows something is gone, and does not hallucinate around a silent gap.
- A websocket event `context_revoked {session_id, chunk_ids, reasons}` goes to the UI, which shows a banner in the chat.
- A `CONTEXT_REVOKED` decision-log row records `{session_id, chunk_ids, reasons}`, with no content.
- Derived content: assistant messages produced **after** a revoked chunk entered may quote it. v1 policy: those assistant messages are kept, but tagged `derived_from_revoked`, and the session is flagged. Removing them is optional, behind `HERMES_REVOKE_DERIVED=1`. This limitation is documented. The hard guarantee covers raw source content only.

### 9.6 Persistence

```sql
CREATE TABLE IF NOT EXISTS session_chunks (
    tenant_id TEXT NOT NULL, session_id TEXT NOT NULL, chunk_id TEXT NOT NULL,
    source_kind TEXT NOT NULL, source_ref TEXT NOT NULL, principal_subject TEXT NOT NULL,
    policy_version INTEGER NOT NULL, acl_epoch INTEGER NOT NULL, fetched_at TEXT NOT NULL,
    content_hash TEXT NOT NULL, revoked_at TEXT, revoke_reason TEXT,
    PRIMARY KEY (tenant_id, session_id, chunk_id)
);
CREATE TABLE IF NOT EXISTS source_acl (
    tenant_id TEXT NOT NULL, source_ref TEXT NOT NULL, epoch INTEGER NOT NULL,
    allowed_subjects TEXT,       -- JSON list or NULL = tenant-wide
    PRIMARY KEY (tenant_id, source_ref)
);
```

`messages` rows that carry tool output gain a `chunk_id` column, so history reloads can re-render with revocations applied.

### 9.7 Test plan (write first)

**`backend/tests/test_provenance_unit.py`**

```python
from backend.provenance import ContextChunk, ProvenanceLedger
from backend.identity import Principal

U = Principal(subject="u", roles=("owner",))

def chunk(ref, pv=1, epoch=1, kind="tool_result"):
    return ContextChunk(chunk_id=ref, tenant_id="default", source_kind=kind, source_ref=ref,
                        principal_subject="u", policy_version=pv, acl_epoch=epoch,
                        fetched_at="2026-10-21T00:00:00Z", content=f"secret from {ref}")

def test_unchanged_policy_keeps_all(fake_policy):
    L = ProvenanceLedger(); L.add(chunk("mcp:a/get")); assert L.recheck(U).revoked == []

def test_disabled_connection_revokes_its_chunks(fake_policy):
    L = ProvenanceLedger(); L.add(chunk("mcp:a/get")); L.add(chunk("mcp:b/get"))
    fake_policy.disable_server("a")
    r = L.recheck(U)
    assert r.revoked == ["mcp:a/get"]
    rendered = str(L.render())
    assert "secret from mcp:a/get" not in rendered and "access to mcp:a/get was revoked" in rendered
    assert "secret from mcp:b/get" in rendered

def test_acl_epoch_bump_revokes_doc(fake_policy):
    L = ProvenanceLedger(); L.add(chunk("rag:doc/1", kind="rag_doc"))
    fake_policy.bump_acl("rag:doc/1")
    assert L.recheck(U).revoked == ["rag:doc/1"]

def test_tier_raise_does_not_revoke_already_read(fake_policy):
    L = ProvenanceLedger(); L.add(chunk("mcp:a/get"))
    fake_policy.set_tier("get", "WRITE")
    assert L.recheck(U).revoked == []

def test_principal_losing_chat_perm_revokes_all(fake_policy):
    L = ProvenanceLedger(); L.add(chunk("mcp:a/get"))
    assert L.recheck(Principal(subject="u", roles=())).revoked == ["mcp:a/get"]

def test_fast_path_no_db_calls_when_versions_unchanged(fake_policy):
    L = ProvenanceLedger(); L.add(chunk("mcp:a/get")); L.recheck(U)
    fake_policy.calls.clear(); L.recheck(U)
    assert fake_policy.calls == ["policy_version", "acl_epochs"]
```

**`backend/tests/test_provenance_agent_wiring.py`**

- `test_tool_results_become_chunks_in_react_loop`
- `test_revocation_between_turns_removes_content_from_next_llm_payload`: capture the httpx POST body on turn 2, and assert the secret is absent and the marker is present.
- `test_pending_approval_auto_rejected_when_evidence_revoked` (decision log has `evidence_revoked`)
- `test_context_revoked_ws_event_emitted`
- `test_history_reload_applies_revocation`

**`backend/tests/test_provenance_cross.py`**

- `test_orchestrator_step2_does_not_see_revoked_step1_output`: disable the connection between steps 1 and 2.

### 9.8 Acceptance

- Revoke a connection while a session runs. On the **next** LLM call, no raw content from that source is in the request body, as verified by intercepting the outbound HTTP.

---

## Phase 3 exit criteria

- [ ] Every `/api/*` route has a permission, and the route-walk test enforces it.
- [ ] Two tenants on one Postgres install are isolated by RLS. The SQLite static scan is green.
- [ ] Mid-session revocation removes source content from the next prompt and is logged.
