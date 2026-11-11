---
title: Integrations
description: LLM providers, MCP, plugins, Telegram, SearXNG, Obsidian, calendars, market data, PostgreSQL, Qdrant, and the hermes_sdk that Hermes Synapse actually implements.
---

# Integrations

Only connectors the repository implements are listed. Optional keys degrade cleanly: the agent tells you what is missing instead of crashing. Configure everything in `.env` (see `.env.example`).

## LLM providers

Hermes talks to any **OpenAI-compatible** chat completions API.

| Provider | Configuration |
|---|---|
| [OpenRouter](https://openrouter.ai) (default) | `LLM_API_BASE=https://openrouter.ai/api/v1` and `OPENROUTER_API_KEY` |
| [Ollama](https://ollama.com) | `LLM_API_BASE=http://host.docker.internal:11434/v1`, `LLM_MODEL=llama3`, any non-empty placeholder key |
| vLLM / LM Studio / LocalAI | Point `LLM_API_BASE` at that server's `/v1` endpoint |

Per-agent overrides: `AGENT_MODEL_CODE`, `AGENT_MODEL_RESEARCH`, `AGENT_MODEL_ANALYST`, `AGENT_MODEL_PLANNER`, `AGENT_MODEL_SPECIALIST`. `COMPLEXITY_ROUTING` can send simple turns around the planner.

## MCP

The dashboard MCP tab and `backend/mcp_client.py` connect to servers listed in `mcp_config.json`. On connect, each tool is registered into `TOOLS_SCHEMA`.

Write-shaped MCP tools wait for a human. A tool skips the gate only when its annotations say `readOnlyHint: true` or `destructiveHint: false`. Missing annotations follow MCP defaults (not read-only, destructive) and wait.

An OpenAPI-to-MCP helper lives at `backend/mcp_openapi_proxy.py` if you need to wrap a REST spec. It is a helper, not a hosted third-party service we ship.

## Plugin boundary and SDK

| Surface | Role |
|---|---|
| `backend/<name>/plugin.py` | Discovered at startup. Core calls hooks (`init_plugin`, `get_extra_agents`, `extra_tool_schemas`, `high_risk_tools`, `market_data_provider`, `handle_fast_command`, `resolve_cron_job`, …) and **never imports a plugin by name**. Proprietary engines stay out of the OSS tree. |
| [`hermes_sdk`](https://github.com/pauloberezini/hermes-synapse/tree/main/hermes_sdk) | `@skill` / `@tool` decorator API for community packages. `hermes_sdk/examples/github_skill.py` is a template, not a seeded GitHub connector. |
| Skills marketplace | `/api/marketplace/*` registry. Default billing is `NoOpBillingAdapter` (free). `StripeBillingAdapter` is used only when `STRIPE_SECRET_KEY` is set (`backend/marketplace/billing_adapter.py`). |
| Auto-hire | `AUTO_HIRE=ask` (default), `on`, or `off`. New specialists are skill-capped to the parent orchestrator. |
| Agent mesh | `backend/mesh.py` `AgentMeshRouter` for capability matching, discovery, and delegation. |

## Chat, voice, search, knowledge

| Integration | Env / notes |
|---|---|
| Telegram bot | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `TELEGRAM_ADMIN_ID` - OTP delivery and agent chat |
| Voice | Browser `SpeechRecognition` (mic) and `speechSynthesis` (spoken replies) in the dashboard. Not a local Whisper / Silero stack. |
| [SearXNG](https://github.com/searxng/searxng) | `SEARXNG_URL` - self-hosted metasearch. No paid search API key. |
| OpenWeatherMap | `OPENWEATHERMAP_API_KEY` |
| Obsidian Local REST API | `OBSIDIAN_API_KEY`, `OBSIDIAN_HOST`, `OBSIDIAN_PORT`, `OBSIDIAN_VAULT_PATH`. Creating a note is high-risk. |
| Qdrant | Vector memory / RAG. Compose service on port 6333. |
| GraphRAG | Optional entity graph (`backend/graphrag.py`) |
| RSS | Built-in RSS skill and dashboard tab |

## Productivity and markets

| Integration | Env / notes |
|---|---|
| Todoist | `TODOIST_API_TOKEN`. Deleting a task is high-risk. |
| Google Calendar | OAuth2 desktop credentials via `GOOGLE_CLIENT_SECRET_PATH` / `backend/google_auth.py` |
| Timers and alarms | Built-in `timers_alarms` skill, persisted with APScheduler |
| Market data | Default `MARKET_DATA_PROVIDER=http`: CoinGecko (crypto) + Yahoo Finance (stocks), no API key. Other names resolve through the plugin `market_data_provider` hook. |

## Data plane and deploy

| Piece | Notes |
|---|---|
| PostgreSQL 16 | Required in Compose (`DATABASE_URL`). SQLite remains for some local/dev paths. |
| Hugging Face FastEmbed | `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` for local embeddings |
| Docker Compose | Production-style stack, UI on [http://localhost:9119](http://localhost:9119) |
| Dev Compose | Hot reload, UI on [http://localhost:5173](http://localhost:5173) |
| Swarm / Kubernetes | `docker-compose.swarm.yml`, `k8s/` |

## Seeded agents

Created on first launch (`backend/database.py` `_get_default_agents`). Missing keys do not crash the process.

| Agent | Skills |
|---|---|
| Jarvis (Main) | Root orchestrator |
| Search Agent | `web_search` |
| Code Engineer | `python_sandbox` (not approval-gated; see [Security](./security.md#known-limitations)) |
| Data Analyst | `python_sandbox` |
| Scheduler | `timers_alarms` |
| Market Monitor | `market_monitor` |
| Daily Planner | `google_calendar`, `todoist_sync` |
| Sys Ops | `shell_execution` |
| Football Analyst | `web_search` |

OSS team presets: **Engineering Shop** and **OSINT Bureau**. Plugins may add more.

## Not claimed

These exist nearby in the tree but are **not** documented as shipped product integrations:

- Whisper.cpp / Silero / Coqui (mentioned in ROADMAP, not wired as the dashboard voice path)
- A built-in GitHub.com connector (`hermes_sdk` example only; `backend/tools/github_ci.py` is not registered in `TOOLS_SCHEMA`)
- A bundled trading / broker engine (that lives behind the plugin boundary, not in OSS)
