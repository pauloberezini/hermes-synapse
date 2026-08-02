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
LLM_MODEL=google/gemini-2.5-flash
```

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
