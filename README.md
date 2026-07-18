<div align="center">

# 🏛️ Hermes

**Hermes** is a low-code, self-hosted framework for building managed networks of AI agents. Powered by Jarvis, it combines a beautiful React visual canvas (drag-and-drop node graph) with an autonomous planning backend.

**Build networks of AI agents that plan dynamically, coordinate via DAG, and never spin out of control.**

[![License: MIT](https://img.shields.io/badge/License-MIT-10b981.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11+-3b82f6.svg)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Supported-2563eb.svg)](https://www.docker.com/)
[![GitHub Stars](https://img.shields.io/github/stars/pauloberezini/hermes-synapse?style=social)](https://github.com/pauloberezini/hermes-synapse/stargazers)

## 📸 Dashboard Preview

[![Hermes Synapse Demo Video](https://img.youtube.com/vi/3GFh-1Gglno/maxresdefault.jpg)](https://youtu.be/3GFh-1Gglno)

The built-in Web Dashboard is running on port `9119` and features:
1. **Communication Hub**: Live chat interface with the main orchestrator (Jarvis) or isolated sub-agents.
2. **Core Config**: Real-time adjustment of system prompts, models, and active system properties.
3. **Decision Logs**: Full visual telemetry of the planner's "thoughts", decision latencies, token consumption, and errors.
4. **Memory Vault (RAG)**: Manage vector database documents (PDF, MD, TXT) parsed and indexed dynamically into Qdrant.
5. **System Core Monitor**: Track host system telemetry (CPU/RAM/Disk), running timers, and active price alerts.

---

## 🏛️ System Architecture

```mermaid
graph TD
    User([👤 User]) <--> TG[💬 Telegram Bot]
    User <--> Web[💻 Web Dashboard]
    
    subgraph Backend [Hermes Backend FastAPI]
        Orch[🤖 Root Orchestrator: jarvis]
        SubOrch[Layers: Sub-orchestrator]
        SubAgent[GitBranch: Sub-agent]
        
        Orch --> SubOrch
        Orch --> SubAgent
        SubOrch --> SubAgent
        
        DB[(🗄️ SQLite: history & settings)] <--> Orch
        Qdrant[(🔍 Qdrant: RAG Memory)] <--> SubAgent
    end

    subgraph Inference [Local inference]
        Ollama[🦙 Ollama native API]
        Models[(Local model store)]
        Ollama <--> Models
    end

    Orch <--> Ollama
    SubAgent <--> Ollama
    
    subgraph ExternalServices [Integrations & Tools]
        Google[📅 Google Calendar]
        Todoist[☑️ Todoist]
        Obsidian[📓 Local Obsidian REST]
        WebSearch[🔍 Google Serper Search]
        LocalExec[💻 Local Shell / Sandbox]
    end
    
    SubAgent <--> ExternalServices
    
    style Backend fill:#090d16,stroke:#00f0ff,stroke-width:2px,color:#fff
    style ExternalServices fill:#111622,stroke:#10b981,stroke-width:1.5px,color:#fff
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
| **Self-hosted** | ✅ Docker, SQLite, local LLMs | ✅ | ✅ | ✅ |

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
```
The default setup is local-first and does not require an LLM API key. Optional
Telegram, search, calendar, and cloud-provider keys can be added later.

### 3. Launch the Stack
```bash
docker-compose up -d --build
```
This starts the backend (FastAPI), frontend dashboard (Nginx/React), Ollama,
and the Qdrant vector database. Pull the default model once:

```bash
docker-compose exec ollama ollama pull hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_M
```

You can also pull and delete models from **System Core Parameters → Ollama Models**.

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

### 🤖 Ollama and model providers

Ollama is the default provider and uses its **native API**, including streamed
chat responses, tool calls, thinking output, usage counters, model inspection,
pull progress, unload, and deletion. No placeholder API key or `/v1` compatibility
endpoint is required.

For a host installation, use:

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
# Optional for a protected remote Ollama server:
OLLAMA_API_KEY=
LLM_MODEL=hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_M
OLLAMA_NUM_CTX=262144
OLLAMA_KEEP_ALIVE=-1
OLLAMA_THINK=false
OLLAMA_FLASH_ATTENTION=1
OLLAMA_KV_CACHE_TYPE=q8_0
```

Docker Compose automatically changes the internal URL to `http://ollama:11434`.
OpenRouter and other OpenAI-compatible providers remain available from the
dashboard provider selector or through `LLM_PROVIDER=openrouter` /
`LLM_PROVIDER=openai_compatible` and `LLM_API_BASE`.

You can also override models per specialized agent role using the following env variables:
* `AGENT_MODEL_RESEARCH` (Research Agent)
* `AGENT_MODEL_CODE` (Code Engineer)
* `AGENT_MODEL_PLANNER` (Planner Agent)

#### 🎨 Model Selection in the Web UI
When creating or editing sub-agents on the visual canvas dashboard:
* For Ollama, the model dropdown discovers installed models through `/api/tags`.
* The Ollama panel shows connectivity, server version, installed/running models, and pull progress.
* Chat text is rendered incrementally as Ollama emits NDJSON chunks; cancellation preserves the partial response.
* If a model is not listed, or you prefer to specify a custom model name manually, select **"Custom model..."** from the dropdown menu and type the exact model identifier directly in the input field.

### 💬 Telegram Integration
1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram and retrieve the token (`TELEGRAM_BOT_TOKEN`).
2. Get your numeric Telegram chat ID via [@userinfobot](https://t.me/userinfobot) and set `TELEGRAM_CHAT_ID`.
3. Start the bot on Telegram by typing `/start`.
4. Voice messages are supported when local STT is enabled. Send a Telegram voice message and Jarvis will transcribe it locally, echo the recognized text, and process it like a normal command.

### 🎙️ Local Voice Assistant
Hermes uses `faster-whisper` for free local speech-to-text. The web dashboard records audio with the browser `MediaRecorder` API and sends it to `/api/voice/transcribe`; Telegram voice notes use the same backend pipeline. Browsers expose microphones only in a secure context, so remote web voice input requires HTTPS; `http://localhost` also works for an SSH-tunnel connection.

Recommended defaults:
* `VOICE_STT_MODEL=small`
* `VOICE_STT_DEVICE=cpu`
* `VOICE_STT_COMPUTE_TYPE=int8`
* `VOICE_STT_LANGUAGE=ru`
* `VOICE_STT_DOWNLOAD_ROOT=/app/backend/data/voice-models`
* `VOICE_STT_PRELOAD=true`
* `VOICE_TTS_ENABLED=true`
* `VOICE_TTS_PROVIDER=rhvoice`
* `VOICE_TTS_VOICE=anna`

The first transcription downloads the selected Whisper model. Rebuild the backend image after changing dependencies:
```bash
docker-compose up -d --build backend
```

### 📅 Google Calendar (OAuth2 Manual Flow)
If you wish to allow Hermes to manage your calendars:
1. Place your Google API desktop app OAuth credentials as `client_secret_*.json` in the root folder.
2. Ensure you have the required dependencies and run the local auth script on your host system:
   ```bash
   pip3 install google-auth-oauthlib google-api-python-client
   python3 backend/google_auth.py
   ```
3. Complete the login flow. The generated `google_token.json` is automatically mapped into the docker container.

### 📓 Local Obsidian REST Integration
1. With the root `hermes-web/docker-compose.yml`, Obsidian runs as a local web app at `https://127.0.0.1:3001`.
2. The Obsidian config and vault data are stored under `hermes-web/obsidian`.
3. Install the **Local REST API** plugin in Obsidian.
4. Enable HTTPS, set the plugin port to `27124`, and copy the generated API key.
5. Configure `OBSIDIAN_API_KEY`, `OBSIDIAN_PORT`, and `OBSIDIAN_VAULT_PATH` in `.env`. Hermes will sync and index your vault chunks into the Qdrant RAG index in the background.

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
# Default: SQLite (zero config, WAL mode enabled automatically)
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
│   ├── database.py       # SQLite/PostgreSQL backend abstraction
│   ├── rag.py            # Qdrant vector memory
│   ├── tools.py          # All skill tool implementations
│   └── subagents.py      # Specialized agent classes
├── frontend/             # React + Vite dashboard
├── docker-compose.yml    # Production stack
├── docker-compose.dev.yml # Development stack (hot-reload)
└── .env.example          # Configuration template
```

---

## 🛣️ Roadmap

- [x] Visual SVG canvas with drag-and-drop wiring
- [x] DAG hierarchical orchestration with planning loop
- [x] SQLite + PostgreSQL pluggable backend
- [x] Qdrant RAG memory with fastembed (local embeddings)
- [x] Python code sandbox with self-correction loop
- [x] Telegram bot interface
- [ ] **Plugin SDK** — `pip install hermes-sdk` → write your own skills
- [ ] **Skills Marketplace** — community-contributed connectors
- [ ] **Voice interface** — Whisper STT + TTS replies
- [ ] **SaaS mode** — multi-tenant namespace isolation

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

## LLM diagnostics and retry policy

All OpenAI-compatible provider responses are normalized into explicit statuses:
`success`, `tool_call`, `empty`, `refusal`, `timeout`, `provider_error`, and
`parse_error`. Chat technical details expose only safe metadata (model,
provider request ID, finish reason, latency, tokens and cost), never raw provider
bodies or API keys.

Configure resilience with `LLM_REQUEST_TIMEOUT`, `LLM_MAX_RETRIES`, and
`LLM_MAX_TOOL_ITERATIONS`. Transient transport failures use bounded exponential
backoff with jitter. Automatic retry is disabled after a tool may have produced
side effects. The chat Stop action cancels the active backend coroutine by run
ID; in a multi-worker deployment this registry must be backed by a shared queue.

For local checks, install the backend dev group and use `python -m pytest`. In
`frontend`, use an actively supported Node release, then run `npm run lint`,
`npm test`, and `npm run build`. Tests mock provider calls and do not use paid
APIs. The architecture/threat audit is in
`../docs/product-and-architecture-audit.md`; the P2 roadmap is in
`../docs/product-roadmap.md`.

## 🛡️ License

MIT License — see [LICENSE](LICENSE) for details.

---

<div align="center">

**If Hermes saved you from rewriting a multi-agent spaghetti pipeline, give us a ⭐**

[⭐ Star on GitHub](https://github.com/pauloberezini/hermes-synapse) · [🐛 Report Bug](https://github.com/pauloberezini/hermes-synapse/issues) · [💡 Request Feature](https://github.com/pauloberezini/hermes-synapse/issues)

</div>
