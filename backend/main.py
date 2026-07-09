import logging
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.agent import agent_instance, DECISION_LOGS
from backend.bot import init_bot, shutdown_bot
from backend.websocket_manager import manager

class AuthVerifyRequest(BaseModel):
    code: str

class ConfigUpdate(BaseModel):
    system_prompt: str | None = None
    model: str | None = None
    fast_mode: bool | None = None
    max_history_len: int | None = None
    max_tokens: int | None = None
    tool_max_tokens: int | None = None
    temperature: float | None = None
    auto_rag: bool | None = None
    memory_enabled: bool | None = None
    memory_auto_save: bool | None = None
    memory_max_items: int | None = None

class PriceAlertRequest(BaseModel):
    symbol: str
    target_price: float
    condition: str

class SubagentUpdate(BaseModel):
    id: str
    name: str
    system_prompt: str
    model: str
    agent_type: str = "agent"
    parent_id: Optional[str] = None
    skills: str = ""
    x: int = 100
    y: int = 100
    temperature: float = 0.7
    role: str = "Specialist"
    status: str = "idle"
    is_enabled: bool = True
    model_provider: str = "openrouter"
    model_type: str = "external"
    model_params: dict = {}

class SubagentPosition(BaseModel):
    id: str
    x: int
    y: int

class SubagentPositionsUpdate(BaseModel):
    positions: List[SubagentPosition]

class ScheduledTaskCreate(BaseModel):
    type: str  # "one-shot" | "alarm" | "recurring"
    label: str
    agent_id: str
    prompt: str
    duration_seconds: Optional[int] = None
    time_str: Optional[str] = None
    interval_hours: Optional[float] = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("hermes.main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize DB, Qdrant/RAG and run the Telegram bot
    from backend.database import init_db
    init_db()
    
    from backend.rag import init_rag
    init_rag()
    
    # Start price alert monitor background task
    from backend.price_monitor import price_monitor
    price_monitor.start()
    
    bot_app = await init_bot()
    
    # Background Obsidian vault sync (non-blocking)
    import asyncio
    async def _obsidian_startup_sync():
        try:
            from backend.obsidian import is_reachable, sync_vault_to_rag
            if await is_reachable():
                logger.info("Obsidian is reachable — starting vault sync in background...")
                result = await sync_vault_to_rag()
                logger.info(f"Obsidian startup sync: {result.get('message', result)}")
            else:
                logger.info("Obsidian not reachable at startup (plugin not running or key not set — OK).")
        except Exception as e:
            logger.warning(f"Obsidian startup sync failed (non-fatal): {e}")
    asyncio.create_task(_obsidian_startup_sync())
    
    from backend.mcp_client import init_mcp_servers, shutdown_mcp_servers
    await init_mcp_servers()

    # Start BCM Session Scheduler in background (non-blocking)
    async def _bcm_session_scheduler_task():
        import sys
        import subprocess
        logger.info("BCM Session Scheduler background loop started.")
        while True:
            try:
                # Runs the session_scheduler checking rules every minute
                subprocess.run([sys.executable, "/app/backend/bcm/session_scheduler.py"], capture_output=True)
            except Exception as e:
                logger.error(f"Error in BCM session scheduler task: {e}")
            await asyncio.sleep(60)
    asyncio.create_task(_bcm_session_scheduler_task())

    yield
    # Shutdown: Stop Telegram bot
    await shutdown_bot()
    
    # Stop price alert monitor background task
    price_monitor.stop()

    # Shutdown MCP servers
    await shutdown_mcp_servers()


app = FastAPI(
    title="Hermes Jarvis Backend",
    description="Backend services for the Jarvis AI Personal Assistant",
    lifespan=lifespan
)

from backend.auth import validate_session
from fastapi.responses import JSONResponse

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Allow public auth routes and plots (images)
    if path in ("/api/auth/request-code", "/api/auth/verify-code") or path.startswith("/api/plots/"):
        return await call_next(request)
        
    # Apply auth only to API routes
    if not path.startswith("/api/"):
        return await call_next(request)
        
    # Check authorization header
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized: Missing or invalid token"})
        
    token = auth_header.split(" ")[1]
    if not validate_session(token):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized: Session expired or invalid"})
        
    return await call_next(request)

@app.post("/api/auth/request-code")
async def request_code():
    from backend.auth import generate_otp
    import backend.bot
    import os
    
    code = generate_otp()
    logger.info(f"Generated OTP Code: {code}")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        return {"status": "error", "message": "TELEGRAM_CHAT_ID is not configured on backend."}
        
    msg = (
        f"🏛️ **Hermes Authorization Request**\n\n"
        f"Sir, an entry request to the web dashboard was detected.\n"
        f"Your one-time access code is:\n\n"
        f"`{code}`\n\n"
        f"This code is valid for 5 minutes."
    )
    
    try:
        if backend.bot.telegram_app and backend.bot.telegram_app.bot:
            await backend.bot.telegram_app.bot.send_message(
                chat_id=int(chat_id),
                text=msg,
                parse_mode="Markdown"
            )
            return {"status": "success", "message": "Code sent to Telegram."}
        else:
            logger.error("Telegram bot is not initialized.")
            return {"status": "error", "message": "Telegram bot is not initialized."}
    except Exception as e:
        logger.error(f"Failed to send auth code to Telegram: {e}")
        return {"status": "error", "message": f"Failed to send code: {str(e)}"}

@app.post("/api/auth/verify-code")
async def verify_code(req: AuthVerifyRequest):
    from backend.auth import verify_otp, create_session
    if verify_otp(req.code):
        token = create_session()
        return {"status": "success", "token": token}
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Invalid or expired access code, Sir.")

from fastapi.staticfiles import StaticFiles
import os

plots_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "plots")
os.makedirs(plots_dir, exist_ok=True)
app.mount("/api/plots", StaticFiles(directory=plots_dir), name="plots")


