# 📰 Changelog & Latest Release News

All notable changes to **Hermes (Jarvis)** will be documented in this file.

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
