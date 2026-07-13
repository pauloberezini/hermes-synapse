import os
import uuid
import logging
import json
import re
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod

logger = logging.getLogger("hermes.memory")

# ---------------------------------------------------------------------------
# Base Interface
# ---------------------------------------------------------------------------

class MemoryEngine(ABC):
    """Abstract interface for pluggable memory backends."""

    @abstractmethod
    def init_memory(self) -> None:
        """Initialize collection/schema details."""
        pass

    @abstractmethod
    def index_document(self, doc_id: str, title: str, text: str,
                       source: str = "manual", note_path: str = "") -> bool:
        """Index a document into the memory store."""
        pass

    @abstractmethod
    def search_memory(self, query: str, limit: int = 3, threshold: float = 0.7,
                      source_filter: str = "") -> List[Dict[str, Any]]:
        """Search memory for relevant chunks."""
        pass

    @abstractmethod
    def delete_document(self, doc_id: str) -> bool:
        """Delete all records/vectors associated with a document ID."""
        pass

    @abstractmethod
    def clear_memory(self) -> bool:
        """Clear all records/vectors in memory."""
        pass


# ---------------------------------------------------------------------------
# 1. Qdrant Flat Vector Memory Engine (Default)
# ---------------------------------------------------------------------------

class QdrantMemoryEngine(MemoryEngine):
    """Encapsulates standard vector RAG search using Qdrant and fastembed."""

    def init_memory(self) -> None:
        from backend.rag import raw_init_rag
        raw_init_rag()

    def index_document(self, doc_id: str, title: str, text: str,
                       source: str = "manual", note_path: str = "") -> bool:
        from backend.rag import raw_index_document
        return raw_index_document(doc_id, title, text, source, note_path)

    def search_memory(self, query: str, limit: int = 3, threshold: float = 0.7,
                      source_filter: str = "") -> List[Dict[str, Any]]:
        from backend.rag import raw_search_memory
        return raw_search_memory(query, limit, threshold, source_filter)

    def delete_document(self, doc_id: str) -> bool:
        from backend.rag import raw_delete_document
        return raw_delete_document(doc_id)


    def clear_memory(self) -> bool:
        try:
            from backend.rag import get_qdrant_client, COLLECTION_NAME
            client = get_qdrant_client()
            client.delete_collection(collection_name=COLLECTION_NAME)
            self.init_memory()
            logger.info("Cleared Qdrant flat vector memory.")
            return True
        except Exception as e:
            logger.error(f"Error clearing Qdrant collection: {e}")
            return False


# ---------------------------------------------------------------------------
# 2. SQLite/Postgres GraphRAG Memory Engine
# ---------------------------------------------------------------------------

