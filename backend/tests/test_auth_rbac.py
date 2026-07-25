"""
Unit tests for backend.auth package (Stage 13: OIDC JWT decoding & RBAC permission checks).
"""
import time
import base64
import json
import pytest
from backend.auth import (
    create_session,
    validate_session,
    decode_jwt_payload,
    get_user_roles,
    check_rbac_permission,
)


def _make_mock_jwt(payload: dict) -> str:
    header_b64 = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    payload_str = json.dumps(payload)
    payload_b64 = base64.urlsafe_b64encode(payload_str.encode("utf-8")).decode("utf-8").rstrip("=")
    signature_b64 = "mock_signature"
    return f"{header_b64}.{payload_b64}.{signature_b64}"


def test_local_session_admin_roles():
    token = create_session()
    assert validate_session(token) is True
    roles = get_user_roles(token)
    assert roles == ["admin"]
    assert check_rbac_permission(token, "admin") is True
    assert check_rbac_permission(token, "editor") is True


def test_jwt_payload_decoding_and_expiration():
    now = int(time.time())
    valid_payload = {"sub": "user_123", "roles": ["editor"], "exp": now + 3600}
    jwt_token = _make_mock_jwt(valid_payload)

    assert validate_session(jwt_token) is True
    roles = get_user_roles(jwt_token)
    assert "editor" in roles
    assert check_rbac_permission(jwt_token, "editor") is True
    assert check_rbac_permission(jwt_token, "admin") is False

    # Expired token
    expired_payload = {"sub": "user_123", "roles": ["admin"], "exp": now - 3600}
    expired_token = _make_mock_jwt(expired_payload)
    assert validate_session(expired_token) is False


def test_invalid_jwt_token_handling():
    invalid_token = "invalid.token.string"
    assert decode_jwt_payload(invalid_token) is None
    assert get_user_roles(invalid_token) == ["viewer"]
    assert check_rbac_permission(invalid_token, "admin") is False
