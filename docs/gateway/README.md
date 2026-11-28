---
title: Gateway stdio proxy and PreToolUse hook
description: Wrap one MCP stdio server, and Claude Code / Cursor builtins, with Hermes Synapse approvals. Pending-retry by default.
---

# Wrap an MCP server and coding-agent builtins with Hermes approvals

Milestones A (stdio proxy) and B (localhost hook). HTTP MCP transport is out of scope. RBAC is unchanged.

```
MCP client  --stdio NDJSON-->  hermes stdio proxy  -->  upstream MCP server
                                      |
                                      v
Claude Code / Cursor hook --HTTP-->  POST /api/gateway/pre-tool  -->  decide()
                                      |                                  |
                                      |                                  v
                                      +------>  Approvals UI + decision_log
```

The hook process does **not** open the database. It posts the host event to a loopback backend endpoint authenticated by a dedicated `HERMES_GATEWAY_TOKEN`.

## Framing (verified)

MCP stdio is **newline-delimited JSON-RPC**. Not LSP `Content-Length`.

Checked on 2026-11-28:

| Source | What we saw |
|---|---|
| [MCP spec 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports) | "Messages are delimited by newlines, and MUST NOT contain embedded newlines." |
| Official Python SDK 2.3.0 `mcp.client.stdio` | Writes `json + "\n"`, reads by splitting on `\n` |
| `@modelcontextprotocol/server-everything` | First response line is `{...json...}`, no `Content-Length` |
| `@modelcontextprotocol/server-filesystem` | Same |
| Hermes `mcp_client.py` / `mcp_openapi_proxy.py` | Already NDJSON |

There is no second dialect to keep. The proxy speaks this format on both sides.

## Wrap in `mcp_config.json`

The dashboard MCP tab and `backend/mcp_client.py` read `mcp_config.json` (`backend/data/mcp_config.json`, else repo-root `mcp_config.json`).

Point the client's `command` at the proxy, and pass the real server after `--`:

```json
{
  "mcpServers": {
    "filesystem": {
      "command": "python",
      "args": [
        "-m",
        "backend.gateway.stdio_proxy",
        "--",
        "npx",
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/path/to/vault"
      ],
      "env": {
        "HERMES_GATEWAY_WAIT": "0",
        "HERMES_GATEWAY_SESSION_ID": "cursor-filesystem",
        "HERMES_GATEWAY_AGENT_NAME": "filesystem",
        "PYTHONPATH": "/path/to/hermes-synapse"
      }
    }
  }
}
```

From the repo root:

```bash
PYTHONPATH=. python -m backend.gateway.stdio_proxy -- \
  npx -y @modelcontextprotocol/server-filesystem /tmp/vault
```

The process needs the same database as the dashboard (`DATABASE_URL` for Postgres, or `HERMES_SQLITE_PATH` for a dedicated sqlite file). `init_db()` runs when the proxy starts.

## Defaults (stdio proxy)

| Env | Default | Meaning |
|---|---|---|
| `HERMES_GATEWAY_WAIT` | `0` | Pending-retry. Do not block the MCP request. |
| `HERMES_GATEWAY_WAIT_TIMEOUT_S` | `50` | Cap if wait is enabled (MCP clients time out at 60s). |
| `HERMES_GATEWAY_ON_TIMEOUT` | `fail_closed` | Only used when wait=1. `pending_retry` returns PENDING instead of deny. |
| `HERMES_GATEWAY_SESSION_ID` | `gateway` | Match key (session + action + payload). |
| `HERMES_GATEWAY_AGENT_NAME` | `gateway` | Display name on the approval. |
| `HERMES_SQLITE_PATH` | unset | Override sqlite file for a proxy subprocess. |

**Pending-retry (default):** first high-risk `tools/call` creates `PENDING`, appends `REQUESTED`, and returns an MCP **tool result** with `isError: true` and JSON `{status: PENDING_APPROVAL, request_id, error}`. It is not a JSON-RPC error. After Approve in the dashboard, the client retries the **identical** arguments. The gate consumes once (`CONSUMED`) and the proxy forwards upstream.

**Wait (optional, `HERMES_GATEWAY_WAIT=1`):** the proxy blocks until Approve/Reject, disconnect, or 50s. The proxy does **not** emit `notifications/progress`, so SDK `resetTimeoutOnProgress` will not extend the wait. Prefer pending-retry for MCP. A client disconnect sets cancel and logs `TIMEOUT` with reason `client_disconnect`; the row stays `PENDING` and is not consumed.

## What is gated (MCP)

- Names in `HIGH_RISK_TOOLS` (and plugin extras)
- Every MCP tool from `tools/list` unless `readOnlyHint: true` or `destructiveHint: false`

Built-in Claude Code / Cursor tools (`Bash`, `Edit`, `Write`, Cursor `Shell` / `Delete`) never appear on this socket. Gate those with the PreToolUse hook below.

## Claude Code / Cursor hook (milestone B)

`scripts/gateway/claude_pre_tool_use.py` is stdlib-only. It reads the host event on stdin and `POST`s it to loopback:

`http://127.0.0.1:8000/api/gateway/pre-tool`