class SQLiteGraphMemoryEngine(MemoryEngine):
    """Local GraphRAG implementation. Uses Qdrant flat vector indexing combined

    with entity-relationship extraction stored in the relational database.
    """

    def __init__(self) -> None:
        self._qdrant_engine = QdrantMemoryEngine()

    def init_memory(self) -> None:
        self._qdrant_engine.init_memory()

    def index_document(self, doc_id: str, title: str, text: str,
                       source: str = "manual", note_path: str = "") -> bool:
        # 1. Index flat vectors first
        success = self._qdrant_engine.index_document(doc_id, title, text, source, note_path)
        if not success:
            return False

        # 2. Clear old graph elements for this document to avoid duplicates on re-index
        from backend.database import db_clear_graph, db_save_graph_node, db_save_graph_edge
        db_clear_graph(doc_id)

        # 3. Extract knowledge graph elements (using LLM or heuristic fallback)
        logger.info(f"Extracting graph elements from document '{title}' ({doc_id})...")
        graph_data = self._extract_graph_elements(text)
        
        # 4. Save to relational database
        for node in graph_data.get("entities", []):
            node_name = node.get("name", "").strip()
            if not node_name:
                continue
            # Create stable UUID for node based on its name
            node_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, node_name.lower()))
            db_save_graph_node(node_id, node_name, node.get("type", "concept"), node.get("description", ""), doc_id)
            
        for edge in graph_data.get("relationships", []):
            src = edge.get("source", "").strip()
            tgt = edge.get("target", "").strip()
            if not src or not tgt:
                continue
            db_save_graph_edge(src, tgt, edge.get("description", "related to"), 1.0, doc_id)

        logger.info(f"Completed GraphRAG indexing for document: {title}")
        return True

    def search_memory(self, query: str, limit: int = 3, threshold: float = 0.7,
                      source_filter: str = "") -> List[Dict[str, Any]]:
        # 1. Fetch flat vector results
        vector_results = self._qdrant_engine.search_memory(query, limit, threshold, source_filter)
        if not vector_results:
            return []

        # 2. Retrieve entities from database
        from backend.database import db_get_graph_nodes, db_get_graph_edges
        all_nodes = db_get_graph_nodes()
        all_edges = db_get_graph_edges()

        # Build keywords list to match query
        query_words = set(re.findall(r'\b\w+\b', query.lower()))
        matched_names = set()
        
        for node in all_nodes:
            node_lower = node["name"].lower()
            if node_lower in query.lower() or any(w in node_lower for w in query_words if len(w) > 3):
                matched_names.add(node["name"])

        # 3. Retrieve relevant subgraph edges
        subgraph_edges = []
        for edge in all_edges:
            if edge["source"] in matched_names or edge["target"] in matched_names:
                subgraph_edges.append(edge)

        # Limit to top 15 edges to avoid context clutter
        subgraph_edges = subgraph_edges[:15]

        if subgraph_edges:
            graph_context = "\n=== KNOWLEDGE GRAPH RELATIONSHIPS ===\n"
            for edge in subgraph_edges:
                graph_context += f"- [{edge['source']}] ({edge['description']}) -> [{edge['target']}]\n"
            # Append context to the first (highest score) flat text chunk
            vector_results[0]["content"] += graph_context

        return vector_results

    def delete_document(self, doc_id: str) -> bool:
        self._qdrant_engine.delete_document(doc_id)
        from backend.database import db_clear_graph
        db_clear_graph(doc_id)
        return True

    def clear_memory(self) -> bool:
        self._qdrant_engine.clear_memory()
        from backend.database import db_clear_graph
        db_clear_graph()
        return True

    def _extract_graph_elements(self, text: str) -> Dict[str, Any]:
        api_key = os.getenv("OPENROUTER_API_KEY")
        api_base = os.getenv("LLM_API_BASE", "https://openrouter.ai/api/v1")
        model = os.getenv("LLM_MODEL", "google/gemini-2.5-flash")
        
        if not api_key:
            return self._heuristic_extractor(text)

        prompt = (
            "You are a knowledge graph extractor. Given the following text chunk, extract a list of entities "
            "(their name, type, and short description) and a list of relationships (source entity, target entity, "
            "short description).\n"
            "Respond ONLY with a valid JSON object matching this schema:\n"
            "{\n"
            '  "entities": [{"name": "entity name", "type": "person/organization/concept/etc", "description": "short description"}],\n'
            '  "relationships": [{"source": "entity name", "target": "entity name", "description": "how they are related"}]\n'
            "}\n"
            "Do not include any Markdown tags (like ```json), preamble, or comments.\n\n"
            f"Text to extract from:\n{text}"
        )
        
        try:
            import httpx
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.1,
                "max_tokens": 1000
            }
            with httpx.Client(timeout=15.0) as client:
                resp = client.post(f"{api_base}/chat/completions", json=payload, headers=headers)
            if resp.status_code == 200:
                content = resp.json()["choices"][0]["message"]["content"].strip()
                if content.startswith("```"):
                    content = re.sub(r"^```[a-zA-Z]*\n", "", content)
                    content = re.sub(r"\n```$", "", content)
                return json.loads(content)
        except Exception as exc:
            logger.warning("LLM graph extraction failed: %s. Falling back to heuristic extractor.", exc)
        
        return self._heuristic_extractor(text)

    def _heuristic_extractor(self, text: str) -> Dict[str, Any]:
        # Regex to find Capitalized Phrases (e.g. "Bitcoin", "Stark Industries")
        candidates = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', text)
        entities_names = list(set(c for c in candidates if len(c) > 2))
        
        entities = []
        for name in entities_names:
            entities.append({
                "name": name,
                "type": "concept",
                "description": f"Heuristically extracted entity from document."
            })
            
        relationships = []
        for i in range(len(entities_names) - 1):
            relationships.append({
                "source": entities_names[i],
                "target": entities_names[i+1],
                "description": "mentioned in same context"
            })
            
        return {"entities": entities, "relationships": relationships}


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_memory_engine() -> MemoryEngine:
    """Return the configured MemoryEngine implementation."""
    engine_name = os.getenv("MEMORY_ENGINE", "qdrant").strip().lower()
    if engine_name == "graph":
        logger.info("Memory engine: using SQLiteGraphMemoryEngine (Local GraphRAG)")
        return SQLiteGraphMemoryEngine()
    logger.info("Memory engine: using QdrantMemoryEngine (Flat Vectors)")
    return QdrantMemoryEngine()
