import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request, Response, Query
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

class SubagentPosition(BaseModel):
    id: str
    x: int
    y: int

class SubagentPositionsUpdate(BaseModel):
    positions: List[SubagentPosition]

class ScheduledTaskCreate(BaseModel):
    type: str  # "one-shot" | "alarm" | "recurring" | "cron"
    label: str
    agent_id: str
    prompt: str
    duration_seconds: Optional[int] = None
    time_str: Optional[str] = None
    interval_hours: Optional[float] = None
    cron_expr: Optional[str] = None

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("hermes.main")

# Silence noisy third-party HTTP pollers (Telegram bot getUpdates, etc.)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("websockets").setLevel(logging.WARNING)
logging.getLogger("websockets.server").setLevel(logging.WARNING)
logging.getLogger("websockets.protocol").setLevel(logging.WARNING)
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

class EndpointLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        str_args = str(record.args) if record.args else ""
        full_text = f"{msg} {str_args}".lower()
        if "websocket" in full_text and ("accepted" in full_text or "closed" in full_text or "connected" in full_text):
            return False
        if "connection open" in full_text or "connection closed" in full_text:
            return False
        if "/api/" in full_text and ("status" in full_text or "timers" in full_text or "200" in full_text):
            return False
        return True

endpoint_filter = EndpointLogFilter()
for uvi_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    uvi_logger = logging.getLogger(uvi_name)
    uvi_logger.addFilter(endpoint_filter)

uvicorn_access = logging.getLogger("uvicorn.access")
uvicorn_access.setLevel(logging.WARNING)
uvicorn_access.disabled = True

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Ensure uvicorn access & websocket handshake logging remains clean after server startup
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("websockets.server").setLevel(logging.WARNING)
    logging.getLogger("websockets.protocol").setLevel(logging.WARNING)
    for uvi_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(uvi_name).addFilter(endpoint_filter)
    
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

    # Start background APScheduler & self-improving skill distillation loop
    try:
        from backend.scheduler import scheduler, restore_state, start_skill_distillation_loop, start_rss_poller_loop, _load_private_plugins, start_watcher_loop
        restore_state()
        scheduler.start()
        start_skill_distillation_loop(interval_seconds=900)
        start_rss_poller_loop(interval_seconds=300)
        start_watcher_loop(interval_seconds=300)

        # Start BCM Session Scheduler in background (non-blocking, opt-in via ENABLE_BCM_AUTO_TRADER)
        if os.environ.get("ENABLE_BCM_AUTO_TRADER", "false").lower() == "true":
            loaded = _load_private_plugins(scheduler)
            if not loaded:
                logger.warning("ENABLE_BCM_AUTO_TRADER is true, but no private BCM plugin was found.")
        else:
            logger.info("BCM Session Scheduler is disabled (set ENABLE_BCM_AUTO_TRADER=true in .env to enable).")
    except Exception as e:
        logger.warning(f"Failed to start scheduler or skill distillation loop: {e}")

    # Start Mesh Router heartbeat loop for Stage 17 distributed capability
    import uuid
    import socket
    
    async def _mesh_heartbeat_task():
        from backend.mesh import get_mesh_router, MeshPeerManifest
        router = get_mesh_router()
        node_id = f"node-{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        endpoint_url = os.environ.get("HERMES_ENDPOINT_URL", f"http://{socket.gethostname()}:8000")
        manifest = MeshPeerManifest(
            node_id=node_id,
            endpoint_url=endpoint_url,
            display_name=f"Hermes Replica {socket.gethostname()}",
            capabilities=["agent_runner", "sandbox"],
            status="online",
            reporting_role="Worker"
        )
        logger.debug(f"Starting Mesh heartbeat for {node_id}")
        try:
            while True:
                try:
                    router.register_peer(manifest)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    logger.error(f"Error in mesh heartbeat task: {e}")
                await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.debug(f"Mesh heartbeat task cancelled for {node_id}")
            
    mesh_task = asyncio.create_task(_mesh_heartbeat_task())

    yield
    # Shutdown: Stop mesh heartbeat task
    if mesh_task and not mesh_task.done():
        mesh_task.cancel()

    # Shutdown: Stop APScheduler & background scheduler loops cleanly
    try:
        from backend.scheduler import shutdown_scheduler
        shutdown_scheduler(wait=False)
    except Exception as e:
        logger.warning(f"Failed to shutdown scheduler cleanly: {e}")

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
    # Allow public auth routes, status endpoint, and plots (images)
    if path in ("/api/auth/request-code", "/api/auth/verify-code", "/api/status") or path.startswith("/api/plots/"):
        return await call_next(request)
        
    # Apply auth only to API routes
    if not path.startswith("/api/"):
        return await call_next(request)
        
    # Public auth endpoints do not require Bearer header
    if path in ["/api/auth/request-code", "/api/auth/verify-code"]:
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

class ConfigUpdate(BaseModel):
    system_prompt: str | None = None
    model: str | None = None

class SettingsUpdate(BaseModel):
    language: str | None = None  # e.g. 'ru', 'en', 'he'


@app.get("/api/status")
async def get_status():
    return {
        "status": "online",
        "agent": {
            "model": agent_instance.model,
            "max_history_len": agent_instance.max_history_len,
        },
        "logs_count": len(DECISION_LOGS)
    }

@app.get("/api/config")
async def get_config():
    return {
        "system_prompt": agent_instance.system_prompt,
        "model": agent_instance.model
    }

@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    if update.system_prompt is not None:
        agent_instance.update_system_prompt(update.system_prompt)
    if update.model is not None:
        agent_instance.model = update.model
        
    # Broadcast updated configuration to all websocket clients
    await manager.broadcast({
        "type": "config_update",
        "system_prompt": agent_instance.system_prompt,
        "model": agent_instance.model
    })
    return {"status": "success", "config": {"system_prompt": agent_instance.system_prompt, "model": agent_instance.model}}

@app.get("/api/settings")
async def get_settings():
    from backend.database import get_setting
    return {"language": get_setting("language") or "en"}

