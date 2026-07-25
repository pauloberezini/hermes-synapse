import time
import secrets
import logging
from typing import Dict, Set, Any, Optional, List

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
    """Checks if a session token is valid (local session or OIDC JWT token)."""
    if token in active_sessions:
        return True
    
    # Check if token is a valid unexpired OIDC JWT token
    claims = decode_jwt_payload(token)
    if claims:
        now = int(time.time())
        exp = claims.get("exp")
        if exp is None or now < int(exp):
            return True
        logger.warning("OIDC JWT token expired.")
    return False

def destroy_session(token: str):
    """Removes a session token from active sessions."""
    if token in active_sessions:
        active_sessions.remove(token)
        logger.info(f"Session destroyed. Total active sessions: {len(active_sessions)}")


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 13: ENTERPRISE SSO & MULTI-TENANT RBAC (OIDC / JWT)
# ═══════════════════════════════════════════════════════════════════════════════

import base64
import json

ROLE_HIERARCHY = {
    "admin": 100,
    "editor": 50,
    "operator": 30,
    "viewer": 10,
}

def decode_jwt_payload(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodes a standard JWT payload without requiring external crypto dependencies.
    Useful for local OIDC validation and role extraction.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        # Restore padding
        padding = "=" * (4 - len(payload_b64) % 4)
        decoded_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(decoded_bytes.decode("utf-8"))
    except Exception as e:
        logger.debug(f"JWT payload decoding skipped: {e}")
        return None

def get_user_roles(token: str) -> List[str]:
    """
    Extracts assigned RBAC roles from session token or OIDC JWT claims.
    Falls back to ['admin'] for local single-user sessions.
    """
    if token in active_sessions:
        return ["admin"]
    
    claims = decode_jwt_payload(token)
    if not claims:
        return ["viewer"]
    
    # Check standard OIDC / Keycloak / Auth0 role claims
    roles = []
    if "roles" in claims and isinstance(claims["roles"], list):
        roles.extend(claims["roles"])
    if "realm_access" in claims and isinstance(claims["realm_access"], dict):
        roles.extend(claims["realm_access"].get("roles", []))
    if "groups" in claims and isinstance(claims["groups"], list):
        roles.extend(claims["groups"])
    
    if not roles and "sub" in claims:
        roles = ["editor"]
        
    return [str(r).lower() for r in roles] or ["viewer"]

def check_rbac_permission(token: str, required_role: str = "viewer") -> bool:
    """
    Validates if the user holding `token` has at least `required_role` level permissions.
    Role Hierarchy: admin (100) > editor (50) > operator (30) > viewer (10).
    """
    user_roles = get_user_roles(token)
    user_max_level = max([ROLE_HIERARCHY.get(r, 10) for r in user_roles], default=10)
    required_level = ROLE_HIERARCHY.get(required_role.lower(), 10)
    return user_max_level >= required_level
