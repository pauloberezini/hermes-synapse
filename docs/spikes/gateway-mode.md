---
title: Gateway mode spike
description: Time-boxed prototype of Hermes Synapse as an approval gateway in front of MCP clients and coding-agent builtins.
---

# Gateway mode spike

**Branch:** `cursor/gateway-spike-2164`  
**Date:** 2026-11-28  
**Scope:** prove or disprove that an external AI coding agent's risky actions can go through the existing Hermes `ApprovalQueue` + hash-chained `decision_log`. RBAC untouched. Not merged to `main`.

This is **not** Phase 4 item 10 (multiplexed HTTP gateway, inventory, call log, client tokens). It is the smallest path that sits in front of one stdio MCP server and in front of Claude Code built-in tools.

```
MCP client  --stdio NDJSON-->  hermes stdio proxy  -->  upstream MCP server
                                      |
                                      v
Claude Code PreToolUse hook ---->  decide() -> gate_tool -> ApprovalQueue
                                      |
                                      v
                         existing Approvals UI + decision_log
```

---

## Verdict

**The shape works.** High-risk MCP `tools/call` and Claude Code builtins (`Bash`, `Edit`, `Write`, …) can create `PENDING` rows in the existing queue, show up for a human, and land `REQUESTED` / `APPROVED` / `REJECTED` / `CONSUMED` on the existing hash chain.

**Blocking-wait is the wrong default on MCP.** A waiting proxy occupies the client's JSON-RPC request. Hermes' own stdio client times out at **60s**; the official MCP TypeScript SDK default is **60s**; Hermes HTTP MCP is **30s**. A human in the Approvals UI is slower than that. Returning `PENDING_APPROVAL` as an MCP **tool result** with `isError: true` (retry the identical call) is the mode that survives timeouts. That is already how in-process `gate_tool` talks to Hermes agents, and it is what Phase 4 specified.

**Wait-then-forward is the right default for a host hook** if the host actually fail-closes on hook timeout. Claude Code's PreToolUse command-hook default timeout is **600s**, which is long enough to click Approve — but a timed-out hook **does not block** unless `onFailure: "block"` is set. Cursor permission hooks **fail open** on crash/timeout unless `failClosed: true`. The example configs set those flags. Without them, gateway mode is theatre.

**Built-in tools bypass the MCP proxy.** Expected, and confirmed by construction plus tests: Claude `Bash`/`Edit`/`Write` never appear as `tools/call` on the MCP socket. The PreToolUse hook is the only gate on that path. The proxy alone is not a coding-agent gateway.

---

## What works (exercised in this VM)

| Piece | Where | Evidence |
|---|---|---|
| Classification reuses `HIGH_RISK_TOOLS` + plugin extras + MCP annotation defaults | `backend/gateway/classify.py` | `test_gateway_classify.py` |
| Claude builtins gated even though they are not in `HIGH_RISK_TOOLS` | `CLAUDE_HIGH_RISK_TOOLS` | `test_claude_builtins_are_gated_even_when_not_mcp` |
| Read-only MCP tools (`readOnlyHint: true` or `destructiveHint: false`) skip the queue and hit upstream | proxy `tools/list` cache | `test_readonly_mcp_tool_forwards_to_upstream` |
| Unannotated MCP tools wait (MCP defaults) | `drop_table` in the fake server | `test_mcp_unannotated_write_is_gated` |
| `decide()` calls existing `gate_tool` / `ApprovalQueue` | `backend/gateway/decide.py` | pending / approve / reject tests |
| Wait + Approve consumes once and **then** forwards | proxy `handle_rpc` | `test_wait_approve_then_forwards`; log `REQUESTED, APPROVED, CONSUMED` |
| Reject never reaches upstream | proxy | `test_reject_never_calls_upstream` |
| Pending is an MCP tool error, not a JSON-RPC error | `tool_result(..., is_error=True)` | `test_tool_result_pending_is_mcp_tool_error_not_jsonrpc_error` |
| Hook maps Bash/Edit/Write, fail-closes on bad JSON, missing backend, decide() exceptions | `backend/gateway/hook.py`, `scripts/gateway/claude_pre_tool_use.py` | `test_gateway_hook.py` |
| Hook wait+approve returns Claude `permissionDecision: allow` so **this** call runs (no operator re-send) | hook | `test_wait_then_approve_allows` |
| `ApprovalQueue.wait_for_decision` (docstring already promised it) | `backend/governance.py` | `test_wait_for_decision_returns_pending_on_timeout` |
| Existing suite still green | `uv run pytest` in `backend/` | **468 passed, 3 skipped** (33 of those are new gateway tests) |

