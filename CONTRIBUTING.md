# 🤝 Contributing to Hermes

Thank you for your interest in contributing! Hermes is built on **OSS-first principles** — self-hosted, zero vendor lock-in, and local-model friendly.

---

## 🚀 Getting Started in 5 Minutes

### Prerequisites

- Docker + Docker Compose (required)
- Python 3.11+ (for backend dev without Docker)
- Node.js 18+ (for frontend dev without Docker)

### 1. Fork & Clone

```bash
git clone https://github.com/YOUR_USERNAME/hermes-synapse
cd hermes-synapse
```

### 2. Configure Environment

```bash
cp .env.example .env
# Minimum required: set OPENROUTER_API_KEY (or use Ollama for fully local dev)
```

### 3. Launch in Development Mode (Hot-Reload)

```bash
docker compose -f docker-compose.dev.yml up
```

This starts:
- **Backend** on `http://localhost:8000` with file-watching (uvicorn `--reload`)
- **Frontend** on `http://localhost:5173` with Vite HMR
- **Qdrant** on `http://localhost:6333`

### 4. Verify Everything Works

```bash
curl http://localhost:8000/health     # → {"status": "ok"}
open http://localhost:5173             # → Hermes Dashboard
```

---

## 🧩 Adding a New Skill

Skills are the primary extension point. A skill is a set of Python functions exposed as LLM tools.

### Skill structure in `backend/tools.py`

```python
# 1. Define the implementation function
def my_new_tool(param: str) -> str:
    """Tool implementation logic here."""
    return f"Result for {param}"

# 2. Register it in the SKILLS_REGISTRY dict (in tools.py)
SKILLS_REGISTRY = {
    ...
    "my_skill": {
        "display_name": "My Skill",
        "tools": ["my_new_tool"],
        "description": "Does something useful",
    },
}

# 3. Add the tool schema to TOOL_SCHEMAS list (in tools.py)
{
    "name": "my_new_tool",
    "description": "Does something useful",
    "parameters": {
        "type": "object",
        "properties": {
            "param": {"type": "string", "description": "Input parameter"}
        },
        "required": ["param"]
    }
}
```

### Skill Guidelines (OSS Checklist ✅)

- ✅ **No hardcoded API keys** — read from `os.getenv()`
- ✅ **Graceful degradation** — return a helpful message if key is missing, not an exception
- ✅ **Local-first** — prefer open APIs / self-hosted alternatives
- ✅ **No proprietary lock-in** — if using a commercial API, check if there's an OSS equivalent

---

## 🏗️ Project Layout

```
backend/
├── main.py           # FastAPI routes (REST + WebSocket)
├── agent.py          # Core LLM loop (tool calling, streaming)
├── orchestrator.py   # DAG planner (multi-agent coordination)
├── database.py       # DB abstraction (SQLite + PostgreSQL)
├── rag.py            # Vector memory (Qdrant + fastembed)
├── tools.py          # All skill implementations + schemas
├── subagents.py      # Specialized agent runners
└── scheduler.py      # Timer and alarm management

frontend/
├── src/
│   ├── components/   # React components
│   ├── tabs/         # Dashboard tab panels
│   └── App.jsx       # Main app + routing
```

---

## 🐛 Reporting Bugs

Use the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.yml).

**Before opening a bug:**
1. Check [existing issues](https://github.com/pauloberezini/hermes-synapse/issues)
2. Try on the latest `main` branch
3. Include your Docker version and OS in the report

---

## 💡 Proposing Features

Use the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.yml).

**Feature acceptance criteria:**
- Does not introduce proprietary vendor dependencies without OSS alternative
- Can be run locally without cloud accounts
- Follows existing skill/module patterns

---

## 🏷️ Good First Issues

Look for issues tagged [`good first issue`](https://github.com/pauloberezini/hermes-synapse/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22).

Ideas for new contributors:
- Add a new RSS feed source in `subagents.py`
- Write a unit test for an existing skill
- Improve a system prompt for one of the default agents
- Translate an agent prompt to a new language

---

## ✅ Pull Request Checklist

Before opening a PR, verify:

- [ ] Code runs with `docker compose up -d --build`
- [ ] No new hardcoded credentials or API keys
- [ ] New skills gracefully degrade when keys are missing
- [ ] No breaking changes to existing API routes without discussion
- [ ] PR description explains *what* changed and *why*

---

## 🛡️ OSS Architecture Principles

Hermes enforces these principles to stay community-friendly:

1. **No vendor lock-in** — any OpenAI-compatible LLM works (Ollama, vLLM, OpenRouter)
2. **Zero-friction local dev** — `docker compose up` with no cloud accounts required
3. **Modular skills** — add/remove capabilities without touching core orchestration

PRs that violate these principles will be kindly redirected to an OSS-compatible approach.

---

## 📜 License

By contributing, you agree your code will be licensed under [MIT](LICENSE).
