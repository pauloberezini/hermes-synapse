import asyncio
import json
import logging
from datetime import datetime, date
from typing import Set, Dict, Any
try:
    from fastapi import WebSocket
except ImportError:
    WebSocket = Any  # type: ignore

logger = logging.getLogger("hermes.ws")

def json_serial(obj: object) -> str:
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)

class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: Set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.add(websocket)
        self._loop = asyncio.get_running_loop()
        logger.debug(f"New dashboard connected. Total active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.debug(f"Dashboard disconnected. Total active connections: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcasts a JSON message to all active WebSocket clients (the frontend)."""
        if not self.active_connections:
            return
        
        message_str = json.dumps(message, default=json_serial, ensure_ascii=False)
        logger.debug(f"Broadcasting to {len(self.active_connections)} clients: {message_str}")
        
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_text(message_str)
            except Exception:
                logger.warning("Error sending message through websocket, marking connection for deletion")
                disconnected.add(connection)
                
        for connection in disconnected:
            self.disconnect(connection)

# Singleton manager
manager = ConnectionManager()
websocket_manager = manager


def broadcast_sync(message: Dict[str, Any]) -> None:
    """Best-effort broadcast. A worker thread hops onto the loop recorded at connect.

    A missing loop or a loop that is not running is a silent no-op. Zero clients
    is also a no-op, inside ``ConnectionManager.broadcast``.
    """
    try:
        running = asyncio.get_running_loop()
    except RuntimeError:
        recorded = manager._loop
        if recorded is None or not recorded.is_running():
            return
        try:
            asyncio.run_coroutine_threadsafe(manager.broadcast(message), recorded)
        except RuntimeError:
            return
        return
    running.create_task(manager.broadcast(message))