How to wrap a stdio server:

```bash
python -m backend.gateway.stdio_proxy -- <upstream command> [args...]
```

Env: `HERMES_GATEWAY_WAIT` (default `1`), `HERMES_GATEWAY_WAIT_TIMEOUT_S` (default `50`), `HERMES_GATEWAY_ON_TIMEOUT` (`fail_closed` \| `pending_retry`), `HERMES_GATEWAY_SESSION_ID`, `HERMES_GATEWAY_AGENT_NAME`.

Hook: copy `scripts/gateway/example.claude.settings.json` to `.claude/settings.json`. Pair with `onFailure: "block"`.

---

## What does not work / was not proven

| Gap | Why it matters |
|---|---|
| **Official MCP stdio framing is Content-Length (LSP-style).** This proxy, like `mcp_client.py` and `mcp_openapi_proxy.py`, speaks **newline-delimited JSON**. Claude Desktop / the TypeScript SDK will not talk to this prototype without a framing adapter. | Blocks real desktop clients. |
| **Claude Code and Cursor were not installed in this VM.** Hook JSON I/O is unit-tested. Host timeout, matcher, and `onFailure`/`failClosed` behaviour is from current public docs, not a live run. | Marked unverified below. |
| **HTTP / Streamable MCP transport** is not in this spike. | Phase 4 item 10. |
| **One upstream only.** No namespacing, no inventory, no multiplex. | Fine for a proof; not a product gateway. |
| **Hook imports the backend and uses the same SQLite/Postgres as the dashboard.** No new HTTP endpoint (would have touched auth). If Hermes runs in Docker and Claude Code on the host, the hook cannot see the queue unless `DATABASE_URL` (or a bind-mounted sqlite) is shared. | Operational gap for MVP. |
| **Gateway-local timeout is not a `decision_log` event.** Timeout fail-closed leaves the row `PENDING` (so a retry can still consume a later Approve). Only `REQUESTED` is chained until a human resolves. | Audit hole for "who/what denied on timeout". |
| **Wait mode after client timeout can still consume.** If the client has gone and the proxy keeps waiting, a late Approve consumes and may call upstream with nobody listening. | See risks. |
| **Not a security boundary if the agent can edit hook settings.** | Same class as any host hook. |

---

## Measured timeouts (this VM, 2026-11-28)

Source constants (grep of this tree, plus published SDKs):

