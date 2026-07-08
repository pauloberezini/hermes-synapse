# 🏛️ Hermes: Light Hierarchical AI Agent Network with Visual Canvas

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker: Supported](https://img.shields.io/badge/Docker-Supported-blue.svg)](https://www.docker.com/)

**Hermes** is a low-code, self-hosted framework for building managed networks of AI agents. Inspired by JARVIS, it combines a beautiful React visual canvas (drag-and-drop node graph) with an autonomous planning backend.

Unlike deterministic workflow builders (like n8n), Hermes resolves complex user requests on the fly using a dynamic LLM planning loop. Unlike chaotic multi-agent groups (like AutoGen), Hermes uses a strict Directed Acyclic Graph (DAG) hierarchy to keep agents coordinated and prevent infinite feedback loops.

---

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

### 🔐 Security & Permission Intersection
To execute actions safely, Hermes implements **Permission Intersection** down the execution tree:
`AllowedTools = ChildTools ∩ ParentTools`

If a parent sub-orchestrator restricts tools to `web_search`, its child sub-agents can never invoke dangerous actions like `execute_command`, even if those agents have the command line skill configured.

---

## 🚀 Quick Start

Ensure you have **Docker** and **Docker Compose** installed.

### 1. Clone the repository
```bash
git clone https://github.com/your-username/hermes.git
cd hermes
```

### 2. Configure Environment Variables
Copy the template configuration file:
```bash
cp .env.example .env
```
Open `.env` and fill in your keys (at minimum, `OPENROUTER_API_KEY`, `TELEGRAM_BOT_TOKEN`, and `TELEGRAM_CHAT_ID` are required).

### 3. Launch the Stack
```bash
docker compose up -d --build
```
This starts the backend (FastAPI), frontend dashboard (Nginx/React), and vector database (Qdrant).

### 4. Access the Dashboard
Open your browser and navigate to:
```
http://localhost:9119
```

*Sir, your dashboard is online.*

---

## ⚙️ Configuration & Integrations

Hermes starts gracefully even if optional integrations are not configured.

### 🤖 LLM Models (OpenRouter & Local / Custom Providers)
By default, Hermes uses OpenRouter. However, it supports **any OpenAI-compatible API** (such as **Ollama**, **vLLM**, **LM Studio**, **LocalAI**, etc.).

To use a local or custom provider:
1. Open your `.env` file.
2. Set `LLM_API_BASE` to your provider's local endpoint (e.g., `http://localhost:11434/v1` for Ollama or `http://localhost:8000/v1` for vLLM).
3. Set `LLM_MODEL` to your local model name (e.g., `llama3`, `mistral`, or `deepseek-coder`).
4. Set `OPENROUTER_API_KEY` to any non-empty placeholder value (e.g., `local` or `dummy`), as the backend requires a non-empty key parameter to initialize.

You can also override models per specialized agent role using the following env variables:
* `AGENT_MODEL_RESEARCH` (Research Agent)
* `AGENT_MODEL_CODE` (Code Engineer)
* `AGENT_MODEL_ANALYST` (Data Analyst)
* `AGENT_MODEL_PLANNER` (Planner Agent)

#### 🎨 Model Selection in the Web UI
When creating or editing sub-agents on the visual canvas dashboard:
* The model dropdown automatically fetches and displays all active models from your configured `LLM_API_BASE` `/models` endpoint (so local models will appear automatically).
* If a model is not listed, or you prefer to specify a custom model name manually, select **"Custom model..."** from the dropdown menu and type the exact model identifier directly in the input field.

### 💬 Telegram Integration
1. Create a bot via [@BotFather](https://t.me/BotFather) on Telegram and retrieve the token (`TELEGRAM_BOT_TOKEN`).
2. Get your numeric Telegram chat ID via [@userinfobot](https://t.me/userinfobot) and set `TELEGRAM_CHAT_ID`.
3. Start the bot on Telegram by typing `/start`.

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
1. Install the **Local REST API** plugin in Obsidian.
2. Enable HTTPS and copy the generated API key.
3. Configure `OBSIDIAN_API_KEY`, `OBSIDIAN_PORT`, and `OBSIDIAN_VAULT_PATH` in `.env`. Hermes will sync and index your vault chunks into the Qdrant RAG index in the background.

---

## 🤖 Default Agents

On first launch, Hermes seeds the following 9 agents into the database automatically. All agents work out of the box — skills that require API keys will gracefully degrade to mock data until the key is provided.

| Agent | Description | Required Keys |
|-------|-------------|---------------|
| 🏛️ **Jarvis (Main)** | Root orchestrator — routes tasks to sub-agents | `OPENROUTER_API_KEY` |
| 🔍 **Search Agent** | Web search, weather, RSS news digest | `SERPER_API_KEY`, `OPENWEATHERMAP_API_KEY` |
| 💻 **Code Engineer** | Writes and executes Python code in a sandbox | `OPENROUTER_API_KEY` |
| 📊 **Data Analyst** | Data analysis, statistics, charts (matplotlib, pandas) | `OPENROUTER_API_KEY` |
| ⏰ **Scheduler** | Timers, reminders, and alarms | `OPENROUTER_API_KEY` |
| 📈 **Market Monitor** | Real-time stock & crypto prices, price alerts | `OPENROUTER_API_KEY` *(powered by yfinance, no extra key)* |
| 📅 **Daily Planner** | Google Calendar events + Todoist task management | `TODOIST_API_TOKEN`, Google OAuth |
| 🖥️ **Sys Ops** | System stats (CPU / RAM / Disk), shell command execution | `OPENROUTER_API_KEY` |
| ⚽ **Football Analyst** | Match results, standings, tactics, transfer news | `SERPER_API_KEY` |

### 🔑 API Keys Quick Reference

| Key | Where to Get It | Required For |
|-----|-----------------|--------------|
| `OPENROUTER_API_KEY` | [openrouter.ai/keys](https://openrouter.ai/keys) | **All agents** (LLM inference) |
| `TELEGRAM_BOT_TOKEN` | [@BotFather](https://t.me/BotFather) on Telegram | Telegram interface |
| `TELEGRAM_CHAT_ID` | [@userinfobot](https://t.me/userinfobot) on Telegram | Telegram interface |
| `SERPER_API_KEY` | [serper.dev](https://serper.dev) — 2,500 free queries/month | Search Agent, Football Analyst |
| `OPENWEATHERMAP_API_KEY` | [openweathermap.org/api](https://home.openweathermap.org/api_keys) — free tier | Search Agent (weather) |
| `TODOIST_API_TOKEN` | Todoist → Settings → Integrations → [Developer](https://app.todoist.com/app/settings/integrations/developer) | Daily Planner (tasks) |
| `OBSIDIAN_API_KEY` | Obsidian → Settings → [Local REST API plugin](https://github.com/coddingtonbear/obsidian-local-rest-api) | Obsidian RAG skill |
| Google OAuth credentials | [Google Cloud Console](https://console.cloud.google.com/apis/credentials) → OAuth 2.0 Desktop Client | Daily Planner (Calendar) |

> **Tip:** Only `OPENROUTER_API_KEY` is strictly required. Every other key is optional — agents with missing keys will still start and return a clear message explaining what needs to be configured.

---

## 📂 Project Structure


* `/backend`: FastAPI server, agents, tools registry, DB migrations, Telegram listeners.
* `/frontend`: React + Vite client web dashboard.
* `docker-compose.yml`: Multi-container configuration (Backend, Dashboard, Qdrant).
* `ROADMAP.md`: Detailed developmental roadmap, specifications, and business plan.

---

## 🛡️ License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
