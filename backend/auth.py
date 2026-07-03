import time
import secrets
import logging
from typing import Dict, Set, Any

logger = logging.getLogger("hermes.auth")

# In-memory stores
active_sessions: Set[str] = set()
# Map session ID to username / meta if needed, or just set of active tokens.

# Store details of the active OTP code
# Structure: {"code": "123456", "expires_at": 1718900000}
current_otp: Dict[str, Any] = {}

def generate_otp() -> str:
    """Generates a secure 6-digit OTP code and sets its expiration to 5 minutes from now."""
    code = f"{secrets.randbelow(900000) + 100000}"  # 6 digit number between 100000 and 999999
    expires_at = int(time.time()) + 300  # 5 minutes
    
    global current_otp
    current_otp = {
        "code": code,
        "expires_at": expires_at
    }
    logger.info(f"Generated new OTP code. Expires in 5 minutes.")
    return code

def verify_otp(code: str) -> bool:
    """Verifies if the code is correct and not expired."""
    global current_otp
    if not current_otp:
        return False
        
    now = int(time.time())
    if now > current_otp.get("expires_at", 0):
        logger.warning("OTP verification failed: Code expired.")
        current_otp = {}
        return False
        
    if current_otp.get("code") == code.strip():
        # Clear code after successful verify to prevent reuse
        current_otp = {}
        logger.info("OTP verification successful.")
        return True
        
    logger.warning("OTP verification failed: Incorrect code.")
    return False

def create_session() -> str:
    """Generates a secure session token and adds it to the active sessions set."""
    token = secrets.token_hex(32)
    active_sessions.add(token)
    logger.info(f"New session created. Total active sessions: {len(active_sessions)}")
    return token

def validate_session(token: str) -> bool:
    """Checks if a session token is valid."""
    return token in active_sessions

def destroy_session(token: str):
    """Removes a session token from active sessions."""
    if token in active_sessions:
        active_sessions.remove(token)
        logger.info(f"Session destroyed. Total active sessions: {len(active_sessions)}")