| Client | Timeout | Source |
|---|---|---|
| Hermes stdio MCP client | **60.0s** | `MCPServerClient.send_request` → `asyncio.wait_for(..., timeout=60.0)` |
| Hermes HTTP MCP client | **30.0s** | `httpx.AsyncClient(timeout=30.0)` in `send_request_http` |
| MCP TypeScript SDK default | **60s** (`DEFAULT_REQUEST_TIMEOUT_MSEC = 60000`) | [protocol.ts v1.29.0](https://github.com/modelcontextprotocol/typescript-sdk/blob/v1.29.0/src/shared/protocol.ts). Per-call override exists. `resetTimeoutOnProgress` can extend a wait if the server emits progress. **Not sent by this prototype.** |
| Claude Code PreToolUse `command` hook | default **600s**; `UserPromptSubmit` family **30s** | [Hooks reference](https://code.claude.com/docs/en/hooks) |
| Claude Code timed-out PreToolUse | **does not block** unless `onFailure: "block"` (v2.1.295+) | same |
| Cursor hook `timeout` | seconds, "platform default" if omitted | [cursor.com/docs/hooks](https://cursor.com/docs/hooks) |
| Cursor crash/timeout/non-2 exit | **fail-open** unless `failClosed: true`. Invalid JSON on permission hooks **blocks**. | same |

Measured in this VM (`scripts/gateway/measure_timeouts.py` plus `pytest --durations`):

| Scenario | Config | Elapsed | Outcome |
|---|---|---|---|
| Enqueue only (`wait=False`), warm process | `decide(..., wait=False)` | **0.004s** | `PENDING_APPROVAL`; `REQUESTED` logged |
| Same, first call in a pytest process | `test_high_risk_pending_retry_*` | **0.22s** | includes first `agent`/`evidence` import |
| Wait, nobody approves, fail-closed | `timeout_s=0.3` | **0.545s** | `effect=deny`, `status=TIMEOUT`; row stays `PENDING` |
| Wait then `pending_retry` | `timeout_s=0.2` | **0.21s** | `effect=pending`; same `request_id` reused on retry |
| Wait + Approve from another thread | `timeout_s=2` | **0.11s** | `allow` + `CONSUMED`; upstream would run |
| NDJSON client 0.4s deadline vs proxy wait 5s | live subprocess proxy | **0.448s**, `outcome=client_timeout` | client hung up; proxy still waiting |
| Simulated in-process client 0.3s vs wait 2s | thread `join(0.3)` | client gives up at **~0.3s**; proxy thread lives until **2.03s** | upstream **not** called; row stays `PENDING` |

**Can we return "pending, retry" instead of hanging?** Yes. Two knobs:

1. `HERMES_GATEWAY_WAIT=0` — return `PENDING_APPROVAL` immediately (~0.2s). Recommended for MCP clients with a 60s cap.
2. `HERMES_GATEWAY_WAIT=1` and `HERMES_GATEWAY_ON_TIMEOUT=pending_retry` — wait up to `WAIT_TIMEOUT_S` for a fast human, then return pending rather than deny. Still occupies the MCP request for that window, so keep it **under 50s** (default).

A `tools/call` result with `isError: true` and JSON `{status: PENDING_APPROVAL, request_id}` is the retry signal. Do **not** use a JSON-RPC error: the model never sees a structured retry hint.

For the hook, "pending, retry" is a **deny** with reason `PENDING_APPROVAL request_id=N. Approve in Hermes, then retry with identical arguments.` Claude Code has no PENDING tool-result on builtins. After Approve, the next identical PreToolUse hits `gate_tool`, consumes, returns `allow`.

---

## Bypass findings

### MCP proxy vs host builtins (tested)

Built-in coding-agent tools **do not** travel on the MCP socket. The proxy only intercepts JSON-RPC `tools/call`. A Claude Code `Bash` is a host tool; `needs_approval("Bash")` is true in the hook classifier, and `needs_approval("Read")` is false. There is no `tools/call` frame for the proxy to see.

Confirmed:

- Proxy + fake upstream: `ping` (read-only) forwarded; `execute_command` / `drop_table` blocked until Approve.
- Hook: `Read` never opens a queue row; `Bash` / `Edit` / `Write` do.
- Therefore: **MCP gateway without the hook does not govern Claude Code or Cursor file/shell tools.** Expected.

An MCP server that itself exposes a tool named `Bash` *would* be gated by the proxy (`known_mcp=True` fail-closes on missing annotations). That is a different path from the host builtin.

### Other bypasses (not fully tested; treat as real)

- User or agent disables/edits `.claude/settings.json` or `hooks.json`.
- Claude Code: hook timeout or missing script **fail-open** unless `onFailure: "block"`.
- Cursor: hook crash/timeout **fail-open** unless `failClosed: true`. Other non-zero exit codes (not 2) fail open by default.
- Cursor cloud agents: HTTP MCP servers run on Cursor's backend; `preToolUse` can deny, `updated_input` is ignored; `beforeMCPExecution` is **deferred** on cloud (docs). Unverified here.
- Tools the hook matcher does not list (`ComputerUse`, browser, Task/subagent internals, `EndConversation` skipping PreToolUse on Claude Code).
- Direct `execute_tool` inside Hermes is already gated; this spike does not change that.

The hook **does** close the builtin gap **if** it is installed, fail-closed, and the process can reach the same ApprovalQueue.

---

## Cursor equivalents (docs only — unverified in this VM)

Cursor has first-class hooks. They are the counterpart, not a missing feature.

| Job | Claude Code | Cursor |
|---|---|---|
| Before any tool | `PreToolUse` | `preToolUse` (matcher `Shell`, `Write`, `Delete`, `MCP:<name>`, …) |
| Before shell | `PreToolUse` matcher `Bash` | `beforeShellExecution` |
| Before MCP | (MCP tools still hit PreToolUse) | `beforeMCPExecution` / `afterMCPExecution` |
| Config | `.claude/settings.json` `hooks` | `.cursor/hooks.json` or `~/.cursor/hooks.json` |
| Allow/deny JSON | `hookSpecificOutput.permissionDecision` | `{ "permission": "allow" \| "deny" }` |
| Block on exit | exit `2` | exit `2` (deny). Other exits fail-open |
| Fail-closed flag | `onFailure: "block"` | `failClosed: true` |
| Third-party | — | Cursor maps Claude hook names (`PreToolUse` → `preToolUse`) |

Example (unverified): `scripts/gateway/example.cursor.hooks.json`. Same Python entrypoint with `HERMES_HOOK_FORMAT=cursor`. `beforeShellExecution` input is `{command, cwd}`; the hook maps that to `Shell`/`Bash`.

Cloud-agent caveat from Cursor docs: HTTP MCP is not on the VM; `beforeMCPExecution` may not fire. A Hermes stdio proxy on the worker would still see stdio MCP. Unverified.

---

## Risks

1. **Fail-open host defaults.** Shipping example configs without `onFailure: "block"` / `failClosed: true` makes the control look present and do nothing on timeout. MVP must treat those flags as mandatory.
2. **60s MCP wait vs human latency.** Blocking wait will false-deny or drop the client. Default MCP to `wait=0` (pending retry). Use wait on hooks, or wait ≤50s with `pending_retry`.
3. **Late consume after client timeout.** Wait mode should abort the wait when the client disconnects (not done). Until then, prefer pending-retry on MCP.
4. **Sticky REJECTED** (existing R2-2). A coding agent that changes args gets a new row; the same args stay blocked in that `session_id`. Set `HERMES_GATEWAY_SESSION_ID` per chat, not globally.
5. **Hook shares the DB.** Docker-compose Hermes + host Claude Code needs a reachable `DATABASE_URL` or a tiny localhost approve API (no RBAC change required: a dedicated gateway token). Without that, the hook fail-closes and the agent cannot work — which is correct, but surprising.
6. **`note_mcp_tool("gateway", …)` pollutes the process-global MCP registry** so `gate_tool` treats `Bash`/`Edit` as MCP-gated. Fine in the hook subprocess; do not import the hook module inside the Hermes API process.
7. **NDJSON vs Content-Length** — a "working" proxy that only speaks Hermes' dialect will silently fail in front of Claude Desktop.
8. **Not a sandbox.** Approving `Bash` still runs in the agent's environment. Hermes is an approval layer, not isolation.
9. **Agents can rewrite hooks.** Governance of the host config is out of band (managed settings / MDM on Claude Code; Cursor enterprise hooks). Out of spike scope.
10. **Timeout denials are invisible in `/decisions/verify`.** Operators will see a pending badge with no REJECTED line.

---

## Estimate to MVP (hours, not calendar)

Spike already has the state machine. Numbers below are remaining work to something an operator could run against a real Claude Code + one stdio MCP server, then HTTP.

### Milestone A — stdio proxy you can put in `mcp_config.json` (~14 hours)

**DoD**

- Dual framing: NDJSON **and** `Content-Length` (detect on first byte/line).
- `python -m backend.gateway.stdio_proxy -- cmd…` documented as the wrapper for one upstream.
- Default `HERMES_GATEWAY_WAIT=0` (pending retry). Optional wait capped at 50s with `pending_retry` fallback.
- Progress notifications on a waiting call (so SDK `resetTimeoutOnProgress` can keep a rare wait-mode client alive) — or an explicit "wait mode unsupported on MCP" note if skipped.
- Client disconnect cancels wait; does not consume.
- `tools/list` annotations drive the gate; `HIGH_RISK_TOOLS` names still gated.
- Pending = MCP tool result `isError: true`, never JSON-RPC error.
- Reject / timeout fail-closed never calls upstream.
- Approve + retry (or wait+approve) calls upstream **once**; `CONSUMED` in the log.
- Tests: fake upstream NDJSON + Content-Length; timeout; disconnect; annotation opt-out.
- Existing `pytest` green. No RBAC changes.

### Milestone B — Claude Code / Cursor hook that shares the live queue (~12 hours)

**DoD**

- Example `.claude/settings.json` and `.cursor/hooks.json` with **fail-closed flags required**.
- Hook reaches Hermes without importing the whole API process: either shared `DATABASE_URL` **or** a localhost `POST /api/gateway/pre-tool` authenticated by `HERMES_GATEWAY_TOKEN` (not a new role matrix; do not touch RBAC).
- Fail-closed on: timeout, invalid JSON, backend unreachable, missing token, non-zero except the documented allow path.
- Live check on a machine with Claude Code: Bash is PENDING in the Approvals UI; Approve then retry (or wait) runs once; decision_log verifies.
- Cursor: same for `beforeShellExecution` **or** documented "unverified on cloud agents".
- Matcher covers Bash/Edit/Write/NotebookEdit/MultiEdit and Cursor Shell/Write/Delete.
- `session_id` from the host event, not a single global string.
- Tests keep the fail-closed import/JSON/timeout cases.

### Milestone C — HTTP transport (Phase 4 slice, ~24 hours)

**DoD**

- Streamable HTTP `POST /mcp` (JSON-RPC, optional SSE) as specified in `docs/specs/roadmap/phase-4-ecosystem.md` §10.3, **without** building inventory UI or partner plugins.
- Same `decide()` path as stdio. Pending retry is the default.
- Gateway client token (hashed at rest, tool allowlist). Reuse Bearer middleware; no new RBAC roles.
- `initialize`, `tools/list`, `tools/call`, `ping`. Namespacing `{server}__{tool}` for two upstreams **or** an explicit single-upstream limitation in the release note.
- Protocol tests with `TestClient` raw JSON-RPC (the cases already listed in the Phase 4 spec).
- Docs: one page in `docs/guide/` (not only this spike file).
- `pytest` + docs build green.

**Total to a usable stdio+hook MVP: ~26 hours (A+B). HTTP on top: ~24 hours (C).** Full Phase 4 (call log UI, reach-vs-touched matrix, inspectors) is extra and should not be folded into this MVP.

---

## Files in this spike

| Path | Role |
|---|---|
| `backend/gateway/classify.py` | High-risk classification |
| `backend/gateway/decide.py` | Wait / pending-retry around `gate_tool` |
| `backend/gateway/stdio_proxy.py` | NDJSON MCP proxy |
| `backend/gateway/hook.py` | PreToolUse decision + Claude/Cursor JSON |
| `backend/governance.py` | `ApprovalQueue.wait_for_decision` only |
| `scripts/gateway/claude_pre_tool_use.py` | Hook entrypoint (fail-closed import) |
| `scripts/gateway/example.claude.settings.json` | `onFailure: "block"`, timeout 50s |
| `scripts/gateway/example.cursor.hooks.json` | `failClosed: true` (unverified host) |
| `backend/tests/test_gateway_*.py` | Proxy, hook, classify, decide |
| `backend/tests/gateway_fake_mcp.py` | NDJSON upstream for local experiments |

`docs/.vitepress/config.mts` excludes `docs/spikes/**` from the published site, same as `docs/specs/**`.
