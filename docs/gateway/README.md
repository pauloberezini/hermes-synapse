---
title: Gateway stdio proxy
description: Wrap one MCP stdio server with Hermes Synapse approvals. Pending-retry by default.
---

# Wrap an MCP server with Hermes approvals

Milestone A of gateway mode. HTTP transport is out of scope. The proxy sits **between** an MCP client and **one** upstream stdio server. Risky `tools/call`s go through the existing ApprovalQueue and hash-chained decision log.

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

## Defaults

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

## What is gated

- Names in `HIGH_RISK_TOOLS` (and plugin extras)
- Every MCP tool from `tools/list` unless `readOnlyHint: true` or `destructiveHint: false`

Built-in Claude Code / Cursor tools (`Bash`, `Edit`, `Write`) never appear on this socket. That is milestone B (the PreToolUse hook).

## Decision log

`REQUESTED` / `APPROVED` / `REJECTED` / `CONSUMED` / `TIMEOUT` all go on the existing chain. Export and check:

```bash
curl -f -H "Authorization: Bearer <TOKEN>" \
  http://127.0.0.1:9119/api/governance/decisions/export.zip -o decisions.zip
python3 scripts/verify_decision_log.py decisions.zip --pin <head_hash>
```