@app.post("/api/settings")
async def update_settings(update: SettingsUpdate):
    from backend.database import set_setting, get_setting
    if update.language is not None:
        set_setting("language", update.language)
    await manager.broadcast({"type": "settings_update", "language": get_setting("language") or "en"})
    return {"status": "success", "language": get_setting("language") or "en"}

@app.get("/api/logs")
async def get_logs():
    from backend.database import get_decision_logs
    return get_decision_logs(100)

@app.get("/api/metrics")
async def get_metrics():
    from backend.database import db_get_aggregated_metrics
    return db_get_aggregated_metrics()

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
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

@app.post("/api/parse-pdf")
async def parse_pdf(file: UploadFile = File(...)):
    """
    Extract plain text from an uploaded PDF using pypdf (OSS, pure-Python).
    Returns { text, pages, truncated } — text is capped at 500 KB.
    """
    import io
    from fastapi import HTTPException
    MAX_TEXT_BYTES = 500 * 1024  # 500 KB extracted text limit for PDF

    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only .pdf files are accepted.")
    try:
        pdf_bytes = await file.read()
        try:
            from pypdf import PdfReader
        except ImportError:
            raise HTTPException(status_code=500, detail="pypdf is not installed in the backend. Add 'pypdf>=4.0.0' to dependencies.")

        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages_count = len(reader.pages)
        extracted_parts = []
        total_bytes = 0
        truncated = False

        for page_num, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text() or ""
            chunk = f"--- Page {page_num} ---\n{page_text}\n"
            chunk_bytes = len(chunk.encode("utf-8"))
            if total_bytes + chunk_bytes > MAX_TEXT_BYTES:
                # Include partial page up to limit
                remaining = MAX_TEXT_BYTES - total_bytes
                if remaining > 0:
                    extracted_parts.append(chunk.encode("utf-8")[:remaining].decode("utf-8", errors="ignore"))
                truncated = True
                break
            extracted_parts.append(chunk)
            total_bytes += chunk_bytes

        full_text = "".join(extracted_parts).strip()
        if not full_text:
            raise HTTPException(status_code=422, detail="Could not extract text from this PDF. It may be scanned/image-based.")

        logger.info(f"PDF parsed: '{file.filename}', {pages_count} pages, {total_bytes} bytes extracted, truncated={truncated}")
        return {
            "text": full_text,
            "pages": pages_count,
            "truncated": truncated,
            "extracted_bytes": total_bytes
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF parse error for '{file.filename}': {e}")
        raise HTTPException(status_code=500, detail=f"Failed to parse PDF: {str(e)}")

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
    from backend.scheduler import add_timer, add_alarm, add_recurring_reminder, add_cron_reminder
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
        elif task.type == "cron":
            if not task.cron_expr:
                raise ValueError("cron_expr is required for cron task")
            cron_id = add_cron_reminder(task.label, task.cron_expr, chat_id, task.agent_id, task.prompt)
            return {"status": "success", "id": cron_id}
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

@app.put("/api/timers/{timer_id}")
async def update_timer_api(timer_id: str, task: ScheduledTaskCreate):
    from backend.scheduler import update_timer
    try:
        ok = update_timer(
            item_id=timer_id,
            label=task.label,
            task_type=task.type,
            agent_id=task.agent_id,
            prompt=task.prompt,
            duration_seconds=task.duration_seconds,
            time_str=task.time_str,
            interval_hours=task.interval_hours,
            cron_expr=task.cron_expr,
        )
        if ok:
            return {"status": "success", "id": timer_id}
        else:
            return JSONResponse(status_code=404, content={"status": "failed", "error": f"Timer '{timer_id}' not found"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "failed", "error": str(e)})

@app.post("/api/timers/{timer_id}/run")
async def run_timer_now_api(timer_id: str):
    from backend.scheduler import trigger_timer_now
    try:
        ok = trigger_timer_now(timer_id)
        if ok:
            return {"status": "triggered", "id": timer_id}
        else:
            return JSONResponse(status_code=404, content={"status": "failed", "error": f"Timer '{timer_id}' not found"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "failed", "error": str(e)})

@app.post("/api/timers/{timer_id}/pause")
async def pause_timer_api(timer_id: str):
    from backend.scheduler import pause_timer
    try:
        ok = pause_timer(timer_id)
        if ok:
            return {"status": "paused", "id": timer_id}
        else:
            return JSONResponse(status_code=404, content={"status": "failed", "error": f"Timer '{timer_id}' not found"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "failed", "error": str(e)})

@app.post("/api/timers/{timer_id}/resume")
async def resume_timer_api(timer_id: str):
    from backend.scheduler import resume_timer
    try:
        ok = resume_timer(timer_id)
        if ok:
            return {"status": "resumed", "id": timer_id}
        else:
            return JSONResponse(status_code=404, content={"status": "failed", "error": f"Timer '{timer_id}' not found"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "failed", "error": str(e)})

@app.post("/api/timers/{timer_id}/restart")
async def restart_timer_api(timer_id: str):
    from backend.scheduler import restart_timer
    try:
        ok = restart_timer(timer_id)
        if ok:
            return {"status": "restarted", "id": timer_id}
        else:
            return JSONResponse(status_code=404, content={"status": "failed", "error": f"Timer '{timer_id}' not found"})
    except Exception as e:
        return JSONResponse(status_code=400, content={"status": "failed", "error": str(e)})

@app.get("/api/subagents")
async def get_subagents_api():
    from backend.database import get_all_subagents
    return get_all_subagents()

@app.get("/api/office/state")
async def get_office_state_api():
    from backend.database import get_agent_office_state
    return get_agent_office_state()

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
    )
    return {"status": "success", "id": clean_id}

@app.post("/api/subagents/positions")
async def update_subagent_positions_api(update: SubagentPositionsUpdate):
    from backend.database import _rowcount
    try:
        for pos in update.positions:
            _rowcount("UPDATE subagents SET x = ?, y = ? WHERE id = ?", (pos.x, pos.y, pos.id))
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error updating positions: {e}")
        return {"status": "error", "message": str(e)}