# Enable CORS for frontend dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/status")
async def get_status():
    return {
        "status": "online",
        "agent": {
            "model": agent_instance.model,
            "max_history_len": agent_instance.max_history_len,
            "memory_enabled": agent_instance.memory_enabled,
        },
        "logs_count": len(DECISION_LOGS)
    }

@app.get("/api/config")
async def get_config():
    return agent_instance.get_runtime_config()

@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    if update.system_prompt is not None:
        agent_instance.update_system_prompt(update.system_prompt)
    if update.model is not None:
        agent_instance.model = update.model
    agent_instance.update_runtime_config(
        fast_mode=update.fast_mode,
        max_history_len=update.max_history_len,
        max_tokens=update.max_tokens,
        tool_max_tokens=update.tool_max_tokens,
        temperature=update.temperature,
        auto_rag=update.auto_rag,
        memory_enabled=update.memory_enabled,
        memory_auto_save=update.memory_auto_save,
        memory_max_items=update.memory_max_items,
    )
    config = agent_instance.get_runtime_config()
    try:
        from backend.database import save_app_settings
        save_app_settings(config)
    except Exception as e:
        logger.warning(f"Failed to persist runtime config: {e}")
        
    # Broadcast updated configuration to all websocket clients
    await manager.broadcast({
        "type": "config_update",
        **config
    })
    return {"status": "success", "config": config}

@app.get("/api/logs")
async def get_logs():
    from backend.database import get_decision_logs
    return get_decision_logs(100)

class DocumentCreate(BaseModel):
    title: str
    content: str

@app.get("/api/documents")
async def get_documents():
    from backend import rag
    return rag.list_documents()

@app.get("/api/documents/search")
async def search_documents(q: str = ""):
    from backend import rag
    if not q.strip():
        return []
    return rag.search_memory(q, limit=5, threshold=0.3)


@app.post("/api/documents")
async def create_document(doc: DocumentCreate):
    from backend import rag
    import uuid
    doc_id = str(uuid.uuid4())
    success = rag.index_document(doc_id, doc.title, doc.content)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Failed to index document in vector store.")
    return {"status": "success", "doc_id": doc_id, "title": doc.title}

@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str):
    from backend import rag
    success = rag.delete_document(doc_id)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail="Failed to delete document from vector store.")
    return {"status": "success", "doc_id": doc_id}

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    import shutil
    import os
    uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    file_path = os.path.join(uploads_dir, file.filename)
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        logger.info(f"File uploaded successfully: {file.filename}")
        
        # Broadcast upload event over WS so the UI is notified
        await manager.broadcast({
            "type": "chat_message",
            "role": "system",
            "content": f"⚙️ [Orchestrator] Dataset: Data file '{file.filename}' loaded."
        })
        
        return {"status": "success", "filename": file.filename, "filepath": file_path}
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@app.get("/api/voice/status")
async def voice_status_api():
    from backend.voice import get_voice_status
    return get_voice_status()


