"""Persistence, expiry, revocation, and OTP hardening for R2-6."""
import hashlib
import logging

from fastapi.testclient import TestClient

from backend.auth import (
    OTP_MAX_ATTEMPTS,
    create_session,
    destroy_session,
    generate_otp,
    reset_in_memory_auth_state,
    validate_session,
    verify_otp,
    verify_otp_status,
)
from backend.main import app
from backend import database as db_mod


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def test_session_survives_simulated_restart():
    token = create_session()
    assert validate_session(token) is True
    reset_in_memory_auth_state(token)
    assert validate_session(token) is True
    from backend.identity import principal_from_token
    from backend.auth import get_user_roles
    assert get_user_roles(token) == ["admin"]
    principal = principal_from_token(token)
    assert principal.subject == "local-admin"
    assert principal.auth_method == "otp"

    client = TestClient(app)
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200


def test_expired_session_is_rejected():
    token = create_session(ttl_seconds=0)
    reset_in_memory_auth_state(token)
    assert validate_session(token) is False

    client = TestClient(app)
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_revoked_session_is_rejected():
    token = create_session()
    destroy_session(token)
    reset_in_memory_auth_state(token)
    assert validate_session(token) is False

    client = TestClient(app)
    resp = client.get("/api/config", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_logout_revokes_session():
    token = create_session()
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/config", headers=headers).status_code == 200
    assert client.post("/api/auth/logout", headers=headers).status_code == 200
    reset_in_memory_auth_state(token)
    assert client.get("/api/config", headers=headers).status_code == 401


def test_session_table_stores_hash_not_plaintext():
    token = create_session()
    rows = db_mod._execute("SELECT token_sha256 FROM auth_sessions")
    dumped = " ".join(str(r) for r in rows)
    assert token not in dumped
    assert _sha(token) in dumped


def test_otp_single_use_and_constant_time_mismatch():
    code = generate_otp()
    assert verify_otp(code) is True
    assert verify_otp(code) is False
    assert verify_otp_status(code) == "invalid"


def test_otp_brute_force_lockout():
    code = generate_otp()
    client = TestClient(app)
    for _ in range(OTP_MAX_ATTEMPTS):
        resp = client.post("/api/auth/verify-code", json={"code": "000000"})
        assert resp.status_code == 401
    locked = client.post("/api/auth/verify-code", json={"code": "000000"})
    assert locked.status_code == 429
    # Original code is burned even if guessed after lockout.
    burned = client.post("/api/auth/verify-code", json={"code": code})
    assert burned.status_code == 429
    import backend.auth as auth_mod
    auth_mod.current_otp = {}
    assert verify_otp(code) is False  # burned in DB even with empty process OTP cache


def test_otp_hash_not_plaintext_in_db():
    code = generate_otp()
    rows = db_mod._execute("SELECT code_hash FROM auth_otp")
    dumped = " ".join(str(r) for r in rows)
    assert code not in dumped
    assert hashlib.sha256(code.encode("utf-8")).hexdigest() in dumped


def test_otp_not_written_to_logs(caplog):
    caplog.set_level(logging.DEBUG)
    code = generate_otp()
    assert code not in caplog.text
    assert "Generated OTP Code:" not in caplog.text

    import os
    from unittest.mock import AsyncMock, MagicMock
    import backend.bot

    original_bot = backend.bot.telegram_app
    backend.bot.telegram_app = MagicMock()
    backend.bot.telegram_app.bot = AsyncMock()
    original_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    os.environ["TELEGRAM_CHAT_ID"] = "12345"
    try:
        import backend.auth as auth_mod
        client = TestClient(app)
        with caplog.at_level(logging.DEBUG):
            resp = client.post("/api/auth/request-code")
        assert resp.status_code == 200
        issued = auth_mod.current_otp.get("code")
        assert issued
        assert issued not in caplog.text
        assert "Generated OTP Code:" not in caplog.text
    finally:
        backend.bot.telegram_app = original_bot
        if original_chat_id is not None:
            os.environ["TELEGRAM_CHAT_ID"] = original_chat_id
        else:
            os.environ.pop("TELEGRAM_CHAT_ID", None)
