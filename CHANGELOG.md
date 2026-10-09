# 📰 Changelog & Latest Release News

All notable changes to **Hermes (Jarvis)** will be documented in this file.

---

## 🚀 [v1.4.1] - 2026-10-09

### 🛡️ Resilience
- **Non-blocking tool execution:** synchronous tools run in a worker thread (`asyncio.to_thread`), so long tools no longer starve the event loop or the health endpoints.
- **Telegram polling:** exponential backoff (15s → 300s) on polling conflicts instead of a fixed cooldown.
- **Idempotent client shutdown:** repeated or concurrent `close()` calls no longer raise "cannot reuse already awaited coroutine".

### 🧹 Hygiene & Docs
- Search docs and `.env.example` describe self-hosted SearXNG (`SEARXNG_URL`).
- Removed stray root artifacts; added `test_public_hygiene.py` to keep the public surface clean.
- `export_oss.sh`: fixed `set -e` abort when the leak gate and coupling check find nothing.

### 🧪 Tests
- New core tests: DAG cycle detection, governance wiring, OpenRouter/Ollama model selection.

---

## 🚀 [v1.4.0] - 2026-09-26

### 🔌 Plugin Boundary (Open-Core Hygiene)
- **Zero core imports of private plugins:** `backend/market_data.py` resolves non-`http` providers through the `market_data_provider(name)` hook; `backend/bot.py` routes Telegram fast commands through `handle_fast_command`. Core never imports `backend.<plugin>` by name.
- **Private tests live with their plugin:** every test that imports or reproduces plugin behaviour moved out of `backend/tests/`, so `uv run pytest` in the OSS tree collects only core tests. Core `conftest.py` no longer references plugin modules.
- **Publish script (`scripts/export_oss.sh`):** syncs the git-tracked core into a clone of the public repo, strips private env keys, aborts on any leaked private import/key/broker name, reports remaining tool-name coupling, and optionally pushes a release tag (`TAG=vX.Y.Z scripts/export_oss.sh --push`).
- **Docs:** README/ROADMAP describe the plugin contract instead of a bundled trading engine; `.env.example` lists only core keys.

### 🧠 Memory & Learning
- Closed-trade outcomes are recorded with realised PnL/exit price and a deterministic post-mortem line (entry thesis + result) instead of zeros, so daily-loss limits and vector-memory paradigms reflect real results.

### 🛠️ Stability
- Scheduler, orchestrator planner JSON validation, session titles, MCP client resilience, WebSocket manager and Obsidian tab fixes accumulated from production log reviews (see commit history).

---

## 🚀 [v1.3.0] - 2026-08-03

### 🐘 Infrastructure & Storage (PostgreSQL 16 Transition)
- **PostgreSQL Database Backend (`jarvis-db`):** Upgraded persistence layer to PostgreSQL 16 Alpine container with healthchecks and automatic schema management (`PostgresBackend` in `backend/database.py`).
- **SQLite Auto-Migration:** Implemented `_auto_migrate_sqlite_to_postgres()` to seamlessly migrate legacy SQLite data (`hermes.db`), sanitize text encoding (strip `\x00` NUL bytes), typecast numeric fields, and sync PostgreSQL sequence counters.

### ⏰ Scheduler & Real-Time Synchronization
- **Real-time Schedule Editing:** Editing scheduled task titles now immediately updates `session_metadata.title` in PostgreSQL and updates the active chat sidebar without requiring page reloads.
- **Robust Task Execution Fallbacks:** Enhanced `trigger_timer_now`, `pause_timer`, and `resume_timer` with multi-tier fallback lookup (Memory -> `session_metadata` DB -> `messages` history) so manual task execution (`RUN NOW`) works reliably even after container restarts or missing memory state.
- **Status Sync:** Synchronized task state (`paused`, `running`, `completed`) across backend scheduler and database records.

### 🌐 WebSockets & UI Enhancements
- **Safe JSON Serialization (`json_serial`):** Resolved WebSocket crashes caused by non-serializable `datetime` objects in `ConnectionManager.broadcast` and `/api/ws` init payload.
- **Human-Readable Task Titles:** Updated session label resolution in frontend (`App.tsx` and `ChatTab.tsx`) so scheduled tasks render human titles (e.g. `BCM Trading`) instead of raw technical UUIDs (`task_...`).
- **Empty Response Protection:** Added fallback handling in `save_message`, `_respond_as_subagent`, and `_trigger_agent_task` to ensure assistant message bubbles are never blank.

### 🛡️ Open-Source Architecture Alignment
- **Zero Vendor Lock-In:** Verified 100% compliance with Open-Source Architecture principles (`/opensource-checker`). All components run locally via Docker Compose with zero dependency on closed proprietary SaaS.