@app.post("/api/voice/transcribe")
async def transcribe_voice_api(file: UploadFile = File(...), language: Optional[str] = None):
    import asyncio
    import os
    import shutil
    import tempfile
    from backend.voice import VoiceTranscriptionError, transcribe_audio_file

    max_mb = float(os.getenv("VOICE_MAX_UPLOAD_MB", "25"))
    voice_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "voice")
    os.makedirs(voice_dir, exist_ok=True)

    original_name = file.filename or "voice.webm"
    _, ext = os.path.splitext(original_name)
    if not ext:
        ext = ".webm"

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(prefix="hermes_voice_", suffix=ext, dir=voice_dir, delete=False) as tmp:
            temp_path = tmp.name
            shutil.copyfileobj(file.file, tmp)

        size_bytes = os.path.getsize(temp_path)
        if size_bytes == 0:
            raise HTTPException(status_code=400, detail="Uploaded audio is empty.")
        if size_bytes > max_mb * 1024 * 1024:
            raise HTTPException(status_code=413, detail=f"Audio is larger than {max_mb:g} MB.")

        result = await asyncio.to_thread(transcribe_audio_file, temp_path, language)
        text = (result.get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="No speech detected in uploaded audio.")

        return {"status": "success", **result, "size_bytes": size_bytes}
    except HTTPException:
        raise
    except VoiceTranscriptionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Voice transcription failed")
        raise HTTPException(status_code=500, detail=f"Voice transcription failed: {exc}") from exc
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass

@app.get("/api/uploads")
async def list_uploads():
    import os
    uploads_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    try:
        files = os.listdir(uploads_dir)
        result = []
        for f in files:
            p = os.path.join(uploads_dir, f)
            # ponytail: skip hidden files like .gitkeep or .DS_Store
            if os.path.isfile(p) and not f.startswith('.'):
                result.append({
                    "name": f,
                    "size_bytes": os.path.getsize(p)
                })
        return result
    except Exception as e:
        logger.error(f"Error listing uploads: {e}")
        return []

@app.get("/api/timers")
async def get_timers_api():
    from backend.scheduler import get_all_timers
    return get_all_timers()

@app.get("/api/reminders")
async def get_reminders_api():
    from backend.scheduler import get_all_reminders
    return get_all_reminders()

@app.delete("/api/reminders/{reminder_id}")
async def cancel_reminder_api(reminder_id: str):
    from backend.scheduler import cancel_recurring_reminder
    ok = cancel_recurring_reminder(reminder_id)
    return {"status": "cancelled" if ok else "not_found", "reminder_id": reminder_id}

@app.post("/api/timers")
async def create_timer_api(task: ScheduledTaskCreate):
    from backend.scheduler import add_timer, add_alarm, add_recurring_reminder
    chat_id = "dashboard"
    try:
        if task.type == "one-shot":
            if task.duration_seconds is None:
                raise ValueError("duration_seconds is required for one-shot timer")
            timer_id = add_timer(task.label, task.duration_seconds, chat_id, task.agent_id, task.prompt)
            return {"status": "success", "id": timer_id}
        elif task.type == "alarm":
            if not task.time_str:
                raise ValueError("time_str is required for alarm timer")
            alarm_id = add_alarm(task.time_str, task.label, chat_id, task.agent_id, task.prompt)
            return {"status": "success", "id": alarm_id}
        elif task.type == "recurring":
            if task.interval_hours is None:
                raise ValueError("interval_hours is required for recurring timer")
            reminder_id = add_recurring_reminder(task.label, task.interval_hours, chat_id, task.agent_id, task.prompt)
            return {"status": "success", "id": reminder_id}
        else:
            return JSONResponse(status_code=400, content={"status": "failed", "error": f"Invalid type: {task.type}"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "failed", "error": str(e)})

@app.delete("/api/timers/{timer_id}")
async def cancel_timer_api(timer_id: str):
    from backend.scheduler import cancel_timer_or_alarm, cancel_recurring_reminder
    ok = cancel_timer_or_alarm(timer_id)
    if not ok:
        ok = cancel_recurring_reminder(timer_id)
    return {"status": "cancelled" if ok else "not_found", "timer_id": timer_id}

@app.get("/api/subagents")
async def get_subagents_api():
    from backend.database import get_all_subagents
    return get_all_subagents()

