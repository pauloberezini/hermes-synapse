"""Fail-fast checks for production/pilot secrets.

Compose interpolation already rejects unset POSTGRES_PASSWORD / QDRANT_API_KEY /
JWT_SECRET. This rejects known-weak placeholders so a copied .env.example cannot
boot with ENV=production.
"""
from __future__ import annotations

import os
import sys
from typing import Mapping, Optional

_PRODUCTION = {"production", "prod", "pilot"}
_WEAK = {
    "",
    "postgres",
    "password",
    "changeme",
    "change_me",
    "secret",
    "admin",
    "hermes",
    "pass",
    "jwt_secret",
    "your_jwt_secret_here",
    "your_qdrant_api_key_here",
}

_MIN_JWT_LEN = 32
_MIN_QDRANT_KEY_LEN = 16


def _is_weak(value: str) -> bool:
    return (value or "").strip().lower() in _WEAK


def validate_runtime_secrets(env: Optional[Mapping[str, str]] = None) -> list[str]:
    e = env if env is not None else os.environ
    mode = (e.get("ENV") or "").strip().lower()
    if mode not in _PRODUCTION:
        return []

    errors: list[str] = []
    jwt = (e.get("JWT_SECRET") or "").strip()
    if _is_weak(jwt) or len(jwt) < _MIN_JWT_LEN:
        errors.append(
            "JWT_SECRET is missing, a known default, or shorter than 32 characters"
        )

    password = (e.get("POSTGRES_PASSWORD") or "").strip()
    if _is_weak(password):
        errors.append("POSTGRES_PASSWORD is missing or a known default")

    db_url = e.get("DATABASE_URL") or ""
    for weak in ("postgres", "password", "changeme", "hermes", "admin"):
        if f":{weak}@" in db_url:
            errors.append("DATABASE_URL embeds a known-default password")
            break

    qkey = (e.get("QDRANT_API_KEY") or "").strip()
    if _is_weak(qkey) or len(qkey) < _MIN_QDRANT_KEY_LEN:
        errors.append(
            "QDRANT_API_KEY is missing, a known default, or shorter than 16 characters"
        )

    return errors


def enforce_runtime_secrets() -> None:
    errors = validate_runtime_secrets()
    if not errors:
        return
    for msg in errors:
        print(f"FATAL: {msg}", file=sys.stderr)
    print(
        "FATAL: refusing to start with unsafe production secrets. "
        "Set JWT_SECRET, POSTGRES_PASSWORD, and QDRANT_API_KEY. "
        "See .env.example.",
        file=sys.stderr,
    )
    raise SystemExit(1)
