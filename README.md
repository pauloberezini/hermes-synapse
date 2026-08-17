<div align="center">

# 🏛️ Hermes

### The Visual, Hierarchical AI Agent Framework

**Build networks of AI agents that plan dynamically, coordinate via DAG, and never spin out of control.**

[![License: MIT](https://img.shields.io/badge/License-MIT-10b981.svg)](https://opensource.org/licenses/MIT)
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

## ✨ Why Hermes?

Most multi-agent frameworks are either **too rigid** (n8n: hardwired workflows) or **too chaotic** (AutoGen: agents talking in circles forever).

**Hermes sits in the middle:** a visual drag-and-drop canvas where you wire up AI agents in a strict **Directed Acyclic Graph (DAG)**. No infinite loops. No hardcoded pipelines. Just agents that actually coordinate.

| | Hermes | n8n / Make | Flowise / LangFlow | AutoGen / CrewAI |
|---|---|---|---|---|
| **Execution** | 🧠 Non-deterministic (AI plans dynamically) | 🔧 Deterministic (hardcoded steps) | 🔗 Visual LLM chains | 💬 Conversational loops |
| **UI** | 🎨 SVG canvas + isolated agent chats | Node editor | Visual chain designer | CLI / API only |
| **Hierarchy** | ✅ Strict DAG (cycle-safe) | ↪ Linear / conditional | Data-flow graphs | ⚠️ Free loops (cycle risk) |
| **Security** | 🔐 Permission Intersection | Hardcoded auth | Sandbox container | Local exec by default |
| **Self-hosted** | ✅ Docker, PostgreSQL, local LLMs | ✅ | ✅ | ✅ |

---

## 📸 Demo

[![Hermes Synapse Demo](https://img.youtube.com/vi/3GFh-1Gglno/maxresdefault.jpg)](https://youtu.be/3GFh-1Gglno)

*👆 Click to watch — canvas node wiring, Telegram integration, and live DAG planning in 3 minutes.*

---

## 🚀 Quick Start

> **Requirements:** Docker + Docker Compose. That's it.

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
```

**Want to use a local model (Ollama)?** Set in `.env`:
```bash
LLM_API_BASE=http://host.docker.internal:11434/v1
LLM_MODEL=llama3
OPENROUTER_API_KEY=local  # any non-empty placeholder
```

---

## 🏛️ Architecture

```
User ──→ Web Dashboard (React Canvas)
           │
           ▼
     🤖 Root Orchestrator (Jarvis)       ← DAG entry point
          / \
   Sub-Orch  Sub-Agent                   ← Hierarchical delegation
        |         |
   Sub-Agents   Skills                   ← Tools: web_search, python_sandbox, ...

AllowedTools = ChildTools ∩ ParentTools  ← Permission Intersection (security)
```

**Key concepts:**
- **Root Orchestrator** — entry point, plans and routes tasks
- **Sub-orchestrators** — coordinate groups of specialized agents  
- **Sub-agents** — specialized executors with their own system prompts
- **Skills** — pluggable tool sets (web search, code sandbox, calendar, RAG...)

---

## 🧩 Advanced Modules & Capabilities

Hermes goes beyond simple chat agents. It is designed for complex, autonomous operations:
- 🏢 **2.5D Pixel Office & Telemetry**: Visualize your agent workforce in real-time. Watch tasks route through intelligent office zones (Meeting Rooms, Desks, Lounge).
- 🛡️ **Paperclip Governance (Control Plane)**: Enforce hard limits with **BudgetGuard** token/dollar spend tracking, and require **Human-in-the-loop** approvals for high-stakes tool executions. Tasks are managed on an atomic Kanban ticket board.
- 🕸️ **Autonomous Agent Mesh**: P2P protocol for inter-agent capability matching, discovery, and task delegation.
- 📈 **BCM Trading Engine**: Autonomous financial engine integrated with CCXT (100+ exchanges) and a built-in Compliance Officer.
- 🗣️ **Voice & Speech**: Integrated local Whisper STT (Speech-to-Text) and TTS for seamless voice interactions.
- 🏢 **Enterprise Ready**: Full OIDC / OAuth2 support, Role-Based Access Control (RBAC), and PostgreSQL database.

---

## 🤖 Built-in Agents (seeded on first launch)

| Agent | Skills | Required Keys |
|---|---|---|
| 🏛️ **Jarvis (Main)** — root orchestrator | — | `OPENROUTER_API_KEY` |
| 🔍 **Search Agent** | Web search, weather, RSS | `SERPER_API_KEY` |
| 💻 **Code Engineer** | Python sandbox (self-correcting) | — |
| 📊 **Data Analyst** | pandas + matplotlib charts | — |
| ⏰ **Scheduler** | Timers, reminders, alarms | — |
| 📈 **Market Monitor** | Stocks + crypto (yfinance) | — |
| 📅 **Daily Planner** | Google Calendar + Todoist | `TODOIST_API_TOKEN` + Google OAuth |
| 🖥️ **Sys Ops** | System stats + shell exec | — |
| ⚽ **Football Analyst** | Match results, tactics, standings | `SERPER_API_KEY` |

> All agents start without error even if their API keys are missing — they return a clear message explaining what needs to be configured.

---

## ⚙️ Configuration

### LLM Providers

Hermes supports **any OpenAI-compatible API**:

```bash
# OpenRouter (default) — access 200+ models
LLM_API_BASE=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=your_key

# Ollama (local)
LLM_API_BASE=http://host.docker.internal:11434/v1
LLM_MODEL=llama3.1

# vLLM / LM Studio / LocalAI — same pattern
LLM_API_BASE=http://localhost:8000/v1
```

### Per-Agent Model Overrides

```bash
AGENT_MODEL_CODE=deepseek/deepseek-r1       # Heavy reasoning for code
AGENT_MODEL_RESEARCH=google/gemini-2.5-flash # Fast for search
AGENT_MODEL_ANALYST=openai/gpt-4o           # Visual for charts
```

### Database Backends

```bash
# DATABASE_URL=   ← leave empty

# PostgreSQL (production / SaaS mode):
DATABASE_URL=postgresql://user:password@localhost:5432/hermes
```

### Optional Integrations

| Integration | Env Var | Notes |
|---|---|---|
| Telegram Bot | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Create via [@BotFather](https://t.me/BotFather) |
| Web Search | `SERPER_API_KEY` | [serper.dev](https://serper.dev) — 2,500 free/month |
| Weather | `OPENWEATHERMAP_API_KEY` | Free tier: 1,000 calls/day |
| Todoist | `TODOIST_API_TOKEN` | Todoist Settings → Integrations |
| Google Calendar | OAuth2 JSON file | See `.env.example` for setup |
| Obsidian RAG | `OBSIDIAN_API_KEY` | [Local REST API plugin](https://github.com/coddingtonbear/obsidian-local-rest-api) |

---

## 🔐 Security: Permission Intersection

Hermes enforces a security constraint down the execution tree:

```
AllowedTools(agent) = agent.skills ∩ parent.skills
```

If a parent sub-orchestrator only has `web_search`, its child agents **cannot** call `execute_command`, even if they have `shell_execution` configured. This prevents privilege escalation through agent chains.

---

## 📂 Project Structure

```
hermes-synapse/
├── backend/              # FastAPI server
│   ├── main.py           # API routes
│   ├── agent.py          # Core LLM orchestration loop
│   ├── orchestrator.py   # DAG planner
│   ├── database.py       # PostgreSQL backend
│   ├── rag.py            # Qdrant vector memory
│   ├── tools.py          # All skill tool implementations
│   └── subagents.py      # Specialized agent classes
├── frontend/             # React + Vite dashboard
├── k8s/                  # Kubernetes Deployment Manifests
├── docker-compose.yml    # Production stack (Docker)
├── docker-compose.swarm.yml # Docker Swarm Stack
├── docker-compose.dev.yml # Development stack (hot-reload)
└── .env.example          # Configuration template
```

---

## 🛣️ Roadmap

- [x] Visual SVG canvas & 2.5D Pixel Office telemetry
- [x] DAG hierarchical orchestration with planning loop
- [x] PostgreSQL database backend
- [x] Qdrant RAG & GraphRAG memory
- [x] Python code sandbox with self-correction loop
- [x] Telegram bot interface
- [x] **Open-Core Skills Marketplace** & **MCP Server Support**
- [x] **Plugin SDK** — `hermes_sdk` for custom skills & dataset exporters
- [x] **Voice interface** — Whisper STT + TTS replies
- [x] **Enterprise SSO & SaaS mode** — OIDC/OAuth2, RBAC, namespace isolation
- [x] **Paperclip Governance** — BudgetGuard, Kanban board, Human-in-the-loop approvals
- [x] **Autonomous P2P Agent Mesh** — Decentralized agent communication
- [ ] **Production Multi-Cluster Agent Mesh** — Cross-cloud distributed execution
- [ ] **Real-Time WebRTC Voice & Multimodal Gateway**
- [ ] **Skills Marketplace Monetization & Billing Engine**

See full [ROADMAP.md](ROADMAP.md) for the detailed specification.

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) to get started.

Quick setup for development:
```bash
git clone https://github.com/pauloberezini/hermes-synapse
cd hermes-synapse
docker compose -f docker-compose.dev.yml up  # hot-reload mode
```

---

## 🛡️ License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**If Hermes saved you from rewriting a multi-agent spaghetti pipeline, give us a ⭐**

[⭐ Star on GitHub](https://github.com/pauloberezini/hermes-synapse) · [🐛 Report Bug](https://github.com/pauloberezini/hermes-synapse/issues) · [💡 Request Feature](https://github.com/pauloberezini/hermes-synapse/issues)

</div>