@app.get("/api/agents")
async def get_agents_api():
    from backend.database import get_all_subagents
    return get_all_subagents()

@app.post("/api/subagents")
async def save_subagent_api(subagent: SubagentUpdate):
    from backend.database import save_subagent
    # Basic slug validation for ID
    import re
    clean_id = re.sub(r'[^a-zA-Z0-9_-]', '', subagent.id).lower()
    save_subagent(
        clean_id,
        subagent.name,
        subagent.system_prompt,
        subagent.model,
        subagent.agent_type,
        subagent.parent_id,
        subagent.skills,
        subagent.x,
        subagent.y,
        subagent.temperature,
        subagent.role,
        subagent.status,
        subagent.is_enabled,
        subagent.model_provider,
        subagent.model_type,
        subagent.model_params,
    )
    return {"status": "success", "id": clean_id}

@app.post("/api/agents")
async def save_agent_api(subagent: SubagentUpdate):
    return await save_subagent_api(subagent)

@app.get("/api/agents/{agent_id}/events")
async def get_agent_events_api(agent_id: str, limit: int = 50):
    from backend.database import get_agent_events
    return get_agent_events(agent_id, limit=limit)

@app.get("/api/office/state")
async def get_office_state_api():
    from backend.database import get_agent_office_state
    return get_agent_office_state()

@app.post("/api/subagents/positions")
async def update_subagent_positions_api(update: SubagentPositionsUpdate):
    from backend.database import DB_PATH
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        for pos in update.positions:
            cursor.execute("UPDATE subagents SET x = ?, y = ? WHERE id = ?", (pos.x, pos.y, pos.id))
        conn.commit()
        conn.close()
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error updating positions: {e}")
        return {"status": "error", "message": str(e)}

@app.delete("/api/subagents/{subagent_id}")
async def delete_subagent_api(subagent_id: str):
    from backend.database import delete_subagent
    ok = delete_subagent(subagent_id)
    return {"status": "success" if ok else "failed"}

@app.get("/api/skills")
async def get_skills_api():
    """Returns all available built-in skill names and which tools each unlocks."""
    skill_to_tools = {
        "web_search":       ["web_search", "get_current_time_israel", "get_weather", "get_rss_digest"],
        "market_monitor":   ["get_market_prices", "add_price_alert"],
        "obsidian_rag":     ["search_obsidian", "read_obsidian_note", "create_obsidian_note", "sync_obsidian_vault"],
        "todoist_sync":     ["get_todoist_tasks", "add_todoist_task", "delete_todoist_task"],
        "google_calendar":  ["get_calendar_events", "add_calendar_event"],
        "timers_alarms":    ["set_timer", "set_alarm", "cancel_timer_or_alarm"],
        "shell_execution":  ["get_system_stats", "execute_command"],
        "python_sandbox":   ["execute_command"],
        "bcm":              ["bcm tools (crypto trading)"],
        "mcp_all":          ["all connected MCP server tools"],
    }
    # Append any live MCP servers as selectable skills
    from backend.mcp_client import mcp_clients
    for name in mcp_clients:
        if name not in skill_to_tools:
            skill_to_tools[name] = [f"MCP: {name}"]
    return skill_to_tools

_models_cache = {"data": None, "timestamp": 0}