@app.delete("/api/subagents/{subagent_id}")
async def delete_subagent_api(subagent_id: str):
    from backend.database import delete_subagent
    ok = delete_subagent(subagent_id)
    return {"status": "success" if ok else "failed"}

# ── Autonomous RSS Nodes & Feeds API Endpoints ──────────────────────────────

class RSSNodeCreate(BaseModel):
    id: str
    name: str
    feed_urls: str = ""
    fetch_interval_minutes: int = 15
    output_limit: int = 10
    date_filter_days: int = 0
    keywords_filter: str = ""
    is_active: int = 1
    x: int = 300
    y: int = 200
    connected_agents: str = ""

class RSSNodeUpdate(BaseModel):
    name: Optional[str] = None
    feed_urls: Optional[str] = None
    fetch_interval_minutes: Optional[int] = None
    output_limit: Optional[int] = None
    date_filter_days: Optional[int] = None
    keywords_filter: Optional[str] = None
    is_active: Optional[int] = None
    x: Optional[int] = None
    y: Optional[int] = None
    connected_agents: Optional[str] = None

class RSSNodePositionItem(BaseModel):
    id: str
    x: int
    y: int

class RSSNodePositionsUpdate(BaseModel):
    positions: List[RSSNodePositionItem]

@app.get("/api/rss/nodes")
async def get_rss_nodes_api():
    from backend.database import db_get_all_rss_nodes
    return db_get_all_rss_nodes()

@app.post("/api/rss/nodes")
async def create_rss_node_api(payload: RSSNodeCreate):
    from backend.database import db_create_rss_node
    import re
    clean_id = re.sub(r'[^a-zA-Z0-9_-]', '', payload.id).lower()
    if not clean_id:
        return JSONResponse(status_code=400, content={"status": "error", "message": "Invalid RSS node ID"})
    res = db_create_rss_node(
        id=clean_id,
        name=payload.name,
        feed_urls=payload.feed_urls,
        fetch_interval_minutes=payload.fetch_interval_minutes,
        output_limit=payload.output_limit,
        date_filter_days=payload.date_filter_days,
        keywords_filter=payload.keywords_filter,
        is_active=payload.is_active,
        x=payload.x,
        y=payload.y,
        connected_agents=payload.connected_agents
    )
    return {"status": "success", "node": res}

@app.put("/api/rss/nodes/{node_id}")
async def update_rss_node_api(node_id: str, payload: RSSNodeUpdate):
    from backend.database import db_update_rss_node, db_get_rss_node
    ok = db_update_rss_node(
        node_id=node_id,
        name=payload.name,
        feed_urls=payload.feed_urls,
        fetch_interval_minutes=payload.fetch_interval_minutes,
        output_limit=payload.output_limit,
        date_filter_days=payload.date_filter_days,
        keywords_filter=payload.keywords_filter,
        is_active=payload.is_active,
        x=payload.x,
        y=payload.y,
        connected_agents=payload.connected_agents
    )
    if not ok:
        return JSONResponse(status_code=404, content={"status": "error", "message": f"RSS node {node_id} not found"})
    return {"status": "success", "node": db_get_rss_node(node_id)}

@app.post("/api/rss/nodes/positions")
async def update_rss_node_positions_api(payload: RSSNodePositionsUpdate):
    from backend.database import db_update_rss_node
    for pos in payload.positions:
        db_update_rss_node(pos.id, x=pos.x, y=pos.y)
    return {"status": "success"}

@app.delete("/api/rss/nodes/{node_id}")
async def delete_rss_node_api(node_id: str):
    from backend.database import db_delete_rss_node
    ok = db_delete_rss_node(node_id)
    return {"status": "success" if ok else "failed"}

@app.post("/api/rss/nodes/{node_id}/fetch")
async def fetch_rss_node_api(node_id: str):
    from backend.rss_service import fetch_and_save_node_rss
    res = fetch_and_save_node_rss(node_id)
    return res

@app.get("/api/rss/nodes/{node_id}/items")
async def get_rss_node_items_api(node_id: str, limit: int = 50, days: int = 0, keywords: str = ""):
    from backend.database import db_get_rss_items
    items = db_get_rss_items(node_id=node_id, limit=limit, date_filter_days=days, keywords_filter=keywords)
    return {"node_id": node_id, "count": len(items), "items": items}

@app.get("/api/rss/nodes/{node_id}/output")
async def get_rss_node_output_api(node_id: str, limit: Optional[int] = None):
    from backend.rss_service import get_rss_node_output
    return get_rss_node_output(node_id=node_id, override_limit=limit)

# ── Paperclip Governance & Presets API Endpoints ────────────────────────────────

class BudgetUpdateRequest(BaseModel):
    daily_budget_usd: Optional[float] = None
    monthly_budget_usd: Optional[float] = None

class ApprovalResolveRequest(BaseModel):
    decision: str  # "APPROVED" | "REJECTED"
    resolver_note: str = ""

@app.get("/api/governance/approvals")
async def get_approvals_api(pending_only: bool = False):
    from backend.governance import ApprovalQueue
    if pending_only:
        return ApprovalQueue.get_pending()
    return ApprovalQueue.get_all()

@app.get("/api/governance/approvals/count")
async def get_pending_approvals_count_api():
    from backend.governance import ApprovalQueue
    return {"count": ApprovalQueue.count_pending()}

@app.post("/api/governance/approvals/{request_id}/resolve")
async def resolve_approval_api(request_id: int, payload: ApprovalResolveRequest):
    from backend.governance import ApprovalQueue
    ok = ApprovalQueue.resolve(request_id, payload.decision, payload.resolver_note)
    if not ok:
        return JSONResponse(status_code=404, content={"status": "failed", "error": f"Request #{request_id} not found"})
    return {"status": "success", "id": request_id, "decision": payload.decision}

@app.get("/api/governance/budget/{session_id}")
async def get_budget_api(session_id: str):
    from backend.governance import BudgetGuard
    return BudgetGuard.get_spend_summary(session_id)

