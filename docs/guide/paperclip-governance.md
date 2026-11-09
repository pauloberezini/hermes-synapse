---
title: Budgeting and governance
description: Paperclip-inspired BudgetGuard spend caps, human approval queues, and OSS team presets in Hermes Synapse.
---

# Budgeting and governance

Hermes Synapse ships Paperclip-inspired controls so autonomous agents cannot spend or act without a ceiling.

For the approval gate, evidence hash, and decision log, read [Security](./security.md) and [Approvals](./approvals.md). This page is the rest of the control plane.

## Token and dollar caps (`BudgetGuard`)

`BudgetGuard` (`backend/governance.py`) reads spend from the database and raises `BudgetExceededError` before the next LLM call if the cap is hit.

Caps live in `app_settings`:

- `budget_global_daily_usd`
- `budget_global_monthly_usd`

Per-session caps live on `session_metadata` (`daily_budget_usd`, `monthly_budget_usd`; `NULL` means unlimited).

```http
GET /api/governance/budget/{session_id}
```

```json
{
  "session_spend_usd": 0.125,
  "session_budget_usd": 5.0,
  "global_daily_spend_usd": 1.42,
  "global_daily_budget_usd": 50.0
}
```

## Human approval queue

High-risk built-ins and write-shaped MCP tools stop at `PENDING` until an operator approves **that exact payload**. Approve does not execute. The next identical call is `CONSUMED` and runs once. See [Approvals](./approvals.md).

The dashboard badge and modal (`ApprovalsBadge.tsx`, `ApprovalsModal.tsx`) are driven by WebSocket `approval_update` events, with a 10 second poll fallback.

## Team presets

One-click OSS presets (`backend/presets.py`):

- **Engineering Shop** - Tech Lead, Backend Python Developer, Security Auditor
- **OSINT Bureau** - Intelligence Director, Web OSINT Scout, Obsidian Vault Archivist

Plugins may add more presets through the plugin hook. They are not listed here unless they live in the OSS tree.

## Video

<YouTube id="3GFh-1Gglno" title="Paperclip governance tutorial" />
