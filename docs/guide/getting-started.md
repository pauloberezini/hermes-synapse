# 🚀 Getting Started with Hermes Synapse

Welcome to **Hermes Synapse** — an open-source, self-hosted **Multi-Agent Mesh & Governance Control Plane** inspired by Paperclip and built for scale.

---

## 🛠️ Quickstart Installation

### 1. Clone the Repository
```bash
git clone https://github.com/pauloberezini/hermes-synapse.git
cd hermes-synapse
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and set your API keys:
```bash
cp .env.example .env
```
Edit `.env` to include your OpenRouter or Gemini API keys:
```env
OPENROUTER_API_KEY=your_key_here
LLM_MODEL=ollama/llama3
```

When a request needs a competence nobody on the staff has, the core can hire a specialist under the orchestrator that owns the chat. `AUTO_HIRE=ask` (the default) creates the agent and waits for confirmation. `on` hires and runs it in the same turn. `off` reports the gap and creates nothing. Hired agents never receive skills the parent does not already have.

#### 🔍 Web Search Backend (SearXNG)
Hermes uses [SearXNG](https://github.com/searxng/searxng) as its open-source, self-hosted metasearch engine. No paid search API key is required:
```env
SEARXNG_URL=http://localhost:8080
```
Point `SEARXNG_URL` to your local or self-hosted SearXNG instance so agents can perform web searches without proprietary search APIs.


### 3. Launch via Docker Compose (Recommended)
```bash
docker-compose up --build -d
```
The application will be accessible at:
- **Web Console UI**: `http://localhost:5173`
- **FastAPI REST Backend**: `http://localhost:8000`

---

## 💻 Local Development Setup

### Backend (Python 3.11+)
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m uvicorn backend.main:app --reload --port 8000
```

### Frontend (React + Vite + TypeScript)
```bash
cd frontend
npm install
npm run dev
```

---

## 🎥 Video Setup Guide

Watch our step-by-step installation and initial configuration tutorial:

<YouTube id="3GFh-1Gglno" title="Hermes Synapse Installation Guide" />