@app.post("/api/governance/budget/{session_id}")
async def update_budget_api(session_id: str, body: BudgetUpdateRequest):
    from backend.database import _rowcount
    _rowcount(
        "UPDATE session_metadata SET daily_budget_usd = ?, monthly_budget_usd = ? WHERE session_id = ?",
        (body.daily_budget_usd, body.monthly_budget_usd, session_id)
    )
    return {"status": "success", "session_id": session_id}

@app.get("/api/subagents/presets")
async def get_presets_api():
    from backend.presets import list_presets
    return list_presets()

@app.post("/api/subagents/presets/{preset_id}/load")
async def load_preset_api(preset_id: str):
    from backend.presets import load_preset
    ok = load_preset(preset_id)
    if not ok:
        return JSONResponse(status_code=404, content={"status": "failed", "error": f"Preset '{preset_id}' not found"})
    return {"status": "success", "preset_id": preset_id}

# ── Paperclip Task Engine REST API Endpoints (FEAT-5) ──────────────────────────

class TaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    status: str = "BACKLOG"
    assigned_agent_id: str = ""

class TaskCheckoutRequest(BaseModel):
    agent_id: str
    lock_duration_seconds: int = 300

class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    assigned_agent_id: Optional[str] = None
    checkpoint_data: Optional[str] = None

@app.get("/api/tasks")
async def get_tasks_api(status: Optional[str] = None, assigned_agent_id: Optional[str] = None):
    from backend.database import db_get_tasks
    return db_get_tasks(status=status, assigned_agent_id=assigned_agent_id)

@app.post("/api/tasks")
async def create_task_api(body: TaskCreateRequest):
    from backend.database import db_create_task
    task_id = db_create_task(
        title=body.title,
        description=body.description,
        status=body.status,
        assigned_agent_id=body.assigned_agent_id,
    )
    return {"status": "success", "id": task_id}

@app.post("/api/tasks/{task_id}/checkout")
async def checkout_task_api(task_id: int, body: TaskCheckoutRequest):
    from backend.database import db_checkout_task
    res = db_checkout_task(task_id, body.agent_id, body.lock_duration_seconds)
    if res.get("status") == "error":
        return JSONResponse(status_code=404, content=res)
    elif res.get("status") == "locked":
        return JSONResponse(status_code=409, content=res)
    return res

@app.post("/api/tasks/{task_id}/pulse")
async def pulse_task_api(task_id: int, max_steps: int = 1):
    from backend.orchestrator import run_orchestration_pulse
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    model = os.environ.get("LLM_MODEL", "ollama/llama3")
    res = await run_orchestration_pulse(task_id, api_key, model, max_steps_per_pulse=max_steps)
    if res.get("status") == "error":
        return JSONResponse(status_code=404, content=res)
    elif res.get("status") == "locked":
        return JSONResponse(status_code=409, content=res)
    return res

@app.put("/api/tasks/{task_id}")
async def update_task_api(task_id: int, body: TaskUpdateRequest):
    from backend.database import db_update_task
    ok = db_update_task(
        task_id,
        title=body.title,
        description=body.description,
        status=body.status,
        assigned_agent_id=body.assigned_agent_id,
        checkpoint_data=body.checkpoint_data,
    )
    if not ok:
        return JSONResponse(status_code=404, content={"status": "failed", "error": f"Task #{task_id} not found or no changes"})
    return {"status": "success", "id": task_id}

@app.delete("/api/tasks/{task_id}")
async def delete_task_api(task_id: int):
    from backend.database import db_delete_task
    ok = db_delete_task(task_id)
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
        "read_rss_node_feed": ["read_rss_node_feed"],
        "bcm":              ["bcm tools (crypto trading)"],
        "mcp_all":          ["all connected MCP server tools"],
    }
    # Append any live MCP servers as selectable skills
    from backend.mcp_client import mcp_clients
    for name in mcp_clients:
        if name not in skill_to_tools:
            skill_to_tools[name] = [f"MCP: {name}"]

    # Append automatically distilled skills
    from backend.database import db_get_distilled_skills
    distilled_list = db_get_distilled_skills(limit=100)
    for ds in distilled_list:
        name = ds.get("skill_name")
        if name and name not in skill_to_tools:
            skill_to_tools[name] = [f"Distilled: {ds.get('title', name)}"]

    return skill_to_tools


@app.get("/api/skills/distilled")
async def get_distilled_skills_api(limit: int = 50):
    """Returns all automatically distilled skills from the database."""
    from backend.database import db_get_distilled_skills
    return db_get_distilled_skills(limit=limit)


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 14: COMMUNITY SKILLS MARKETPLACE & PLUGIN REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/marketplace/skills")
async def get_marketplace_skills_api():
    """
    Returns all registered community skills authored using `hermes_sdk` and database persistence.
    Includes manifests, tools, required environment variables, and tags.
    """
    from hermes_sdk.skill import get_registry
    from backend.marketplace.lifecycle import LifecycleManager
    
    registry = get_registry()
    manifests = [manifest.to_dict() for manifest in registry.values()]
    db_skills = LifecycleManager.list_skills()
    
    # Merge DB skills if not in memory registry
    memory_names = {m["name"] for m in manifests}
    for s in db_skills:
        if s["name"] not in memory_names:
            manifests.append(s)

    return {
        "status": "success",
        "count": len(manifests),
        "skills": manifests
    }


class SkillRegistrationPayload(BaseModel):
    name: str
    display_name: str
    description: str
    tools: List[str] = []
    author: str = "community"
    price_type: str = "free"
    price_usd: float = 0.0


