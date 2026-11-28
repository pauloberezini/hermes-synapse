"""Dedicated gateway hook token. Not a session, not JWT, not an RBAC role.

``HERMES_GATEWAY_TOKEN`` must be at least 32 characters. Compare is
constant-time. The raw token is never returned, logged, or written to
decision_log. Bind defaults to loopback (``127.0.0.1``).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse

MIN_TOKEN_LEN = 32
DEFAULT_BIND = "127.0.0.1"
PATH = "/api/gateway/pre-tool"

_log = logging.getLogger("hermes.gateway")
_redact_installed = False


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


def configured_token() -> Optional[str]:
    raw = os.environ.get("HERMES_GATEWAY_TOKEN", "")
    if len(raw) < MIN_TOKEN_LEN:
        return None
    return raw


def tokens_match(provided: str, expected: str) -> bool:
    """Length-independent compare: digest both, then ``hmac.compare_digest``."""
    return hmac.compare_digest(_digest(provided), _digest(expected))


def redact_token(text: str) -> str:
    token = os.environ.get("HERMES_GATEWAY_TOKEN") or ""
    if token and token in text:
        return text.replace(token, "[HERMES_GATEWAY_TOKEN_REDACTED]")
    return text


class _TokenRedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        token = os.environ.get("HERMES_GATEWAY_TOKEN") or ""
        if not token:
            return True

        def _scrub(value: object) -> object:
            if isinstance(value, str) and token in value:
                return value.replace(token, "[HERMES_GATEWAY_TOKEN_REDACTED]")
            return value

        if isinstance(record.msg, str):
            record.msg = _scrub(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: _scrub(v) for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(_scrub(a) for a in record.args)
        return True


def install_token_redact_filter() -> None:
    """Attach once so the token cannot leak through logging handlers."""
    global _redact_installed
    if _redact_installed:
        return
    filt = _TokenRedactFilter()
    logging.getLogger().addFilter(filt)
    for name in ("hermes", "hermes.gateway", "hermes.main", "uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).addFilter(filt)
    _redact_installed = True


def bind_hosts() -> set[str]:
    raw = os.environ.get("HERMES_GATEWAY_BIND", DEFAULT_BIND).strip() or DEFAULT_BIND
    allowed = {part.strip() for part in raw.split(",") if part.strip()}
    if "127.0.0.1" in allowed:
        allowed.update({"127.0.0.1", "::1", "localhost"})
    return allowed


def peer_host(request: Request) -> str:
    if request.client is None:
        return ""
    return request.client.host or ""


def forwarded(request: Request) -> bool:
    """Reject proxied requests by default so bind cannot be spoofed."""
    if os.environ.get("HERMES_GATEWAY_TRUST_PROXY", "").strip().lower() in ("1", "true", "yes"):
        return False
    for name in ("x-forwarded-for", "x-real-ip", "forwarded"):
        if request.headers.get(name):
            return True
    return False


def authorize_gateway_request(request: Request) -> Optional[JSONResponse]:
    """Return an error response, or None if the caller may use the hook API.

    Fail closed. Never include the token (or a prefix of it) in the body.
    """
    install_token_redact_filter()
    if forwarded(request):
        _log.warning("gateway hook rejected: forwarded header from %s", peer_host(request) or "unknown")
        return JSONResponse(status_code=403, content={"detail": "Gateway hook is loopback-only"})

    host = peer_host(request)
    if host not in bind_hosts():
        _log.warning("gateway hook rejected: peer %s not in bind list", host or "unknown")
        return JSONResponse(status_code=403, content={"detail": "Gateway hook is loopback-only"})

    expected = configured_token()
    if expected is None:
        _log.error("gateway hook unconfigured: HERMES_GATEWAY_TOKEN missing or shorter than %s", MIN_TOKEN_LEN)
        return JSONResponse(
            status_code=503,
            content={"detail": "Gateway hook token is not configured"},
        )

    auth = request.headers.get("Authorization") or ""
    if not auth.startswith("Bearer "):
        _log.warning("gateway hook rejected: missing bearer")
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    provided = auth[7:]
    if not tokens_match(provided, expected):
        _log.warning("gateway hook rejected: token mismatch")
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return None