The backend binds that route to **loopback peers** (`HERMES_GATEWAY_BIND=127.0.0.1` by default; `::1` / `localhost` aliases included). Forwarded headers (`X-Forwarded-For`, `X-Real-IP`) are rejected unless `HERMES_GATEWAY_TRUST_PROXY=1`. Do not put this route behind a reverse proxy if you want the bind check to mean anything.

Auth is a dedicated token, not a session and not JWT:

```bash
openssl rand -hex 32   # at least 32 characters
export HERMES_GATEWAY_TOKEN=...
```

Compare is SHA-256 then `hmac.compare_digest`. A session OTP/JWT cannot call this route; this token cannot call the rest of `/api`. RBAC is not involved. The raw token is never written to logs or `decision_log` (reasons are scrubbed; uvicorn access logs stay off).

The hook process must inherit `HERMES_GATEWAY_TOKEN`. Do not put it in `settings.json`.

| Env | Default | Meaning |
|---|---|---|
| `HERMES_GATEWAY_TOKEN` | unset | Required, ≥32 chars. Missing/short → hook deny (fail-closed); endpoint 503. |
| `HERMES_GATEWAY_URL` | `http://127.0.0.1:8000/api/gateway/pre-tool` | Must be loopback or the script denies. |
| `HERMES_GATEWAY_BIND` | `127.0.0.1` | TCP peers allowed to hit the endpoint. |
| `HERMES_GATEWAY_WAIT` | `0` | Same pending-retry default as the proxy. |
| `HERMES_HOOK_HOST_TIMEOUT_S` | `50` | Host hook timeout from the example settings. Wait is capped 5s below this. |
| `HERMES_HOOK_HTTP_TIMEOUT_S` | `45` | urllib timeout in the script (capped at 45s). |
| `HERMES_HOOK_FORMAT` | `claude` | `cursor` for Cursor permission JSON. |

**Pending-retry:** a high-risk builtin (`Bash`, `Edit`, `Write`, `NotebookEdit`, `MultiEdit`, Cursor `Shell`/`Write`/`Delete`) creates `PENDING`, logs `REQUESTED` + `HOOK`, and the hook returns **deny** with `Pending approval for {action} (request_id=…). Retry this tool with identical arguments after a human approves it in Hermes.` Approve in the dashboard, then the host retries identical arguments; the gate consumes once.

**Optional wait:** `HERMES_GATEWAY_WAIT=1` blocks inside the endpoint up to the hook wait cap (default 45s, always below the host hook timeout). On that wait timeout the hook **denies with the same pending-retry reason** (row stays `PENDING`). Set `HERMES_GATEWAY_ON_TIMEOUT=fail_closed` to deny without inviting a retry.

**Fail-closed** (deny JSON, exit 0): invalid stdin JSON, missing/short token, non-loopback URL, HTTP timeout, unreachable backend, HTTP 4xx/5xx, or a non-JSON response. Pair with the host flags below or a killed script fails **open**.

`session_id` comes from the host event (`session_id` or `conversation_id`), not a single global string.

### Example `.claude/settings.json`

Copy `scripts/gateway/example.claude.settings.json`. Keys were checked against **Claude Code CLI 2.1.332** (Zod `BashCommandHookSchema` in the installed binary):

| Key | Required value | CLI meaning (2.1.332) |
|---|---|---|
| `type` | `command` | Shell command hook |
| `command` | path to the script | Spawned via shell unless `args` is set |
| `timeout` | `50` (seconds) | Per-command timeout. Default host timeout is 600s if omitted. |
| `onFailure` | `block` | Default is `continue` (fail-open). `block` treats spawn/timeout/non-0-or-2/invalid JSON as exit 2 and **blocks the tool**. |
| `statusMessage` | optional | Spinner text while the hook runs |
| `matcher` | `Bash\|Edit\|Write\|NotebookEdit\|MultiEdit` | Tool-name pattern |

`onFailure` lives on the **command hook object**, not the matcher. Values are `continue` \| `block`.

### Example Cursor `hooks.json` (unverified-live)

Copy `scripts/gateway/example.cursor.hooks.json`. It sets `failClosed: true` on `preToolUse` and `beforeShellExecution`. **Not executed against a live Cursor agent in this environment.** Remove the `_unverified_live` field if the host rejects unknown keys.

### Production compose note

Pilot compose publishes the dashboard on `127.0.0.1:9119` and does **not** publish backend `:8000`. The bind check uses the TCP peer the backend sees. Point `HERMES_GATEWAY_URL` at a loopback-published backend (`127.0.0.1:8000`), or run the hook in a place that can reach that peer as `127.0.0.1`. Do not send the gateway token through an untrusted proxy.

## Decision log

`REQUESTED` / `APPROVED` / `REJECTED` / `CONSUMED` / `TIMEOUT` / `HOOK` all go on the existing chain. Every hook decision that reaches the backend appends `HOOK`. Fail-closed in the hook **process** (bad JSON, missing token, unreachable backend) never reaches the chain — there is no backend to write to.

Export and check:

```bash
curl -f -H "Authorization: Bearer <SESSION>" \
  http://127.0.0.1:9119/api/governance/decisions/export.zip -o decisions.zip
python3 scripts/verify_decision_log.py decisions.zip --pin <head_hash>
```

Use a dashboard session token for export, not `HERMES_GATEWAY_TOKEN`.