@app.post("/api/marketplace/register")
async def register_marketplace_skill_api(payload: SkillRegistrationPayload):
    """Dynamically registers a community skill into the Hermes Marketplace registry and DB."""
    from hermes_sdk.types import SkillManifest, ToolSchema
    from hermes_sdk.skill import get_registry
    from backend.marketplace.lifecycle import LifecycleManager, MarketplaceSkillManifest
    
    registry = get_registry()
    tools_schemas = [ToolSchema(name=t, description=f"Tool: {t}") for t in payload.tools]
    manifest = SkillManifest(
        name=payload.name,
        display_name=payload.display_name,
        description=payload.description,
        author=payload.author,
        tools=tools_schemas
    )
    registry[payload.name] = manifest

    # Persist in DB
    LifecycleManager.upsert_skill(MarketplaceSkillManifest(
        id=payload.name,
        name=payload.name,
        display_name=payload.display_name,
        description=payload.description,
        author=payload.author,
        tools=payload.tools,
        price_type=payload.price_type,
        price_usd=payload.price_usd
    ))

    return {
        "status": "success",
        "message": f"Skill '{payload.name}' registered in Hermes Marketplace.",
        "skill": manifest.to_dict()
    }


@app.post("/api/marketplace/skills/{skill_id}/install")
async def install_marketplace_skill_api(skill_id: str):
    """1-Click installation endpoint for a marketplace skill."""
    from backend.marketplace.lifecycle import LifecycleManager
    result = LifecycleManager.install_skill(skill_id)
    return {"status": "success", "message": f"Skill '{skill_id}' installed.", "skill": result}


@app.post("/api/marketplace/skills/{skill_id}/uninstall")
async def uninstall_marketplace_skill_api(skill_id: str):
    """Uninstalls a marketplace skill."""
    from backend.marketplace.lifecycle import LifecycleManager
    result = LifecycleManager.uninstall_skill(skill_id)
    return {"status": "success", "message": f"Skill '{skill_id}' uninstalled.", "skill": result}


@app.post("/api/marketplace/skills/{skill_id}/configure")
async def configure_marketplace_skill_api(skill_id: str, config: Dict[str, Any]):
    """Saves environment variable configuration for an installed skill."""
    from backend.marketplace.lifecycle import LifecycleManager
    result = LifecycleManager.save_skill_config(skill_id, config)
    return result


@app.get("/api/marketplace/skills/{skill_id}/telemetry")
async def get_skill_telemetry_api(skill_id: str):
    """Retrieves usage telemetry stats for a skill."""
    from backend.marketplace.metering import MeteringEngine
    stats = MeteringEngine.get_skill_stats(skill_id)
    return {"status": "success", "telemetry": stats}


@app.post("/api/marketplace/skills/{skill_id}/checkout")
async def checkout_skill_billing_api(skill_id: str, redirect_url: str = "http://localhost:9119"):
    """Generates payment checkout session via configured BillingAdapter (Phase 5)."""
    from backend.marketplace.billing_adapter import get_billing_adapter
    adapter = get_billing_adapter()
    session = await adapter.create_checkout_session(user_id="default_user", skill_id=skill_id, redirect_url=redirect_url)
    return session
@app.post("/api/marketplace/skills/{skill_id}/verify")
async def verify_skill_billing_api(skill_id: str, payload: Dict[str, Any]):
    """Verifies a newly purchased license or JWT token."""
    from backend.marketplace.billing_adapter import get_billing_adapter
    adapter = get_billing_adapter()
    is_entitled = await adapter.check_entitlement(user_id="default_user", skill_id=skill_id)
    if is_entitled:
        return {"status": "success", "entitled": True, "message": "License verified successfully"}
    else:
        return {"status": "error", "entitled": False, "message": "Invalid license or token"}


@app.get("/api/marketplace/billing/provider")
async def get_billing_provider_api():
    """Returns active billing provider name (noop, stripe, or opennode)."""
    from backend.marketplace.billing_adapter import get_billing_adapter
    adapter = get_billing_adapter()
    return {
        "status": "success",
        "provider": adapter.__class__.__name__,
        "billing_enabled": os.getenv("BILLING_ENABLED", "false").lower() == "true"
    }


@app.get("/api/marketplace/developer/{developer_id}/earnings")
async def get_developer_earnings_api(developer_id: str):
    """Returns developer earnings breakdown (Phase 5)."""
    from backend.marketplace.payouts import payout_engine
    earnings = await payout_engine.get_developer_earnings(developer_id)
    return {"status": "success", "data": earnings}


@app.get("/api/marketplace/billing/usage")
async def get_billing_usage_api(user_id: str = "default_user"):
    """Returns user billing usage and total spent across skills (Phase 5)."""
    from backend.marketplace.payouts import payout_engine
    usage = await payout_engine.get_billing_usage(user_id)
    return {"status": "success", "data": usage}

@app.post("/api/marketplace/developer/onboard")
async def developer_onboard_api(developer_id: str = "default_user", redirect_url: str = "http://localhost:9119"):
    """Initiates Stripe Connect onboarding for a developer."""
    import stripe
    import os
    from backend.database import db_get_developer_stripe_account, db_set_developer_stripe_account
    
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    if not stripe.api_key:
        return {"status": "error", "message": "Stripe is not configured on this server."}
        
    account_id = db_get_developer_stripe_account(developer_id)
    if not account_id:
        account = stripe.Account.create(
            type="express",
            capabilities={
                "card_payments": {"requested": True},
                "transfers": {"requested": True},
            }
        )
        account_id = account.id
        db_set_developer_stripe_account(developer_id, account_id, 0)
        
    account_link = stripe.AccountLink.create(
        account=account_id,
        refresh_url=redirect_url + "?onboard=refresh",
        return_url=redirect_url + "?onboard=success",
        type="account_onboarding",
    )
    return {"status": "success", "onboarding_url": account_link.url}

