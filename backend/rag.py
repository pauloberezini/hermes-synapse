import os
import uuid
import logging
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models
from fastembed import TextEmbedding

logger = logging.getLogger("hermes.rag")

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = "hermes_memory"

# Lazy-loaded embedding model and Qdrant client
_embedding_model = None
_qdrant_client = None

def get_embedding_model() -> TextEmbedding:
    global _embedding_model
    if _embedding_model is None:
        logger.info("Initializing local fastembed TextEmbedding model (BAAI/bge-small-en-v1.5)...")
        # TextEmbedding downloads model if not cached and runs ONNX inference on CPU
        _embedding_model = TextEmbedding()
    return _embedding_model

def get_qdrant_client() -> QdrantClient:
    global _qdrant_client
    if _qdrant_client is None:
        logger.info(f"Connecting to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}...")
        _qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    return _qdrant_client

def raw_init_rag():
    """Initializes the RAG collection in Qdrant if it doesn't already exist."""
    try:
        client = get_qdrant_client()
        # Check if collection exists
        collections = client.get_collections().collections
        exists = any(c.name == COLLECTION_NAME for c in collections)
        
        if not exists:
            logger.info(f"Creating Qdrant collection: {COLLECTION_NAME}...")
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=384,  # BAAI/bge-small-en-v1.5 dimension is 384
                    distance=models.Distance.COSINE
                )
            )
            logger.info("Collection created successfully.")
        else:
            logger.info(f"Qdrant collection '{COLLECTION_NAME}' already exists.")
    except Exception as e:
        logger.error(f"Failed to initialize Qdrant/RAG: {e}")

def chunk_text(text: str, chunk_size: int = 600, overlap: int = 150) -> List[str]:
    """Helper to split document text into overlapping chunks for indexing."""
    chunks = []
    text = text.strip()
    if not text:
        return []
        
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        # If we reached the end of the text, break
        if end >= len(text):
            break
        start += chunk_size - overlap
    return chunks

def raw_index_document(doc_id: str, title: str, text: str,
                      source: str = "manual", note_path: str = "") -> bool:
    """Chunks the text, generates embeddings, and uploads them to Qdrant.
    
    Args:
        doc_id:    Stable unique ID for this document (re-indexing deletes old chunks first).
        title:     Human-readable display name.
        text:      Raw document text to embed.
        source:    Origin tag: 'obsidian' | 'upload' | 'manual'.
        note_path: Vault-relative path for Obsidian notes (e.g. 'Daily/2026-06-23.md').
    """
    try:
        client = get_qdrant_client()
        embedder = get_embedding_model()
        
        # Delete old chunks of this document first to avoid duplication on re-indexing
        delete_document(doc_id)
        
        chunks = chunk_text(text)
        if not chunks:
            return False
            
        logger.info(f"Indexing document '{title}' ({doc_id}) [{source}] into {len(chunks)} chunks...")
        
        # Generate embeddings in batch
        embeddings = list(embedder.embed(chunks))
        
        points = []
        for i, (chunk, vector) in enumerate(zip(chunks, embeddings)):
            point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{doc_id}_{i}"))
            points.append(
                models.PointStruct(
                    id=point_id,
                    vector=vector.tolist(),
                    payload={
                        "doc_id": doc_id,
                        "title": title,
                        "chunk_index": i,
                        "content": chunk,
                        "source": source,
                        "note_path": note_path,
                    }
                )
            )
            
        client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )
        logger.info(f"Successfully indexed document '{title}'.")
        return True
    except Exception as e:
        logger.error(f"Error indexing document '{title}': {e}")
        return False

def raw_search_memory(query: str, limit: int = 3, threshold: float = 0.7,
                      source_filter: str = "") -> List[Dict[str, Any]]:
    """Searches memory for relevant chunks and returns list of hits above the threshold.
    
    Args:
        source_filter: If set, only return results from this source ('obsidian', 'upload', 'manual').
    """
    try:
        client = get_qdrant_client()
        embedder = get_embedding_model()
        
        # Embed the query string
        query_vector = list(embedder.embed([query]))[0].tolist()
        
        logger.info(f"Searching memory for query: '{query}' (source_filter={source_filter or 'all'})...")
        
        # Build optional source filter
        query_filter = None
        if source_filter:
            query_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="source",
                        match=models.MatchValue(value=source_filter)
                    )
                ]
            )
        
        res = client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=query_filter,
            limit=limit,
            score_threshold=threshold
        )
        hits = res.points
        
        results = []
        for hit in hits:
            results.append({
                "score": hit.score,
                "title": hit.payload.get("title"),
                "doc_id": hit.payload.get("doc_id"),
                "content": hit.payload.get("content"),
                "source": hit.payload.get("source", "manual"),
                "note_path": hit.payload.get("note_path", ""),
            })
        logger.info(f"Found {len(results)} search results.")
        return results
    except Exception as e:
        logger.error(f"Error searching vector DB: {e}")
        return []

def raw_delete_document(doc_id: str) -> bool:
    """Deletes all vector points associated with a document ID."""
    try:
        client = get_qdrant_client()
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=models.Filter(
                must=[
                    models.FieldCondition(
                        key="doc_id",
                        match=models.MatchValue(value=doc_id)
                    )
                ]
            )
        )
        logger.info(f"Deleted vector index for document: {doc_id}")
        return True
    except Exception as e:
        logger.error(f"Error deleting document {doc_id}: {e}")
        return False

def list_documents(source_filter: str = "") -> List[Dict[str, str]]:
    """Queries Qdrant to list all unique documents indexed.
    
    Args:
        source_filter: If set, only list docs from this source ('obsidian', 'upload', 'manual').
    """
    try:
        client = get_qdrant_client()
        
        # Build optional filter
        scroll_filter = None
        if source_filter:
            scroll_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="source",
                        match=models.MatchValue(value=source_filter)
                    )
                ]
            )
        
        # Scroll through collection payload
        records, _ = client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=scroll_filter,
            limit=500,
            with_payload=True,
            with_vectors=False
        )
        
        # Deduplicate by doc_id
        seen_docs = {}
        for record in records:
            payload = record.payload
            doc_id = payload.get("doc_id")
            if doc_id and doc_id not in seen_docs:
                seen_docs[doc_id] = {
                    "id": doc_id,
                    "title": payload.get("title", "Untitled Note"),
                    "source": payload.get("source", "manual"),
                    "note_path": payload.get("note_path", ""),
                }
                
        return list(seen_docs.values())
    except Exception as e:
        logger.error(f"Error listing documents: {e}")
        return []

# ─── PLUGGABLE ADAPTERS ────────────────────────────────-----------------------

def init_rag():
    from backend.memory import get_memory_engine
    get_memory_engine().init_memory()

def index_document(doc_id: str, title: str, text: str,
                   source: str = "manual", note_path: str = "") -> bool:
    from backend.memory import get_memory_engine
    return get_memory_engine().index_document(doc_id, title, text, source, note_path)

def search_memory(query: str, limit: int = 3, threshold: float = 0.7,
                  source_filter: str = "") -> List[Dict[str, Any]]:
    from backend.memory import get_memory_engine
    return get_memory_engine().search_memory(query, limit, threshold, source_filter)

def delete_document(doc_id: str) -> bool:
    from backend.memory import get_memory_engine
    return get_memory_engine().delete_document(doc_id)

