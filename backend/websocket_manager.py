import json
import logging
from typing import Set, Dict, Any
from fastapi import WebSocket

logger = logging.getLogger("hermes.ws")

class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket, subprotocol: str | None = None):
        await websocket.accept(subprotocol=subprotocol)
        self.active_connections.add(websocket)
        logger.info(f"New dashboard connected. Total active connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
        logger.info(f"Dashboard disconnected. Total active connections: {len(self.active_connections)}")

    async def broadcast(self, message: Dict[str, Any]):
        """Broadcasts a JSON message to all active WebSocket clients (the frontend)."""
        if not self.active_connections:
            return
        
        message_str = json.dumps(message)
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
