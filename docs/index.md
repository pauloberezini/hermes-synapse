---
layout: home
title: Approve the exact call your AI agent is about to make
titleTemplate: :title | Hermes Synapse
description: Hermes Synapse is a self-hosted approval layer for AI agents that touch money or production systems. An approval covers one payload and works once. Every step lands in a hash-chained log you can check offline.
head:
  - - meta
    - name: keywords
      content: Hermes Synapse, AI agent governance, human-in-the-loop, approval gate, runtime governance, multi-agent orchestrator, MCP, decision log, SupplyAlpha
hero:
  name: HERMES SYNAPSE
  text: Approve the exact call your AI agent is about to make.
  tagline: Hermes Synapse is a self-hosted approval layer for AI agents that touch money or production systems. An approval covers one payload and works once. Every step lands in a hash-chained log you can check offline.
  image:
    src: /og-image.png
    alt: Hermes Synapse Communication Link showing a Sys Ops command waiting for human approval
  actions:
    - theme: brand
      text: Run the approvals demo
      link: /guide/approvals
    - theme: alt
      text: Become a design partner
      link: https://www.linkedin.com/in/pauloberezini/

features:
  - title: The agent asks and you decide.
    details: Approving only records your decision. The agent then sends the same call again, and that call runs once. After that, the same call creates a new pending request.
  - title: An auditor can check the log without us.
    details: Requests, approvals, rejections and uses are chained with SHA-256. Export it and run one Python script. It needs no Hermes install and no network.
  - title: It runs on your own machines with Docker Compose, under the MIT license.
    details: Any OpenAI-compatible model works, including a local one. MCP tools that are not marked read-only wait for a human by default.
---

## Why Hermes Synapse

- A visual DAG of orchestrators and specialists. No cycles. Children inherit only the intersection of their skills and the parent's.
- Dynamic LLM planning, not a hardcoded pipeline.
- A real gate on risky tools: the operator reviews the claim and the source, approves a payload hash, then the agent must send the **same** call again before anything runs. A replay is a new `PENDING` request, not a free pass.
- An append-only, hash-chained decision log you can export and check with `scripts/verify_decision_log.py`. No Hermes install. No network.

Self-hosted. MIT. Docker Compose. Built by [Pavel Bereznichenko](https://github.com/pauloberezini) at [SupplyAlpha.ai](https://supplyalpha.ai).

How it compares to Microsoft Agent Governance Toolkit, LangGraph human-in-the-loop, and a Slack button: [comparison](/guide/comparison).

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

The **Code Engineer** (and Data Analyst) `execute_code` path does **not** go through `gate_tool`. That is a known limitation (R1-2), not a footnote. Do not say "everything is gated."

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
