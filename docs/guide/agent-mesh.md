# 🕸️ P2P Agent Mesh & Hermes Python SDK

Hermes Synapse includes a decentralized **Peer-to-Peer Agent Mesh** allowing distinct agent nodes to discover each other, delegate subtasks, and share vector memory.

---

## 🐍 1. Hermes Python SDK

The `hermes_sdk` package provides a simple interface for building custom agent nodes:

```python
from hermes_sdk import HermesClient

client = HermesClient(base_url="http://localhost:8000")

# Register custom subagent
agent = client.register_subagent(
    id="osint_researcher",
    name="OSINT Analyst",
    system_prompt="You gather open source intelligence from verified sources.",
    skills=["web_search", "python_sandbox"]
)

# Dispatch query to mesh
response = client.send_query("Search latest news on space exploration")
print(response)
```

---

## 🧠 2. Vector RAG Memory Engine

Agents automatically store context and query embeddings in Qdrant & SQLite graph stores:
- Graph node/edge relationships (`graph_nodes`, `graph_edges`).
- Subagent memory logs and semantic recall.

---

## 🎥 Video Tutorial

Watch how to connect custom agents using the Hermes Python SDK:

<YouTube id="dQw4w9WgXcQ" title="Building Custom Agents with Hermes SDK" />