@app.post("/api/marketplace/stripe/webhook")
async def stripe_webhook_api(request: Request):
    """Handles Stripe Webhooks to update ledger and developer onboarding status."""
    import stripe
    import os
    from fastapi import HTTPException
    from backend.database import _execute
    
    stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
    endpoint_secret = os.environ.get("STRIPE_WEBHOOK_SECRET")
    
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not endpoint_secret:
        return {"status": "ignored", "reason": "No webhook secret configured"}
        
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        client_ref = session.get('client_reference_id')
        if client_ref and "::" in client_ref:
            user_id, skill_id = client_ref.split("::", 1)
            amount_usd = session.get('amount_total', 0) / 100.0
            
            _execute("""
                INSERT INTO marketplace_ledger (user_id, skill_id, amount_usd, transaction_type, provider, reference_id)
                VALUES (?, ?, ?, 'purchase', 'stripe', ?)
            """, (user_id, skill_id, amount_usd, session['id']))
            
            _execute("""
                UPDATE marketplace_skills SET is_installed = 1 WHERE id = ?
            """, (skill_id,))
            
    elif event['type'] == 'account.updated':
        account = event['data']['object']
        if account.get('charges_enabled'):
            _execute("""
                UPDATE marketplace_developers SET onboarding_complete = 1 WHERE stripe_account_id = ?
            """, (account['id'],))
            
    return {"status": "success"}


@app.get("/api/marketplace/skills/{skill_name}/validate-env")
async def validate_skill_env_api(skill_name: str):
    """Check whether all required environment variables for a registered skill are configured."""
    from hermes_sdk.skill import get_registry, validate_skill_env
    registry = get_registry()
    manifest = registry.get(skill_name)
    if manifest is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail=f"Skill '{skill_name}' is not registered."
        )
    result = validate_skill_env(manifest)
    return {
        "skill": skill_name,
        **result,
    }


class RuntimeEnvPayload(BaseModel):
    key: str
    value: str


@app.post("/api/settings/env")
async def set_runtime_env_api(payload: RuntimeEnvPayload):
    """Inject an environment variable into the running process at runtime.

    This endpoint lets the frontend settings panel set a missing API key
    without requiring a server restart or a file edit.  The variable is
    stored **only in the current process memory** — it is NOT persisted to
    disk — so it will be lost on the next container/server restart.

    For permanent configuration, users should add the key to their ``.env``
    file as documented in ``.env.example``.

    Security: This endpoint is protected by the global auth middleware.
    Only authenticated admin users can set env vars.
    """
    import os
    key = payload.key.strip()
    value = payload.value.strip()
    if not key:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Environment variable key must not be empty.")
    # Reject obviously dangerous key names (e.g. PATH, LD_PRELOAD)
    _BLOCKED_KEYS = {"PATH", "LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "PYTHONPATH"}
    if key in _BLOCKED_KEYS:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail=f"Setting '{key}' is not allowed via this endpoint.")
    os.environ[key] = value
    logger.info("Runtime env var set via API: %s (value hidden)", key)
    return {
        "status": "success",
        "message": f"Environment variable '{key}' set for this session. "
                   f"Add it to .env for permanent configuration.",
        "key": key,
        "persistent": False,
    }



# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 15: AUTONOMOUS AGENT MESH & PEER-TO-PEER PROTOCOL
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/api/mesh/peers")
async def get_mesh_peers_api(active_only: bool = True):
    """Returns all registered P2P agent nodes in the Hermes Mesh network."""
    from backend.mesh import get_mesh_router
    router = get_mesh_router()
    peers = router.list_peers(active_only=active_only)
    return {
        "status": "success",
        "count": len(peers),
        "peers": [p.model_dump() if hasattr(p, "model_dump") else p.dict() for p in peers]
    }


@app.post("/api/mesh/peers/register")
async def register_mesh_peer_api(peer_data: Dict[str, Any]):
    """Registers or updates a P2P agent node in the Hermes Mesh network."""
    from backend.mesh import get_mesh_router, MeshPeerManifest
    router = get_mesh_router()
    manifest = MeshPeerManifest(**peer_data)
    registered = router.register_peer(manifest)
    return {
        "status": "success",
        "peer": registered.model_dump() if hasattr(registered, "model_dump") else registered.dict()
    }


@app.post("/api/mesh/dispatch")
async def dispatch_mesh_task_api(task_data: Dict[str, Any]):
    """Dispatches a task payload to a target peer node in the P2P agent mesh network."""
    from backend.mesh import get_mesh_router, MeshTaskPayload
    router = get_mesh_router()
    payload = MeshTaskPayload(**task_data)
    result = router.dispatch_mesh_task(payload)
    return result


@app.post("/api/skills/distill/auto")
async def trigger_auto_distillation_api(min_steps: int = 3, limit: int = 10):
    """Triggers an automatic distillation scan over recent successful multi-step decision logs."""
    from backend.skill_loop import get_skill_distiller
    distiller = get_skill_distiller()
    distilled = distiller.process_undistilled_logs(min_steps=min_steps, limit=limit)
    return {
        "status": "success",
        "distilled_count": len(distilled),
        "skills": distilled
    }


@app.post("/api/skills/distill/{log_id}")
async def trigger_single_log_distillation_api(log_id: int):
    """Distills a specific decision log entry by ID into a reusable SKILL.md file."""
    from backend.database import get_decision_logs, db_is_log_distilled
    logs = get_decision_logs(limit=200)
    target_log = next((l for l in logs if l.get("id") == log_id), None)
    if not target_log:
        raise HTTPException(status_code=404, detail=f"Decision log #{log_id} not found")
    
    if db_is_log_distilled(log_id):
        return {"status": "already_distilled", "message": f"Log #{log_id} has already been distilled."}

    from backend.skill_loop import get_skill_distiller
    distiller = get_skill_distiller()
    skill_dict = distiller.distill_log_entry(target_log)
    saved_skill = distiller.save_and_index_skill(skill_dict)
    return {"status": "success", "skill": saved_skill}

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
                        "ollama/llama3",
                        "ollama/llama3",
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
        {"id": "ollama/llama3", "name": "Google: Gemini 2.5 Flash (default)"},
        {"id": "ollama/llama3", "name": "Google: Gemini 2.5 Pro"},
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
    from backend.database import _execute
    from backend.scheduler import get_all_timers
    import json
    try:
        subagent_rows = _execute("SELECT id FROM subagents")
        subagent_ids = {r[0] for r in subagent_rows}
        
        msg_rows = _execute("SELECT session_id, MAX(timestamp) as last_time FROM messages GROUP BY session_id ORDER BY last_time DESC")
        msg_sessions = [r[0] for r in msg_rows]
        
        # Fetch all metadata from session_metadata table
        meta_rows = _execute("SELECT session_id, title, agent_id, is_scheduled, job_id, schedule_type, schedule_info FROM session_metadata")
        metadata_map = {}
        scheduled_meta_sessions = []
        for r in meta_rows:
            s_id, title, agent_id, is_scheduled, job_id, schedule_type, schedule_info = r
            info_dict = None
            if schedule_info:
                try:
                    info_dict = json.loads(schedule_info)
                except Exception:
                    info_dict = None
            metadata_map[s_id] = {
                "title": title,
                "agent_id": agent_id,
                "is_scheduled": bool(is_scheduled or s_id.startswith("task_")),
                "job_id": job_id or (s_id[5:] if s_id.startswith("task_") else None),
                "schedule_type": schedule_type,
                "schedule_info": info_dict
            }
            if is_scheduled or s_id.startswith("task_"):
                scheduled_meta_sessions.append(s_id)

        # Combine sessions from messages and session_metadata (so newly created sessions with 0 messages appear)
        all_meta_sessions = list(metadata_map.keys())
        all_session_ids = []
        seen = set()
        for s in msg_sessions + all_meta_sessions:
            if s not in seen:
                seen.add(s)
                all_session_ids.append(s)
        
        # Overlay live scheduler info
        live_jobs = {t["id"]: t for t in get_all_timers()}
        
        # Filter out subagents and archive sessions
        user_sessions = [s for s in all_session_ids if s not in subagent_ids and s != "dashboard" and not s.startswith("archive_")]
        
        sessions_response = []
        msg_sessions_set = set(msg_sessions)
        for s in ["dashboard"] + user_sessions:
            meta = metadata_map.get(s, {})
            title = meta.get("title")
            agent_id = meta.get("agent_id")
            is_scheduled = meta.get("is_scheduled", False) or s.startswith("task_")
            job_id = meta.get("job_id") or (s[5:] if s.startswith("task_") else None)
            schedule_type = meta.get("schedule_type")
            schedule_info = meta.get("schedule_info") or {}

            # Filter out deleted ghost timers that have no live job and 0 messages
            if is_scheduled and job_id and job_id not in live_jobs and s not in msg_sessions_set:
                continue

            if job_id and job_id in live_jobs:
                live_info = live_jobs[job_id]
                schedule_info.update(live_info)
                if not schedule_type:
                    schedule_type = live_info.get("type")
                if not title:
                    label = live_info.get("label", "")
                    title = f"⏰ {label}" if label and not label.startswith("⏰") else (label or s)

            if not title:
                if s == "dashboard":
                    title = "Main Terminal"
                else:
                    title = s

            sessions_response.append({
                "id": s,
                "title": title,
                "agent_id": agent_id,
                "is_scheduled": is_scheduled,
                "job_id": job_id,
                "schedule_type": schedule_type,
                "schedule_info": schedule_info
            })
        return sessions_response
    except Exception as e:
        logger.error("Error in get_history_sessions: %s", e)
        return [{"id": "dashboard", "title": "Main Terminal", "agent_id": None, "is_scheduled": False}]

class SessionAgentPayload(BaseModel):
    agent_id: str

@app.post("/api/history/{session_id}/agent")
async def set_session_agent(session_id: str, payload: SessionAgentPayload):
    """Updates the target agent/orchestrator ID for a session in the DB."""
    from backend.database import save_session_metadata, get_session_title
    try:
        title = get_session_title(session_id) or session_id
        save_session_metadata(session_id, title, agent_id=payload.agent_id)
        return {"status": "success", "message": f"Session {session_id} target agent set to {payload.agent_id}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/api/history/{chat_id}")
async def get_history_api(chat_id: str, limit: int = 40):
    from backend.database import get_chat_history
    return get_chat_history(chat_id, limit=limit)

@app.delete("/api/history/{chat_id}")
async def delete_history_api(chat_id: str):
    from backend.database import clear_chat_history, delete_session_title
    from backend.scheduler import cancel_timer_or_alarm, cancel_recurring_reminder
    clear_chat_history(chat_id)
    delete_session_title(chat_id)
    job_id = chat_id[5:] if chat_id.startswith("task_") else chat_id
    cancel_timer_or_alarm(job_id)
    cancel_recurring_reminder(job_id)
    if chat_id in agent_instance.last_costs:
        agent_instance.last_costs[chat_id] = 0.0
    return {"status": "success"}

@app.get("/api/sessions/{session_id}/export-trajectory")
@app.get("/api/history/{session_id}/export")
async def export_session_trajectory(
    session_id: str,
    format: str = Query("sharegpt", description="Export dataset format: sharegpt, openai, or alpaca"),
    extension: str = Query("jsonl", description="Export file extension: jsonl or json"),
    download: bool = Query(True, description="Whether to trigger file download attachment response")
):
    """Exports session execution trajectory in specified format (ShareGPT, OpenAI, or Alpaca)."""
    import json
    from backend.database import get_session_trajectory_data
    from backend.exporters import get_exporter

    data = get_session_trajectory_data(session_id)
    exporter = get_exporter(format)

    ext = extension.lower().strip()
    if ext not in ("jsonl", "json"):
        ext = "jsonl"

    result = exporter.export(
        session_id=session_id,
        messages=data.get("messages", []),
        decision_logs=data.get("decision_logs", []),
        extension=ext
    )

    filename = f"trajectory_{session_id}_{format}.{ext}"

    if download:
        if isinstance(result, (dict, list)):
            content_str = json.dumps(result, indent=2, ensure_ascii=False)
        else:
            content_str = str(result)

        media_type = "application/x-jsonlines" if ext == "jsonl" else "application/json"
        return Response(
            content=content_str,
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )

    if isinstance(result, str) and ext == "jsonl":
        return Response(content=result, media_type="application/x-jsonlines")
    return result


