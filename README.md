<div align="center">

# Hermes Synapse

### Open-source multi-agent orchestrator with human approval gates

Agents plan on a DAG, inherit only the tools their parent allows, and stop on risky calls until a human approves that exact payload — once.

[![License: MIT](https://img.shields.io/badge/License-MIT-10b981.svg)](LICENSE)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11+-3b82f6.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Supported-2563eb.svg)](https://www.docker.com/)
[![GitHub Stars](https://img.shields.io/github/stars/pauloberezini/hermes-synapse?style=social)](https://github.com/pauloberezini/hermes-synapse/stargazers)

```bash
git clone https://github.com/pauloberezini/hermes-synapse && cd hermes-synapse
cp .env.example .env  # add your LLM API key
docker compose up -d
# Open → http://localhost:9119
```

</div>

---

## Why

Most multi-agent stacks are either **hardwired workflows** or **unbounded chat loops**. Hermes sits in the middle:

- A visual DAG of orchestrators and specialists — no cycles, no privilege escalation through children.
- Dynamic LLM planning, not a hardcoded pipeline.
- A real gate on risky tools: approve the claim, then the agent must send the **same** call again before anything runs.

Self-hosted. MIT. Docker Compose.

---

## Quick start

> **Requirements:** Docker + Docker Compose.

```bash
# 1. Clone
git clone https://github.com/pauloberezini/hermes-synapse
cd hermes-synapse

# 2. Configure (only OPENROUTER_API_KEY is required — everything else is optional)
cp .env.example .env

# 3. Launch
docker compose up -d --build

# 4. Open dashboard
open http://localhost:9119
# Login code is sent to Telegram and printed in the backend log:
# docker logs jarvis-backend | grep "Generated OTP Code"
```

**Local model (Ollama):** in `.env`:

```bash
LLM_API_BASE=http://host.docker.internal:11434/v1
LLM_MODEL=llama3
OPENROUTER_API_KEY=local  # any non-empty placeholder
```

Dev hot-reload: `docker compose -f docker-compose.dev.yml up` (UI on http://localhost:5173).

---

## See it in action

Local rehearsal, 29 Oct 2026. Prompt: *Ask Sys Ops to run `df -h /` on the server.* No secrets in these frames.

**1. A Sys Ops shell call stops at PENDING in chat**

![Sys Ops execute_command waiting for approval; live badge on the Approvals icon](docs/images/01_chat_sysops_pending_live_badge.jpg)

**2. Approval modal with claim, source, and hash**

![Governance Approvals modal showing CLAIM, SOURCE, args, and bundle hash](docs/images/03b_modal_claim_source_crop.png)

**3. After approve, re-sending the exact call runs it once**

![Same chat after approve + resend: command ran once, exit_code 0](docs/images/06_chat_resend_runs_once.jpg)

Approving does not execute anything. Send the same request again in the **same chat**; the gate consumes the approval and Sys Ops runs the command once. Send it a third time and you get a **new PENDING** — approvals are single-use. The **All** tab lists PENDING, APPROVED, and CONSUMED.

**4. Offline verification of the exported decision log passes; a tampered copy fails**

![curl verify ok, offline --pin ok, three tamper cases fail](docs/images/10_export_offline_verify_ok_and_tamper_fail.png)

Canvas / Telegram walkthrough (3 min): [YouTube](https://youtu.be/3GFh-1Gglno).

---

## How approvals work

Risky tool calls go through `gate_tool` (`backend/tools.py` → `backend/governance.py`) **before** the tool body.

| What | Rule |
|---|---|
| Sys Ops `execute_command` | Always gated |
| Other high-risk names | Always gated (`create_obsidian_note`, agent mutations, audit export, …) |
| MCP tools | Gated by default. Opt out with `readOnlyHint: true` or `destructiveHint: false` |

**Lifecycle** (scoped to the chat session, bound to the exact JSON payload):

```
PENDING → APPROVED → CONSUMED
```

1. The tool returns `PENDING_APPROVAL`. Nothing runs.
2. A human opens **Governance Approvals**, checks **CLAIM** (agent, tool, args, hash) and **SOURCE** (plan step / user instruction), then Approve or Reject.
3. Approve **does not run the tool**. The agent must re-send the **identical** call in the **same** chat. That send consumes the row and runs once.
4. The same call afterwards opens a **new PENDING**. A rejected call stays blocked in that session.

The modal has **Pending** and **All** tabs. Full walkthrough: [docs/guide/approvals.md](docs/guide/approvals.md).

---

## Decision log

Every `REQUESTED` / `APPROVED` / `REJECTED` / `CONSUMED` event is appended to a hash chain (`approval_decisions`). Export is a zip of `decisions.jsonl`, `evidence/<id>.json`, `manifest.json`, and `VERIFY.md`.

```bash
# After login; governance routes need a Bearer token
TOKEN=<session token>

curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/governance/decisions/verify

curl -fs -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/governance/decisions/export.zip \
  -o export.zip
# /api/governance/decisions/export is the same archive

python3 scripts/verify_decision_log.py export.zip --pin <head_hash>
# ok checked=N head=H
```

Tampering with evidence **inputs** (the approved command) fails with `bundle_hash mismatch`. Editing a decision row fails with `entry_hash mismatch`. Dropping a row fails with `count mismatch`. `--pin` catches a truncated tail whose manifest was rewritten to match.

---

## Known limitations

- **`bundle_hash` does not cover evidence `description` or `links`.** Inputs, plan, upstream item hashes, and flags are in the digest; changing only the human-readable description still verifies. Treat those fields as display, not proof.
- **The Code Engineer is not gated.** It runs generated Python in the sandbox via `execute_code` and never calls `gate_tool`. Open roadmap item — do not claim every agent is gated.
- The log is **tamper-evident, not signed**. A party who rewrites the whole chain *and* the head hash you pinned can still pass the checker. Keep `--pin` on a head you recorded yourself.

More: [ROADMAP.md](ROADMAP.md) · [docs/specs/roadmap](docs/specs/roadmap/README.md).

---

## Architecture

```
User ──→ Web Dashboard (React)
           │
           ▼
     Root Orchestrator (Jarvis)          ← DAG entry point
          / \
   Sub-Orch  Sub-Agent                   ← Hierarchical delegation
        |         |
   Sub-Agents   Skills                   ← Tools: web_search, python_sandbox, ...

AllowedTools = ChildTools ∩ ParentTools  ← Permission intersection
```

A child cannot gain `execute_command` just because it lists `shell_execution`. Auto-hired specialists are capped the same way.

---

## Built-in agents (seeded on first launch)

| Agent | Skills | Required keys |
|---|---|---|
| **Jarvis (Main)** — root orchestrator | — | `OPENROUTER_API_KEY` |
| **Search Agent** | Web search, weather, RSS | `SEARXNG_URL` |
| **Code Engineer** | Python sandbox (not gated — see limitations) | — |
| **Data Analyst** | pandas + matplotlib | — |
| **Scheduler** | Timers, reminders, alarms | — |
| **Market Monitor** | Stocks + crypto (yfinance) | — |
| **Daily Planner** | Google Calendar + Todoist | `TODOIST_API_TOKEN` + Google OAuth |
| **Sys Ops** | System stats + shell (`execute_command` is gated) | — |
| **Football Analyst** | Match results, tactics, standings | `SEARXNG_URL` |

Agents start even if their keys are missing; they return a message saying what to configure.

---

## Configuration

**Any OpenAI-compatible API:**

```bash
# OpenRouter (default)
LLM_API_BASE=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=your_key

# Ollama
LLM_API_BASE=http://host.docker.internal:11434/v1
LLM_MODEL=llama3.1
```

Per-agent overrides: `AGENT_MODEL_CODE`, `AGENT_MODEL_RESEARCH`, `AGENT_MODEL_ANALYST`, `AGENT_MODEL_PLANNER`.

PostgreSQL (Compose default): `DATABASE_URL=postgresql://user:password@localhost:5432/hermes`. Leave empty only for local SQLite.

| Integration | Env var |
|---|---|
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Web search | `SEARXNG_URL` (SearXNG) |
| Weather | `OPENWEATHERMAP_API_KEY` |
| Todoist | `TODOIST_API_TOKEN` |
| Google Calendar | OAuth JSON — see `.env.example` |
| Obsidian RAG | `OBSIDIAN_API_KEY` |

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
git clone https://github.com/pauloberezini/hermes-synapse
cd hermes-synapse
docker compose -f docker-compose.dev.yml up
```

---

## License

MIT — see [LICENSE](LICENSE).

---

<div align="center">

[⭐ Star on GitHub](https://github.com/pauloberezini/hermes-synapse) · [🐛 Issues](https://github.com/pauloberezini/hermes-synapse/issues)

</div>
