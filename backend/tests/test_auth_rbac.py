"""
Unit tests for backend.auth package (Stage 13: OIDC JWT decoding & RBAC permission checks).
"""
import hashlib
import hmac
import time
import base64
import json
from fastapi.testclient import TestClient
from backend.auth import (
    create_session,
    validate_session,
    decode_jwt_payload,
    get_user_roles,
    check_rbac_permission,
)
from backend.main import app


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _make_mock_jwt(payload: dict) -> str:
    """Unsigned stand-in: header claims HS256, signature is not a MAC."""
    header_b64 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    payload_b64 = _b64url(json.dumps(payload).encode("utf-8"))
    return f"{header_b64}.{payload_b64}.mock_signature"


def _sign_jwt(payload: dict, secret: str, alg: str = "HS256") -> str:
    header_b64 = _b64url(json.dumps({"alg": alg, "typ": "JWT"}, separators=(",", ":")).encode())
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    if alg == "none":
        return f"{header_b64}.{payload_b64}."
    sig = hmac.new(secret.encode("utf-8"), f"{header_b64}.{payload_b64}".encode("ascii"), hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url(sig)}"


def test_local_session_admin_roles():
    token = create_session()
    assert validate_session(token) is True
    roles = get_user_roles(token)
    assert roles == ["admin"]
    assert check_rbac_permission(token, "admin") is True
    assert check_rbac_permission(token, "editor") is True


def test_jwt_payload_decoding_and_expiration(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    now = int(time.time())
    valid_payload = {"sub": "user_123", "roles": ["editor"], "exp": now + 3600}
    jwt_token = _sign_jwt(valid_payload, "test-secret")

    assert validate_session(jwt_token) is True
    roles = get_user_roles(jwt_token)
    assert "editor" in roles
    assert check_rbac_permission(jwt_token, "editor") is True
    assert check_rbac_permission(jwt_token, "admin") is False

    expired_token = _sign_jwt({"sub": "user_123", "roles": ["admin"], "exp": now - 3600}, "test-secret")
    assert validate_session(expired_token) is False


def test_invalid_jwt_token_handling():
    invalid_token = "invalid.token.string"
    assert decode_jwt_payload(invalid_token) is None
    assert get_user_roles(invalid_token) == ["viewer"]
    assert check_rbac_permission(invalid_token, "admin") is False


def test_dev_master_token_is_not_a_session():
    assert validate_session("dev_master_token") is False
    assert check_rbac_permission("dev_master_token", "admin") is False


def test_forged_jwt_does_not_authenticate_or_grant_admin(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    now = int(time.time())
    forged = _make_mock_jwt({"sub": "attacker", "roles": ["admin"], "exp": now + 3600})

    assert validate_session(forged) is False
    assert decode_jwt_payload(forged) is None
    assert "admin" not in get_user_roles(forged)
    assert check_rbac_permission(forged, "admin") is False


def test_alg_none_jwt_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    now = int(time.time())
    token = _sign_jwt({"sub": "attacker", "roles": ["admin"], "exp": now + 3600}, "test-secret", alg="none")

    assert validate_session(token) is False
    assert check_rbac_permission(token, "admin") is False


def test_jwt_signed_with_wrong_secret_is_rejected(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    now = int(time.time())
    token = _sign_jwt({"sub": "attacker", "roles": ["admin"], "exp": now + 3600}, "other-secret")

    assert validate_session(token) is False
    assert check_rbac_permission(token, "admin") is False


def test_jwt_rejected_when_secret_unset(monkeypatch):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    now = int(time.time())
    token = _sign_jwt({"sub": "user_123", "roles": ["admin"], "exp": now + 3600}, "test-secret")

    assert validate_session(token) is False
    assert check_rbac_permission(token, "admin") is False


def test_middleware_rejects_backdoor_and_forged_admin_jwt(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    client = TestClient(app)
    now = int(time.time())
    forged = _make_mock_jwt({"sub": "attacker", "roles": ["admin"], "exp": now + 3600})
    alg_none = _sign_jwt({"roles": ["admin"], "exp": now + 3600}, "test-secret", alg="none")

    assert client.get("/api/config", headers={"Authorization": "Bearer dev_master_token"}).status_code == 401
    assert client.get("/api/config", headers={"Authorization": f"Bearer {forged}"}).status_code == 401
    assert client.get("/api/config", headers={"Authorization": f"Bearer {alg_none}"}).status_code == 401

    session = create_session()
    assert client.get("/api/config", headers={"Authorization": f"Bearer {session}"}).status_code == 200
