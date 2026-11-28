"""Backend must pass QDRANT_API_KEY through to the Qdrant client."""
from unittest.mock import patch

import backend.rag as rag


def test_get_qdrant_client_forwards_api_key(monkeypatch):
    monkeypatch.setenv("QDRANT_API_KEY", "pilot-qdrant-key")
    rag._qdrant_client = None
    with patch("backend.rag.QdrantClient") as client_cls:
        rag.get_qdrant_client()
        kwargs = client_cls.call_args.kwargs
        assert kwargs["api_key"] == "pilot-qdrant-key"
        assert kwargs["https"] is False
        assert kwargs["host"] == rag.QDRANT_HOST
        assert kwargs["port"] == rag.QDRANT_PORT
    rag._qdrant_client = None


def test_get_qdrant_client_https_opt_in(monkeypatch):
    monkeypatch.setenv("QDRANT_API_KEY", "pilot-qdrant-key")
    monkeypatch.setenv("QDRANT_HTTPS", "true")
    rag._qdrant_client = None
    with patch("backend.rag.QdrantClient") as client_cls:
        rag.get_qdrant_client()
        assert client_cls.call_args.kwargs["https"] is True
    rag._qdrant_client = None


def test_get_qdrant_client_omits_empty_api_key(monkeypatch):
    monkeypatch.delenv("QDRANT_API_KEY", raising=False)
    rag._qdrant_client = None
    with patch("backend.rag.QdrantClient") as client_cls:
        rag.get_qdrant_client()
        assert client_cls.call_args.kwargs["api_key"] is None
        assert client_cls.call_args.kwargs["https"] is False
    rag._qdrant_client = None