@app.post("/api/history/{session_id}/archive")
async def archive_history_session(session_id: str):
    """Archives a session by renaming its session_id in the DB."""
    from backend.database import _rowcount
    try:
        _rowcount("UPDATE messages SET session_id = ? WHERE session_id = ?", (f"archive_{session_id}", session_id))
        _rowcount("UPDATE session_metadata SET session_id = ? WHERE session_id = ?", (f"archive_{session_id}", session_id))
        return {"status": "success", "message": f"Session {session_id} archived"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.post("/api/history/{session_id}/fork")
async def fork_history_session(session_id: str):
    """Forks a session by duplicating its messages to a new session_id."""
    from backend.database import _execute, get_session_title, save_session_title
    import time
    new_session_id = f"{session_id}_fork_{int(time.time())}"
    try:
        _execute("""
            INSERT INTO messages (session_id, role, content, cost_usd) 
            SELECT ?, role, content, cost_usd FROM messages WHERE session_id = ? ORDER BY id ASC
        """, (new_session_id, session_id))
        
        # Fork custom title metadata
        old_title = get_session_title(session_id)
        if not old_title:
            old_title = session_id
        save_session_title(new_session_id, f"Fork of {old_title}")
        
        return {"status": "success", "new_session_id": new_session_id}
    except Exception as e:
        return {"status": "error", "message": str(e)}

class RenameSessionPayload(BaseModel):
    title: str

@app.post("/api/history/{session_id}/rename")
async def rename_history_session(session_id: str, payload: RenameSessionPayload):
    """Updates the custom title for a session in the DB."""
    from backend.database import save_session_title
    try:
        save_session_title(session_id, payload.title)
        return {"status": "success", "message": f"Session {session_id} renamed to {payload.title}"}
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
        from backend.database import get_chat_history
        from backend.activity_logger import ACTIVITY_LOGS
        from backend.websocket_manager import json_serial
        import json

        history = get_chat_history("dashboard")
        init_payload = {
            "type": "init",
            "config": {
                "system_prompt": agent_instance.system_prompt,
                "model": agent_instance.model
            },
            "logs": DECISION_LOGS[:20],
            "history": history,
            "activity_logs": ACTIVITY_LOGS
        }
        await websocket.send_text(json.dumps(init_payload, default=json_serial, ensure_ascii=False))
        
        while True:
            # Maintain connection alive, process incoming messages if any
            data = await websocket.receive_text()
            try:
                import json
                msg = json.loads(data)
                if msg.get("type") == "chat_message":
                    user_text = msg.get("content", "")
                    chat_id = msg.get("chat_id", "dashboard")

                    # Build display text (shown in chat history — clean, no raw file dump)
                    display_text = user_text

                    # Inject attached file content into agent context only
                    attached_file = msg.get("attached_file")
                    agent_text = user_text
                    if attached_file and isinstance(attached_file, dict):
                        fname = attached_file.get("name", "file")
                        ftype = attached_file.get("type", "text")   # "text" | "pdf"
                        fcontent = attached_file.get("content", "")
                        fpages = attached_file.get("pages")          # PDF only
                        ftruncated = attached_file.get("truncated", False)

                        if fcontent:
                            ext = fname.rsplit(".", 1)[-1].lower() if "." in fname else "txt"
                            code_lang = {
                                "py": "python", "js": "javascript", "ts": "typescript",
                                "tsx": "tsx", "jsx": "jsx", "sh": "bash",
                                "json": "json", "yaml": "yaml", "yml": "yaml",
                                "md": "markdown", "html": "html", "css": "css",
                                "toml": "toml", "xml": "xml"
                            }.get(ext, "")

                            meta_lines = [f"File: {fname}"]
                            if fpages:
                                meta_lines.append(f"Pages: {fpages}")
                            if ftruncated:
                                meta_lines.append("Note: content truncated at limit — summary of the beginning of the document")
                            meta = " | ".join(meta_lines)

                            agent_text = (
                                f"<file_context>\n"
                                f"<!-- {meta} -->\n"
                                f"```{code_lang}\n{fcontent}\n```\n"
                                f"</file_context>\n\n"
                                f"Sir's request: {user_text}"
                            )
                            # Also append a hint so agent knows Obsidian save is available
                            if any(kw in user_text.lower() for kw in [
                                "сохрани", "запиши", "obsidian", "в заметки", "save", "store", "note"
                            ]):
                                agent_text += (
                                    "\n\n[Hint for agent: Sir wants to save this file to Obsidian. "
                                    "Use create_obsidian_note with an informative title derived from the "
                                    f"filename '{fname}' and the file content. Determine the folder from the "
                                    "taxonomy automatically.]"
                                )

                    # Broadcast display_text to chat (user sees original question only)
                    await manager.broadcast({
                        "type": "chat_message",
                        "role": "user",
                        "content": display_text,
                        "chat_id": chat_id,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    # Call agent with enriched context
                    response_text = await agent_instance.respond(agent_text, session_id=chat_id)

                    
                    # Auto-generate title if this is the first message in a custom chat session
                    if chat_id.startswith("chat_"):
                        from backend.database import get_session_title, save_session_title
                        if not get_session_title(chat_id):
                            async def generate_and_broadcast_title():
                                try:
                                    import asyncio
                                    from backend.agent import generate_chat_title
                                    title = await generate_chat_title(
                                        user_message=user_text,
                                        api_key=agent_instance.api_key,
                                        api_base=agent_instance.api_base,
                                        model=agent_instance.model
                                    )
                                    save_session_title(chat_id, title)
                                    await manager.broadcast({
                                        "type": "session_title_update",
                                        "chat_id": chat_id,
                                        "title": title
                                    })
                                except Exception as ex:
                                    logger.error(f"Error generating session title: {ex}")
                            import asyncio
                            asyncio.create_task(generate_and_broadcast_title())

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
                        "id": assistant_msg_id,
                        "timestamp": datetime.now(timezone.utc).isoformat()
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
