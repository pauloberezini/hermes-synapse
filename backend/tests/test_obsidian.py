import pytest
import json
from unittest.mock import MagicMock, patch, AsyncMock
from qdrant_client import QdrantClient
from fastapi.testclient import TestClient

from backend import obsidian
from backend import rag
from backend.main import app
from backend.auth import active_sessions

# Setup mock Qdrant and Embedder just like in test_rag.py
@pytest.fixture(autouse=True)
def setup_mock_qdrant():
    in_memory_client = QdrantClient(":memory:")
    
    from qdrant_client.http import models
    in_memory_client.create_collection(
        collection_name=rag.COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=384,
            distance=models.Distance.COSINE
        )
    )
    
    mock_embedder = MagicMock()
    mock_embedder.embed.side_effect = lambda texts: [
        MagicMock(tolist=lambda: [0.01] * 384) 
        for text in texts
    ]
    
    with patch("backend.rag.get_qdrant_client", return_value=in_memory_client), \
         patch("backend.rag.get_embedding_model", return_value=mock_embedder):
        yield

# We will mock the httpx client methods
@pytest.fixture
def mock_http():
    with patch("backend.obsidian._client") as mock_client_func, \
         patch("httpx.AsyncClient") as mock_class:
        # Mock client instance returned by _client() context manager
        client_inst = AsyncMock()
        mock_client_func.return_value.__aenter__.return_value = client_inst
        
        # Mock client instance returned by httpx.AsyncClient() context manager (for create_note)
        class_inst = AsyncMock()
        mock_class.return_value.__aenter__.return_value = class_inst
        
        yield client_inst, class_inst

@pytest.mark.asyncio
async def test_is_reachable(mock_http):
    client_inst, _ = mock_http
    
    # 1. Reachable returns True on status < 500
    with patch("backend.obsidian._get_api_key", return_value="test-key"):
        mock_resp = MagicMock(status_code=200)
        client_inst.get.return_value = mock_resp
        assert await obsidian.is_reachable() is True
        
        # 2. Unreachable returns False on status >= 500
        mock_resp.status_code = 500
        assert await obsidian.is_reachable() is False
        
        # 3. Unreachable returns False on Exception
        client_inst.get.side_effect = Exception("Connection refused")
        assert await obsidian.is_reachable() is False

    # 4. Returns False if no API key configured
    with patch("backend.obsidian._get_api_key", return_value=None):
        assert await obsidian.is_reachable() is False

@pytest.mark.asyncio
async def test_list_notes(mock_http):
    client_inst, _ = mock_http
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = {
        "files": ["Daily/2026-06-23.md", "Ideas.md", "image.png", "Document.pdf"]
    }
    client_inst.get.return_value = mock_resp
    
    notes = await obsidian.list_notes()
    # Should only return markdown files
    assert notes == ["Daily/2026-06-23.md", "Ideas.md"]
    client_inst.get.assert_called_with(f"{obsidian._get_base_url()}/vault/")

@pytest.mark.asyncio
async def test_read_note(mock_http):
    client_inst, _ = mock_http
    mock_resp = MagicMock(status_code=200, text="# My Note\nContent")
    client_inst.get.return_value = mock_resp
    
    content = await obsidian.read_note("Ideas.md")
    assert content == "# My Note\nContent"
    client_inst.get.assert_called_with(f"{obsidian._get_base_url()}/vault/Ideas.md")

@pytest.mark.asyncio
async def test_create_note(mock_http):
    _, class_inst = mock_http
    mock_resp = MagicMock(status_code=200)
    class_inst.put.return_value = mock_resp
    
    success = await obsidian.create_note("Vexa/Test.md", "# Test")
    assert success is True
    class_inst.put.assert_called_once()

