---
layout: home
title: Runtime governance and human approvals for AI agents
titleTemplate: :title | Hermes Synapse
description: Hermes Synapse holds risky AI agent tool calls until a person approves that exact call, and writes every step to a hash-chained log you can verify offline. Self-hosted, MIT.
head:
  - - meta
    - name: keywords
      content: Hermes Synapse, AI agent governance, human-in-the-loop, approval gate, runtime governance, MCP, decision log, audit log, SecOps, SRE, AI platform
hero:
  name: HERMES SYNAPSE
  text: Runtime governance and human approvals for AI agents.
  tagline: Your agent works in the demo. Security will not sign off on production, because nobody can show who approved what it did. Hermes holds risky tool calls until a person approves that exact call, and logs every step in a chain you can check offline.
  image:
    src: /og-image.png
    alt: Hermes Synapse Communication Link showing a Sys Ops command waiting for human approval
  actions:
    - theme: brand
      text: Run the approvals demo
      link: /guide/approvals
    - theme: alt
      text: Talk about a pilot
      link: https://www.linkedin.com/in/pauloberezini/

features:
  - title: An approval covers one call.
    details: Approving only records your decision. The agent then sends the same call again and it runs once. Change an argument and you get a new request.
  - title: Security can check the log without us.
    details: Requests, approvals, rejections and uses are chained with SHA-256. Export the log and run one Python script from the standard library. It needs no Hermes install and no network.
  - title: Agents only get narrower.
    details: A child agent gets the tools in both its own list and its parent's. BudgetGuard stops LLM calls when a session or global spend cap is reached.
---

## Who it is for

SecOps, SRE and AI platform teams at companies of roughly 50 to 500 people. You have an agent that is almost useful. Security or compliance wants to know who can make it act, who approved what, and whether the record can be trusted. Hermes is the layer that answers those three questions.

## What is in the box

- A visual DAG of orchestrators and specialists. No cycles. Children inherit only the intersection of their skills and the parent's.
- Dynamic LLM planning instead of a hardcoded pipeline.
- A gate on risky tools. The operator reads the claim and the source, approves a payload hash, and then the agent has to send the same call again before anything runs. A replay is a new `PENDING` request.
- An append-only, hash-chained decision log you can export and check with `scripts/verify_decision_log.py`. No Hermes install. No network.

Self-hosted. MIT. Docker Compose. Built by [Pavel Bereznichenko](https://github.com/pauloberezini) at [SupplyAlpha.ai](https://supplyalpha.ai).

Where it fits next to Microsoft Agent Governance Toolkit, LangGraph human-in-the-loop and a Slack button: [comparison](/guide/comparison). Under financial regulation, such as the Israel Securities Authority draft directive on AI: [regulated fintech](/use-cases/regulated-fintech).

<div class="cta-row">
  <a class="primary" href="https://github.com/pauloberezini/hermes-synapse">Get the code on GitHub</a>
  <a class="ghost" href="./guide/getting-started.html">Install with Docker Compose</a>
  <a class="ghost" href="./guide/approvals.html">Run the approvals demo</a>
</div>

## See it run

Rehearsal shots from 29 Oct 2026 on `main` (`f4f92d5`). The command is `df -h /`. No real secrets in these frames.

### A Sys Ops shell call stops at PENDING

<figure class="shot">

![Communication Link chat: Sys Ops execute_command waiting for approval, live Approvals badge showing one pending request](./assets/screenshots/chat-sysops-pending-live-badge.png)

<figcaption>The Approvals badge counts up as soon as the gate writes PENDING. The model is told to wait.</figcaption>
</figure>

### The pending queue

<figure class="shot">

![Governance Approvals pending queue listing a Sys Ops execute_command request](./assets/screenshots/approvals-pending-queue.png)

<figcaption>One card per request. Open evidence, then approve or reject.</figcaption>
</figure>

### Claim, source, args, and hash

<figure class="shot">

![Governance Approvals modal with CLAIM, SOURCE, pretty-printed args, and truncated bundle hash](./assets/screenshots/approvals-claim-source-hash.png)

<figcaption>CLAIM is the tool, agent name, session, args, and bundle_hash. SOURCE is the planner step (or the user instruction on a direct chat).</figcaption>
</figure>

### Approve with a note. Nothing executes yet.

<figure class="shot">

![Approval card with resolver note Read-only disk check, OK once and Approve / Reject buttons](./assets/screenshots/approvals-approve-with-note.png)

<figcaption>Approve writes APPROVED and records the operator Principal. The original tool call already returned PENDING_APPROVAL.</figcaption>
</figure>

### Re-send. The approved command runs once.

<figure class="shot">

![Chat after resend: Sys Ops ran the approved command once, tool returned exit_code 0](./assets/screenshots/chat-resend-runs-once.png)

<figcaption>The gate consumes the APPROVED row, the tool body runs, and the log records CONSUMED.</figcaption>
</figure>

### The same prompt again is a new PENDING item

<figure class="shot">

![Chat replay of the same df -h / request creating a new PENDING_APPROVAL instead of auto-running](./assets/screenshots/chat-replay-new-pending.png)

<figcaption>Consumed approvals are not reused. A replay is a new request with a new id.</figcaption>
</figure>

### Different args, different hash

<figure class="shot">

![Pending queue with two execute_command requests, one for df -h /tmp and one for df -h /](./assets/screenshots/approvals-two-pending-different-args.png)

<figcaption>df -h / and df -h /tmp are different payload keys. They never share an approval.</figcaption>
</figure>

### All tab: APPROVED, PENDING, CONSUMED

<figure class="shot">

![Approvals All tab showing APPROVED, PENDING, and CONSUMED statuses on the same request history](./assets/screenshots/approvals-all-tab-statuses.png)

<figcaption>The queue is an audit timeline, not a toaster that disappears after Approve.</figcaption>
</figure>

### Export, pin the head, watch tampering fail

<figure class="shot">

![Terminal: decisions verify ok, offline verify_decision_log.py --pin succeeds, then three tamper cases fail](./assets/screenshots/export-offline-verify-ok-tamper-fail.png)

<figcaption>Change inputs in evidence, edit a resolver note, or drop the last entry. The stdlib verifier exits 1.</figcaption>
</figure>

## How it works

```
Operator / Telegram / API
        │
        ▼
 Web dashboard (React)
        │
        ▼
 Root orchestrator (jarvis)  ── DAG planner
        │
        ▼
 Specialist (Sys Ops, Search, …)
        │
        ▼
 execute_tool ──► gate_tool
                    │
        ┌───────────┼────────────┐
        │ high-risk / MCP write  │ safe
        ▼                        ▼
   PENDING + evidence          run
        │
        ▼
 Governance Approvals
   Approve  →  APPROVED  →  re-send identical args  →  CONSUMED (runs once)
   Reject   →  REJECTED (sticky in this session)
        │
        ▼
 approval_decisions hash chain
        │
        ▼
 /decisions/verify  ·  export.zip  ·  verify_decision_log.py --pin
```

Planning is a DAG. Nested orchestrators re-plan among their own children. Cycle detection keeps the graph acyclic. A child's effective tools are `child.skills ∩ parent.skills`. Auto-hired specialists are capped the same way.

Read the [approvals walkthrough](/guide/approvals) and the [security model](/guide/security) for the exact hash coverage, API, and known limitations.

## Integrations at a glance

Documented in full on [Integrations](/guide/integrations). What the tree actually supports:

| Kind | Connectors |
|---|---|
| LLMs | Any OpenAI-compatible API: OpenRouter (default), Ollama, vLLM, LM Studio, LocalAI |
| Protocols | MCP client (tools registered at connect time; write-shaped tools wait for approval) |
| Extension | `hermes_sdk` skills, `backend/<name>/plugin.py` hooks, skills marketplace (no-op billing by default) |
| Chat / voice | Telegram bot, browser Speech Recognition + speechSynthesis |
| Search / knowledge | SearXNG, Obsidian Local REST API, Qdrant RAG, GraphRAG, RSS |
| Productivity | Google Calendar, Todoist, OpenWeatherMap, timers |
| Markets | CoinGecko + Yahoo Finance HTTP provider (plugins can replace it) |
| Data plane | PostgreSQL 16, Qdrant |
| Deploy | Docker Compose, Swarm, Kubernetes |

## Security, in one page

Approvals are bound to **session + action + payload**. `bundle_hash` is SHA-256 over a canonical view of the redacted evidence (args, plan, upstream hashes, flags). `description` and `links` are not in that hash. Approve does not execute. Consume is one-shot. The decision log is append-only and tamper-evident when you pin the head hash. Secrets that match known formats are redacted in evidence.

The **Code Engineer** (and Data Analyst) `execute_code` path does **not** go through `gate_tool`. That is a known limitation (R1-2), not a footnote. Do not say "everything is gated." Approvals cover agents running in Hermes, including their calls to external MCP tools. There is no gateway in front of Claude Code, Cursor or other MCP clients.

Full write-up: [Security model](/guide/security).

## Quick start

```bash
git clone https://github.com/pauloberezini/hermes-synapse
cd hermes-synapse
cp .env.example .env
docker compose up -d --build
# Dashboard: http://localhost:9119
# docker logs jarvis-backend | grep "Generated OTP Code"
```

Step-by-step, Ollama, and auto-hire: [Getting started](/guide/getting-started).

## Built by SupplyAlpha.ai

Hermes Synapse is designed and maintained by **Pavel Bereznichenko** at **[SupplyAlpha.ai](https://supplyalpha.ai)**. MIT licensed. Issues and PRs welcome on [GitHub](https://github.com/pauloberezini/hermes-synapse).

<div class="cta-row">
  <a class="primary" href="https://github.com/pauloberezini/hermes-synapse">Star pauloberezini/hermes-synapse</a>
  <a class="ghost" href="./guide/security.html">Read the security model</a>
</div>