@app.get("/api/models")
async def get_models_api():
    """Returns all available models from OpenRouter (or user provider) using user keys."""
    import time, os, httpx
    now = time.time()
    if _models_cache["data"] and (now - _models_cache["timestamp"] < 3600):
        return _models_cache["data"]

    api_base = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
    api_key = os.getenv("OPENROUTER_API_KEY", "")

    url = f"{api_base}/models"
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "data" in data:
                    models = data["data"]
                    result = []
                    for m in models:
                        m_id = m.get("id")
                        m_name = m.get("name") or m_id
                        result.append({"id": m_id, "name": m_name})
                    
                    rec_models = [
                        "google/gemini-2.5-flash",
                        "google/gemini-2.5-pro",
                        "anthropic/claude-sonnet-4-5",
                        "anthropic/claude-opus-4",
                        "openai/gpt-4o",
                        "openai/gpt-4o-mini",
                        "deepseek/deepseek-r1",
                        "deepseek/deepseek-v3-0324",
                        "meta-llama/llama-3.3-70b-instruct"
                    ]
                    
                    recommended = []
                    others = []
                    
                    for item in result:
                        if item["id"] in rec_models:
                            recommended.append(item)
                        else:
                            others.append(item)
                            
                    recommended.sort(key=lambda x: rec_models.index(x["id"]))
                    others.sort(key=lambda x: x["id"].lower())
                    
                    final_result = recommended + others
                    _models_cache["data"] = final_result
                    _models_cache["timestamp"] = now
                    return final_result
    except Exception as e:
        logger.error(f"Error fetching models: {e}")

    # Fallback list if request fails
    return [
        {"id": "google/gemini-2.5-flash", "name": "Google: Gemini 2.5 Flash (default)"},
        {"id": "google/gemini-2.5-pro", "name": "Google: Gemini 2.5 Pro"},
        {"id": "anthropic/claude-sonnet-4-5", "name": "Anthropic: Claude Sonnet 4.5"},
        {"id": "anthropic/claude-opus-4", "name": "Anthropic: Claude Opus 4"},
        {"id": "openai/gpt-4o", "name": "OpenAI: GPT-4o"},
        {"id": "openai/gpt-4o-mini", "name": "OpenAI: GPT-4o-Mini"},
        {"id": "deepseek/deepseek-r1", "name": "DeepSeek: R1"},
        {"id": "deepseek/deepseek-v3-0324", "name": "DeepSeek: V3"},
        {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Meta Llama 3.3 70B"},
    ]

# ─── MCP CONFIG API ───────────────────────────────────────────────────────────

class MCPServerConfig(BaseModel):
    name: str
    command: str
    args: list = []
    env: dict = {}

@app.get("/api/mcp/servers")
async def get_mcp_servers():
    """Returns current MCP server configs and live connection status."""
    import json, os
    from backend.mcp_client import mcp_clients
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mcp_config.json")
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
    servers = config.get("mcpServers", {})
    result = []
    for name, cfg in servers.items():
        result.append({
            "name": name,
            "command": cfg.get("command", ""),
            "args": cfg.get("args", []),
            "env": {k: v for k, v in cfg.get("env", {}).items() if "key" not in k.lower() and "secret" not in k.lower() and "token" not in k.lower()},
            "connected": name in mcp_clients,
            "tools_count": len(mcp_clients[name].tools) if name in mcp_clients else 0,
        })
    return result

@app.post("/api/mcp/servers")
async def add_mcp_server(server: MCPServerConfig):
    """Adds or updates an MCP server config and reconnects."""
    import json, os
    from backend.mcp_client import mcp_clients, mcp_tool_to_server, MCPServerClient
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mcp_config.json")
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    config = {}
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
    config.setdefault("mcpServers", {})
    config["mcpServers"][server.name] = {
        "command": server.command,
        "args": server.args,
        "env": server.env,
    }
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)
    # Connect the new server live
    try:
        if server.name in mcp_clients:
            await mcp_clients[server.name].shutdown()
        client = MCPServerClient(server.name, config["mcpServers"][server.name])
        await client.start()
        mcp_clients[server.name] = client
        from backend.tools import TOOLS_SCHEMA
        for tool in client.tools:
            tool_name = tool["name"]
            mcp_tool_to_server[tool_name] = server.name
            if not any(t.get("function", {}).get("name") == tool_name for t in TOOLS_SCHEMA):
                TOOLS_SCHEMA.append({"type": "function", "function": {"name": tool_name, "description": tool.get("description", ""), "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})}})
        return {"status": "success", "name": server.name, "tools": len(client.tools)}
    except Exception as e:
        logger.error(f"MCP server connect error: {e}")
        return {"status": "config_saved", "warning": str(e)}

@app.delete("/api/mcp/servers/{name}")
async def delete_mcp_server(name: str):
    """Removes an MCP server from config and disconnects it."""
    import json, os
    from backend.mcp_client import mcp_clients, mcp_tool_to_server
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "mcp_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r") as f:
            config = json.load(f)
        config.get("mcpServers", {}).pop(name, None)
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)
    if name in mcp_clients:
        await mcp_clients[name].shutdown()
        del mcp_clients[name]
        # Remove its tools from registry
        dead = [t for t, s in mcp_tool_to_server.items() if s == name]
        for t in dead:
            mcp_tool_to_server.pop(t, None)
    return {"status": "success", "name": name}

@app.get("/api/system/stats")
async def get_system_stats_api():
    from backend.tools import get_system_stats
    import json
    return json.loads(get_system_stats())

@app.get("/api/market/prices")
async def get_market_prices_api(symbols: str):
    from backend.price_monitor import price_monitor
    parts = [s.strip() for s in symbols.split(",") if s.strip()]
    results = {}
    for s in parts:
        p = await price_monitor.get_market_price(s)
        results[s] = p if p is not None else "no data"
    return results

@app.get("/api/market/alerts")
async def get_market_alerts():
    from backend.price_monitor import price_monitor
    return price_monitor.get_alerts()

@app.post("/api/market/alerts")
async def create_market_alert(req: PriceAlertRequest):
    from backend.price_monitor import price_monitor
    alert = price_monitor.add_alert(req.symbol, req.target_price, req.condition, "dashboard")
    return {"status": "success", "alert": alert}

@app.delete("/api/market/alerts/{alert_id}")
async def cancel_market_alert(alert_id: str):
    from backend.price_monitor import price_monitor
    ok = price_monitor.cancel_alert(alert_id)
    return {"status": "cancelled" if ok else "not_found"}

@app.delete("/api/activity/logs")
async def clear_activity_logs_api():
    from backend.database import clear_activity_logs
    from backend.activity_logger import ACTIVITY_LOGS
    clear_activity_logs()
    ACTIVITY_LOGS.clear()
    return {"status": "success"}

@app.get("/api/history/sessions")
async def get_history_sessions():
    from backend.database import DB_PATH
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM subagents")
        subagent_ids = {r[0] for r in cursor.fetchall()}
        
        cursor.execute("SELECT session_id, MAX(timestamp) as last_time FROM messages GROUP BY session_id ORDER BY last_time DESC")
        sessions = [r[0] for r in cursor.fetchall()]
        conn.close()
        
        # Filter out subagents, and keep only "dashboard" and custom sessions
        user_sessions = [s for s in sessions if s not in subagent_ids and s != "dashboard" and not s.startswith("archive_")]
        return ["dashboard"] + user_sessions
    except Exception as e:
        return ["dashboard"]

@app.get("/api/history/{chat_id}")
async def get_history_api(chat_id: str, limit: int = 40):
    from backend.database import get_chat_history
    return get_chat_history(chat_id, limit=limit)

@app.delete("/api/history/{chat_id}")
async def delete_history_api(chat_id: str):
    from backend.database import clear_chat_history
    clear_chat_history(chat_id)
    # Also clear from agent's in-memory last costs or messages if needed
    if chat_id in agent_instance.last_costs:
        agent_instance.last_costs[chat_id] = 0.0
    return {"status": "success"}

@app.post("/api/history/{session_id}/archive")
async def archive_history_session(session_id: str):
    """Archives a session by renaming its session_id in the DB."""
    from backend.database import DB_PATH
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE messages SET session_id = ? WHERE session_id = ?", (f"archive_{session_id}", session_id))
        conn.commit()
        conn.close()
        return {"status": "success", "message": f"Session {session_id} archived"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/history/{session_id}/fork")
async def fork_history_session(session_id: str):
    """Forks a session by duplicating its messages to a new session_id."""
    from backend.database import DB_PATH
    import sqlite3
    import time
    new_session_id = f"{session_id}_fork_{int(time.time())}"
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO messages (session_id, role, content, cost_usd) 
            SELECT ?, role, content, cost_usd FROM messages WHERE session_id = ? ORDER BY id ASC
        """, (new_session_id, session_id))
        conn.commit()
        conn.close()
        return {"status": "success", "new_session_id": new_session_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}



# ─── Obsidian API Endpoints ─────────────────────────────────────────────────

class ObsidianNoteCreate(BaseModel):
    title: str
    content: str
    folder: str = "Jarvis"

@app.get("/api/obsidian/status")
async def obsidian_status():
    """Check if the Obsidian Local REST API plugin is reachable."""
    from backend.obsidian import is_reachable, _get_api_key
    reachable = await is_reachable()
    return {
        "reachable": reachable,
        "api_key_configured": bool(_get_api_key()),
        "message": "✅ Obsidian connected" if reachable else "❌ Obsidian is unavailable. Start Obsidian and enable the Local REST API plugin."
    }

@app.get("/api/obsidian/notes")
async def obsidian_list_notes(folder: str = ""):
    """List all markdown notes in the vault (or a specific folder)."""
    from backend.obsidian import list_notes
    from backend.rag import list_documents
    notes = await list_notes(folder)
    indexed = {d["note_path"] for d in list_documents(source_filter="obsidian") if d.get("note_path")}
    return {
        "notes": notes,
        "total": len(notes),
        "indexed_count": len(indexed),
        "indexed_paths": list(indexed)
    }

@app.post("/api/obsidian/sync")
async def obsidian_sync():
    """Trigger full Obsidian vault → Qdrant RAG sync."""
    from backend.obsidian import sync_vault_to_rag
    result = await sync_vault_to_rag()
    return result

@app.get("/api/obsidian/search")
async def obsidian_search(q: str = ""):
    """Semantic search across indexed Obsidian notes."""
    if not q.strip():
        return []
    from backend.rag import search_memory
    return search_memory(q, limit=8, threshold=0.35, source_filter="obsidian")

@app.post("/api/obsidian/notes")
async def obsidian_create_note(note: ObsidianNoteCreate):
    """Create a new note in the Obsidian vault."""
    from backend.tools import create_obsidian_note
    result_str = create_obsidian_note(
        title=note.title,
        content=note.content,
        folder=note.folder
    )
    import json
    return json.loads(result_str)

@app.get("/api/obsidian/note")
async def obsidian_read_note(path: str):
    """Read the raw markdown content of a note by its vault-relative path."""
    from backend.obsidian import read_note
    content = await read_note(path)
    if content is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Note not found: {path}")
    return {"path": path, "content": content}

@app.delete("/api/obsidian/note")
async def obsidian_delete_note(path: str):
    """Delete a note in the Obsidian vault by path and remove from Qdrant RAG."""
    from backend.obsidian import delete_note
    from backend.rag import delete_document
    import hashlib
    
    ok = await delete_note(path)
    if not ok:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Failed to delete note: {path}")
        
    # Also delete from Qdrant RAG
    doc_id = "obsidian_" + hashlib.sha1(path.encode()).hexdigest()
    delete_document(doc_id)
    
    return {"status": "success", "message": f"Note {path} deleted successfully."}

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket):
    token = websocket.query_params.get("token")
    from backend.auth import validate_session
    if not token or not validate_session(token):
        await websocket.accept()
        await websocket.close(code=1008)
        return

    await manager.connect(websocket)
    try:
        # Send initial setup on connection
        from backend.database import get_chat_history
        from backend.activity_logger import ACTIVITY_LOGS
        history = get_chat_history("dashboard")
        await websocket.send_json({
            "type": "init",
            "config": {
                "system_prompt": agent_instance.system_prompt,
                "model": agent_instance.model
            },
            "logs": DECISION_LOGS[:20],
            "history": history,
            "activity_logs": ACTIVITY_LOGS
        })
        
        while True:
            # Maintain connection alive, process incoming messages if any
            data = await websocket.receive_text()
            try:
                import json
                msg = json.loads(data)
                if msg.get("type") == "chat_message":
                    user_text = msg.get("content")
                    chat_id = msg.get("chat_id", "dashboard")
                    # Broadcast user message to all dashboard connections
                    await manager.broadcast({
                        "type": "chat_message",
                        "role": "user",
                        "content": user_text,
                        "chat_id": chat_id
                    })
                    # Call agent
                    response_text = await agent_instance.respond(user_text, session_id=chat_id)
                    cost_usd = agent_instance.last_costs.get(chat_id, 0.0)
                    suppress_tts = agent_instance.check_and_clear_suppress_tts(chat_id)
                    
                    saved_ids = agent_instance.last_saved_ids.get(chat_id, {})
                    user_msg_id = saved_ids.get("user")
                    assistant_msg_id = saved_ids.get("assistant")
                    
                    # Broadcast agent response
                    await manager.broadcast({
                        "type": "chat_message",
                        "role": "assistant",
                        "content": response_text,
                        "chat_id": chat_id,
                        "cost_usd": cost_usd,
                        "suppress_tts": suppress_tts,
                        "id": assistant_msg_id
                    })
                    
                    # Broadcast user message ID update
                    if user_msg_id:
                        await manager.broadcast({
                            "type": "user_message_id_update",
                            "chat_id": chat_id,
                            "content": user_text,
                            "id": user_msg_id
                        })
                    # Broadcast updated logs
                    await manager.broadcast({
                        "type": "logs_update",
                        "logs": DECISION_LOGS[:20]
                    })
            except Exception as e:
                logger.error(f"Error processing websocket frame: {e}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.exception("WebSocket connection error")
        manager.disconnect(websocket)
