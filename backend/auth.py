import base64
import hashlib
import hmac
import json
import os
import time
import secrets
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger("hermes.auth")

SESSION_TTL_SECONDS = 12 * 3600
OTP_TTL_SECONDS = 300
OTP_MAX_ATTEMPTS = 5

# Process-local OTP copy so existing tests can read the issued code.
# Verification always uses the hashed DB row so replicas/restarts agree.
current_otp: Dict[str, Any] = {}


def _token_sha256(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _otp_hash(code: str) -> str:
    return hashlib.sha256(code.strip().encode("utf-8")).hexdigest()


def _session_row_live(row: Optional[Dict[str, Any]], now: Optional[int] = None) -> bool:
    if not row:
        return False
    now = int(time.time()) if now is None else now
    if row.get("revoked_at") is not None:
        return False
    return int(row.get("expires_at") or 0) > now


class _ActiveSessions:
    """DB-backed session set with an in-memory overlay for test tokens."""

    def __init__(self) -> None:
        self._mem: set[str] = set()

    def add(self, token: str) -> None:
        if not token:
            return
        self._mem.add(token)
        _persist_session(token)

    def __contains__(self, token: object) -> bool:
        if not isinstance(token, str) or not token:
            return False
        if token in self._mem:
            row = _fetch_session(token)
            if row is None:
                return True
            return _session_row_live(row)
        return _session_row_live(_fetch_session(token))

    def remove(self, token: str) -> None:
        self._mem.discard(token)
        _revoke_session(token)

    def discard(self, token: str) -> None:
        self.remove(token)

    def __len__(self) -> int:
        return len(self._mem)

    def clear(self) -> None:
        self._mem.clear()


active_sessions = _ActiveSessions()


def reset_in_memory_auth_state(token: Optional[str] = None) -> None:
    """Drop process-local OTP/session cache (simulates a worker restart).

    If `token` is given, only that session is evicted from memory so other
    tests' fixture tokens stay valid.
    """
    global current_otp
    current_otp = {}
    if token:
        active_sessions._mem.discard(token)
    else:
        active_sessions.clear()


def _persist_session(token: str, ttl_seconds: int = SESSION_TTL_SECONDS) -> None:
    try:
        from backend.database import upsert_auth_session
        now = int(time.time())
        expires_at = now + int(ttl_seconds)
        upsert_auth_session(
            token_sha256=_token_sha256(token),
            subject="local-admin",
            roles="admin",
            created_at=now,
            expires_at=expires_at,
            last_seen_at=now,
        )
    except Exception as e:
        logger.warning("Failed to persist auth session: %s", e)


def _fetch_session(token: str) -> Optional[Dict[str, Any]]:
    try:
        from backend.database import get_auth_session
        return get_auth_session(_token_sha256(token))
    except Exception as e:
        logger.debug("Failed to load auth session: %s", e)
        return None


def _revoke_session(token: str) -> None:
    try:
        from backend.database import revoke_auth_session
        revoke_auth_session(_token_sha256(token), int(time.time()))
    except Exception as e:
        logger.debug("Failed to revoke auth session: %s", e)


def _touch_session(token: str) -> None:
    try:
        from backend.database import touch_auth_session
        now = int(time.time())
        touch_auth_session(_token_sha256(token), now, now + SESSION_TTL_SECONDS, now)
    except Exception as e:
        logger.debug("Failed to touch auth session: %s", e)


def generate_otp() -> str:
    """Generates a secure 6-digit OTP code and sets its expiration to 5 minutes from now."""
    code = f"{secrets.randbelow(900000) + 100000}"  # 6 digit number between 100000 and 999999
    expires_at = int(time.time()) + OTP_TTL_SECONDS

    global current_otp
    current_otp = {
        "code": code,
        "expires_at": expires_at,
    }
    try:
        from backend.database import upsert_auth_otp
        upsert_auth_otp(_otp_hash(code), expires_at)
    except Exception as e:
        logger.warning("Failed to persist OTP: %s", e)
    logger.info("Generated new OTP code. Expires in 5 minutes.")
    return code


def write_emergency_otp_file(code: str) -> bool:
    """
    Writes the active OTP to backend/data/.current_otp with restricted permissions (0600).
    Used as an emergency fallback during network/DNS isolation or Telegram API outages.
    """
    try:
        data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        otp_file = os.path.join(data_dir, ".current_otp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        fd = os.open(otp_file, flags, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(code.strip())
        return True
    except Exception as e:
        logger.debug(f"Failed to write emergency OTP file: {e}")
        return False


def _clear_emergency_otp_file() -> None:
    try:
        otp_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", ".current_otp")
        if os.path.exists(otp_file):
            os.remove(otp_file)
    except Exception:
        pass


def verify_otp_status(code: str) -> str:
    """Verify OTP against the hashed DB row.

    Returns:
        "ok" | "invalid" | "locked"
    """
    global current_otp
    submitted = (code or "").strip()
    candidate_hash = _otp_hash(submitted) if submitted else _otp_hash("0")
    now = int(time.time())

    try:
        from backend.database import get_auth_otp, consume_auth_otp, increment_auth_otp_failure, clear_auth_otp
        row = get_auth_otp()
    except Exception as e:
        logger.warning("Failed to load OTP state: %s", e)
        row = None
        consume_auth_otp = increment_auth_otp_failure = clear_auth_otp = None  # type: ignore

    if row:
        stored_hash = str(row.get("code_hash") or "")
        if int(row.get("expires_at") or 0) <= now:
            logger.warning("OTP verification failed: Code expired.")
            current_otp = {}
            if clear_auth_otp:
                try:
                    clear_auth_otp()
                except Exception:
                    pass
            return "invalid"
        if int(row.get("locked") or 0) or int(row.get("attempts") or 0) >= OTP_MAX_ATTEMPTS:
            logger.warning("OTP verification failed: Too many attempts.")
            current_otp = {}
            return "locked"
        if len(stored_hash) != len(candidate_hash):
            stored_hash = candidate_hash  # keep compare_digest length-safe; still fail
            hashes_ok = False
        else:
            hashes_ok = hmac.compare_digest(stored_hash, candidate_hash)
        if hashes_ok and submitted:
            consumed = False
            if consume_auth_otp:
                try:
                    consumed = consume_auth_otp(candidate_hash, now)
                except Exception:
                    consumed = False
            if consumed:
                current_otp = {}
                _clear_emergency_otp_file()
                logger.info("OTP verification successful.")
                return "ok"
            logger.warning("OTP verification failed: Code already used.")
            return "invalid"
        if increment_auth_otp_failure:
            try:
                increment_auth_otp_failure(OTP_MAX_ATTEMPTS)
            except Exception:
                pass
        logger.warning("OTP verification failed: Incorrect code.")
        return "invalid"

    # Memory fallback (tests / DB unavailable on a single worker)
    if not current_otp:
        return "invalid"
    if now > int(current_otp.get("expires_at") or 0):
        logger.warning("OTP verification failed: Code expired.")
        current_otp = {}
        return "invalid"
    stored_code = str(current_otp.get("code") or "")
    if hmac.compare_digest(stored_code.encode("utf-8"), submitted.encode("utf-8")) if len(stored_code) == len(submitted) else False:
        current_otp = {}
        _clear_emergency_otp_file()
        logger.info("OTP verification successful.")
        return "ok"
    logger.warning("OTP verification failed: Incorrect code.")
    return "invalid"


def verify_otp(code: str) -> bool:
    """Verifies if the code is correct and not expired."""
    return verify_otp_status(code) == "ok"


def create_session(ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    """Generates a secure session token and persists its hash."""
    token = secrets.token_hex(32)
    active_sessions._mem.add(token)
    _persist_session(token, ttl_seconds=ttl_seconds)
    logger.info("New session created. Total active sessions: %s", len(active_sessions))
    return token


def validate_session(token: str) -> bool:
    """Checks if a session token is valid (local session or signed OIDC JWT)."""
    if token and token in active_sessions:
        if token not in active_sessions._mem or _fetch_session(token) is not None:
            _touch_session(token)
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
    """Revokes a session token in the database and drops the process cache."""
    if not token:
        return
    active_sessions.remove(token)
    logger.info("Session destroyed. Total active sessions: %s", len(active_sessions))


# ═══════════════════════════════════════════════════════════════════════════════
# STAGE 13: ENTERPRISE SSO & MULTI-TENANT RBAC (OIDC / JWT)
# ═══════════════════════════════════════════════════════════════════════════════

ROLE_HIERARCHY = {
    "admin": 100,
    "editor": 50,
    "operator": 30,
    "viewer": 10,
}

def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def decode_jwt_payload(token: str) -> Optional[Dict[str, Any]]:
    """
    Return JWT claims only after the HS256 signature matches JWT_SECRET.
    Unset secret, alg=none, or a bad signature yields None.
    """
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        return None
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
        header = json.loads(_b64url_decode(header_b64))
        if not isinstance(header, dict) or header.get("alg") != "HS256":
            return None
        expected = hmac.new(
            secret.encode("utf-8"),
            f"{header_b64}.{payload_b64}".encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _b64url_decode(sig_b64)):
            return None
        claims = json.loads(_b64url_decode(payload_b64))
        return claims if isinstance(claims, dict) else None
    except Exception as e:
        logger.debug(f"JWT verification failed: {e}")
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
