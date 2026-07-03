import os
import pytest
import sqlite3
from unittest.mock import MagicMock, patch
from qdrant_client import QdrantClient
from qdrant_client.http import models

from backend import database
from backend import rag
from backend.tools import execute_tool

@pytest.fixture(autouse=True)
def setup_test_environment(tmp_path):
    # Overwrite SQLite path to temp DB
    original_db_path = database.DB_PATH
    original_db_dir = database.DB_DIR
    test_db = tmp_path / "test_hermes.db"
    database.DB_PATH = str(test_db)
    database.DB_DIR = str(tmp_path)
    database.init_db()

    # Spin up in-memory Qdrant client
    in_memory_client = QdrantClient(":memory:")
    in_memory_client.create_collection(
        collection_name=rag.COLLECTION_NAME,
        vectors_config=models.VectorParams(
            size=384,
            distance=models.Distance.COSINE
        )
    )
    
    mock_embedder = MagicMock()
    mock_embedder.embed.side_effect = lambda texts: [
        MagicMock(tolist=lambda: [0.1] * 384) 
        for text in texts
    ]

    with patch("backend.rag.get_qdrant_client", return_value=in_memory_client), \
         patch("backend.rag.get_embedding_model", return_value=mock_embedder):
        yield

    # Restore DB paths
    database.DB_PATH = original_db_path
    database.DB_DIR = original_db_dir


def test_sqlite_subagent_memory_crud():
    subagent_id = "test_tutor"
    
    # Initially empty
    assert database.db_get_subagent_memory(subagent_id) == {}
    
    # Save a fact
    database.db_save_subagent_memory(subagent_id, "vocabulary", "hola = hello")
    assert database.db_get_subagent_memory(subagent_id) == {"vocabulary": "hola = hello"}
    
    # Save another fact
    database.db_save_subagent_memory(subagent_id, "user_level", "A1")
    assert database.db_get_subagent_memory(subagent_id) == {
        "vocabulary": "hola = hello",
        "user_level": "A1"
    }
    
    # Update fact
    database.db_save_subagent_memory(subagent_id, "user_level", "A2")
    assert database.db_get_subagent_memory(subagent_id, "user_level") == {"user_level": "A2"}
    
    # Delete fact
    deleted = database.db_delete_subagent_memory(subagent_id, "vocabulary")
    assert deleted is True
    assert database.db_get_subagent_memory(subagent_id) == {"user_level": "A2"}


def test_subagent_memory_tools_execution():
    subagent_id = "dynamic_tutor_chat"
    
    # Call save_subagent_memory tool
    save_result = execute_tool(
        "save_subagent_memory",
        {"key": "lessons_progress", "value": "numbers completed"},
        chat_id=subagent_id
    )
    assert "success" in save_result
    
    # Retrieve via SQLite directly to verify
    db_mem = database.db_get_subagent_memory(subagent_id)
    assert db_mem == {"lessons_progress": "numbers completed"}
    
    # Call get_subagent_memory tool
    get_result = execute_tool(
        "get_subagent_memory",
        {"key": "lessons_progress"},
        chat_id=subagent_id
    )
    assert "numbers completed" in get_result
    
    # Verify RAG indexing via search
    hits = rag.search_memory("numbers completed", limit=1)
    assert len(hits) == 1
    assert hits[0]["doc_id"] == f"subagent_mem_{subagent_id}_lessons_progress"
    assert "numbers completed" in hits[0]["content"]
