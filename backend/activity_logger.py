import time
import logging
from typing import List, Dict, Any

logger = logging.getLogger("hermes.activity_logger")

# In-memory log buffer containing the last 200 activity records, loaded from database on startup
ACTIVITY_LOGS: List[Dict[str, Any]] = []
try:
    from backend.database import get_activity_logs
    ACTIVITY_LOGS = get_activity_logs(200)
except Exception as e:
    logger.warning(f"Could not load activity logs from database on startup: {e}")

def log_activity(activity_type: str, source: str, message: str, token_cost: float = 0.0):
    """
    Log system activity.
    activity_type: 'active' (user tasks/thinking) or 'idle' (background ticks)
    source: Component name (e.g. 'Orchestrator', 'PriceMonitor', 'Scheduler')
    message: Log text description
    token_cost: Token cost estimate in USD (defaults to 0.0)
    """
    from datetime import datetime
    from zoneinfo import ZoneInfo
    
    entry = {
        "timestamp": datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%H:%M:%S"),
        "type": activity_type,
        "source": source,
        "message": message,
        "token_cost": token_cost
    }
    
    ACTIVITY_LOGS.insert(0, entry)
    if len(ACTIVITY_LOGS) > 200:
        ACTIVITY_LOGS.pop()
        
    # Save to database
    try:
        from backend.database import save_activity_log
        save_activity_log(entry)
    except Exception as db_err:
        logger.error(f"Failed to save activity log to database: {db_err}")
        
    logger.info(f"[{activity_type.upper()}] ({source}) {message} | Cost: ${token_cost:.6f}")
    
    # Broadcast to WebSocket manager if loop is active
    try:
        import asyncio
        from backend.websocket_manager import manager
        
        try:
            loop = asyncio.get_running_loop()
            if loop.is_running():
                loop.create_task(manager.broadcast({
                    "type": "activity_log",
                    "log": entry
                }))
        except RuntimeError:
            # No running event loop (e.g. running in synchronous tests or scripts)
            pass
    except Exception as e:
        logger.debug(f"Failed to broadcast activity log: {e}")
