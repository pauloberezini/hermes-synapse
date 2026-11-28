"""OpenAPI MCP proxy must not call a third-party host by default."""
from pathlib import Path
from unittest.mock import patch

import pytest

from backend.mcp_openapi_proxy import (
    MISSING_OPENAPI_URL,
    require_openapi_url,
)

ROOT = Path(__file__).resolve().parents[2]


def test_require_openapi_url_fails_when_unset():
    with pytest.raises(SystemExit) as exc:
        require_openapi_url("")
    assert "OPENAPI_URL" in str(exc.value)
    assert "no default host" in str(exc.value)


def test_require_openapi_url_returns_explicit_url():
    assert (
        require_openapi_url("https://your-service.example/openapi.json")
        == "https://your-service.example/openapi.json"
    )


def test_get_token_does_not_fetch_without_token_url(monkeypatch):
    import backend.mcp_openapi_proxy as proxy

    monkeypatch.setattr(proxy, "AUTH_TOKEN_URL", "")
    monkeypatch.setattr(proxy, "AUTH_USERNAME", "user")
    monkeypatch.setattr(proxy, "AUTH_PASSWORD", "pass")
    monkeypatch.setattr(proxy, "STATIC_BEARER_TOKEN", "")
    monkeypatch.setattr(proxy, "token", "")
    with patch("backend.mcp_openapi_proxy.urllib.request.urlopen") as urlopen:
        assert proxy.get_token() == ""
        urlopen.assert_not_called()


def test_load_openapi_spec_does_not_fetch_when_url_missing(monkeypatch):
    import backend.mcp_openapi_proxy as proxy

    monkeypatch.setattr(proxy, "OPENAPI_URL", "")
    with patch("backend.mcp_openapi_proxy.urllib.request.urlopen") as urlopen:
        with pytest.raises(SystemExit) as exc:
            proxy.load_openapi_spec()
        urlopen.assert_not_called()
    assert str(exc.value) == MISSING_OPENAPI_URL


def test_repo_has_no_amvera_tech_host():
    hits = []
    skip_dirs = {".git", "node_modules", ".venv", "dist", ".vitepress"}
    for path in ROOT.rglob("*"):
        if any(part in skip_dirs for part in path.parts):
            continue
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        needle = "amvera" + ".tech"
        if needle in text.lower():
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []
