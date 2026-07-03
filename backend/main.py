import logging
from typing import List, Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, Request, Response
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

class SubagentPosition(BaseModel):
    id: str
    x: int
    y: int

class SubagentPositionsUpdate(BaseModel):
    positions: List[SubagentPosition]

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

class ConfigUpdate(BaseModel):
    system_prompt: str | None = None
    model: str | None = None

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
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")

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
            if os.path.isfile(p):
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

@app.delete("/api/timers/{timer_id}")
async def cancel_timer_api(timer_id: str):
    from backend.scheduler import cancel_timer_or_alarm
    ok = cancel_timer_or_alarm(timer_id)
    return {"status": "cancelled" if ok else "not_found", "timer_id": timer_id}

@app.get("/api/subagents")
async def get_subagents_api():
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
        subagent.y
    )
    return {"status": "success", "id": clean_id}

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

@app.get("/api/history/{chat_id}")
async def get_history_api(chat_id: str, limit: int = 40):
    from backend.database import get_chat_history
    return get_chat_history(chat_id, limit=limit)

@app.get("/api/history/sessions")
async def get_history_sessions():
    from backend.database import DB_PATH
    import sqlite3
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM subagents")
        subagent_ids = {r[0] for r in cursor.fetchall()}
        
        cursor.execute("SELECT DISTINCT session_id FROM messages")
        sessions = [r[0] for r in cursor.fetchall()]
        conn.close()
        
        # Filter out subagents, and keep only "dashboard" and custom sessions
        user_sessions = [s for s in sessions if s not in subagent_ids and s != "dashboard"]
        return ["dashboard"] + user_sessions
    except Exception as e:
        return ["dashboard"]

@app.delete("/api/history/{chat_id}")
async def delete_history_api(chat_id: str):
    from backend.database import clear_chat_history
    clear_chat_history(chat_id)
    # Also clear from agent's in-memory last costs or messages if needed
    if chat_id in agent_instance.last_costs:
        agent_instance.last_costs[chat_id] = 0.0
    return {"status": "success"}



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