@pytest.mark.asyncio
async def test_search_notes(mock_http):
    client_inst, _ = mock_http
    mock_resp = MagicMock(status_code=200)
    mock_resp.json.return_value = [
        {
            "filename": "Ideas.md",
            "score": 0.9,
            "matches": [{"context": "Some matching text in Ideas"}]
        }
    ]
    client_inst.post.return_value = mock_resp
    
    results = await obsidian.search_notes("test query")
    assert len(results) == 1
    assert results[0]["filename"] == "Ideas.md"
    assert results[0]["excerpt"] == "Some matching text in Ideas"

@pytest.mark.asyncio
async def test_sync_vault_to_rag(mock_http):
    client_inst, _ = mock_http
    
    # Mock listing notes
    mock_list_resp = MagicMock(status_code=200)
    mock_list_resp.json.return_value = {"files": ["Note1.md", "Note2.md"]}
    
    # Mock reading note
    mock_read_resp1 = MagicMock(status_code=200, text="This is the content of Note 1.")
    mock_read_resp2 = MagicMock(status_code=200, text="This is the content of Note 2.")
    
    client_inst.get.side_effect = [mock_list_resp, mock_read_resp1, mock_read_resp2]
    
    result = await obsidian.sync_vault_to_rag()
    assert result["indexed"] == 2
    assert result["skipped"] == 0
    assert result["errors"] == 0
    
    # Verify indexed in RAG database
    docs = rag.list_documents(source_filter="obsidian")
    assert len(docs) == 2
    assert any(d["title"] == "Note1" for d in docs)
    assert any(d["title"] == "Note2" for d in docs)

def test_obsidian_tools():
    from backend.tools import search_obsidian, read_obsidian_note, create_obsidian_note, sync_obsidian_vault
    
    # 1. Test read_obsidian_note tool
    with patch("backend.obsidian.read_note", new_callable=AsyncMock) as mock_read:
        mock_read.return_value = "Note content"
        res = read_obsidian_note("Path.md")
        assert "Note content" in res
        mock_read.assert_called_with("Path.md")
        
    # 2. Test create_obsidian_note tool
    with patch("backend.obsidian.create_note", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = True
        res = create_obsidian_note("Title", "Content", "Folder")
        assert "created" in res
        
    # 3. Test sync_obsidian_vault tool
    with patch("backend.obsidian.sync_vault_to_rag", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = {"indexed": 5, "message": "Synced"}
        res = sync_obsidian_vault()
        assert "Synced" in res

def test_api_endpoints():
    test_client = TestClient(app)
    test_client.headers = {"Authorization": "Bearer test-token"}
    active_sessions.add("test-token")
    
    # 1. Test status endpoint (reachable)
    with patch("backend.obsidian.is_reachable", new_callable=AsyncMock) as mock_reach, \
         patch("backend.obsidian._get_api_key", return_value="configured"):
        mock_reach.return_value = True
        resp = test_client.get("/api/obsidian/status")
        assert resp.status_code == 200
        assert resp.json()["reachable"] is True
        
    # 2. Test notes listing endpoint
    with patch("backend.obsidian.list_notes", new_callable=AsyncMock) as mock_list:
        mock_list.return_value = ["Daily.md", "Ideas.md"]
        resp = test_client.get("/api/obsidian/notes")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2
        assert resp.json()["notes"] == ["Daily.md", "Ideas.md"]
        
    # 3. Test sync POST endpoint
    with patch("backend.obsidian.sync_vault_to_rag", new_callable=AsyncMock) as mock_sync:
        mock_sync.return_value = {"indexed": 10, "message": "Success"}
        resp = test_client.post("/api/obsidian/sync")
        assert resp.status_code == 200
        assert resp.json()["indexed"] == 10
        
    # 4. Test search endpoint
    rag.index_document("obsidian_1", "Secret Vault Note", "Password is admin123", source="obsidian", note_path="Secret.md")
    resp = test_client.get("/api/obsidian/search?q=Secret")
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) > 0
    assert results[0]["title"] == "Secret Vault Note"
