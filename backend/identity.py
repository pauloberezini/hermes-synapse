"""Identity and Principal primitives for authorization, RBAC, and audit logging.

Provides the `Principal` dataclass and helpers to extract the caller principal
from session tokens or incoming FastAPI requests.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request, status

logger = logging.getLogger("hermes.identity")


@dataclass(frozen=True)
class Principal:
    """Represents an authenticated caller (human operator, service, or agent)."""

    subject: str  # "local-admin" for OTP sessions, JWT "sub" otherwise
    roles: tuple[str, ...]  # lower-case tuple of roles
    tenant_id: str = "default"
    auth_method: str = "otp"  # "otp" | "jwt" | "service" | "agent"


def principal_from_token(token: str) -> Principal:
    """Resolve an authentication token to a Principal.

    Args:
        token: Bearer token (either local OTP session token or signed JWT).

    Returns:
        Principal corresponding to the caller.

    Raises:
        ValueError: If the token cannot be authenticated.
    """
    from backend.auth import active_sessions, decode_jwt_payload, get_user_roles

    if token in active_sessions:
        return Principal(
            subject="local-admin",
            roles=("admin", "owner"),
            tenant_id="default",
            auth_method="otp",
        )

    claims = decode_jwt_payload(token)
    if claims is not None:
        sub = str(claims.get("sub") or "anonymous")
        roles = tuple(get_user_roles(token))
        tenant = str(claims.get("tenant_id") or claims.get("tenant") or "default")
        return Principal(
            subject=sub,
            roles=roles,
            tenant_id=tenant,
            auth_method="jwt",
        )

    raise ValueError("Invalid or expired session token")


def current_principal(request: Request) -> Principal:
    """FastAPI dependency to retrieve the current Principal.

    Reads `request.state.principal` if populated by middleware, or parses
    the Authorization header directly.

    Args:
        request: FastAPI HTTP request.

    Returns:
        The authenticated Principal.

    Raises:
        HTTPException: 401 if unauthenticated or invalid token.
    """
    cached: Any = getattr(request.state, "principal", None)
    if isinstance(cached, Principal):
        return cached

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid Authorization header",
        )

    token = auth_header.split(" ", 1)[1].strip()
    try:
        principal = principal_from_token(token)
        request.state.principal = principal
        return principal
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(err),
        ) from err
