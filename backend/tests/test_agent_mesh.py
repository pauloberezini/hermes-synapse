"""
Unit tests for Stage 15 Autonomous Agent Mesh & Peer-to-Peer Protocol.
"""
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.auth import create_session
from backend.mesh import get_mesh_router, MeshPeerManifest, MeshTaskPayload

client = TestClient(app)


def test_agent_mesh_router_unit():
    router = get_mesh_router()
    peer1 = MeshPeerManifest(
        node_id="node_alpha",
        endpoint_url="http://localhost:9120",
        display_name="Alpha Node",
        capabilities=["web_search", "python_sandbox"],
        status="online"
    )
    router.register_peer(peer1)

    assert router.get_peer("node_alpha") is not None
    peers_with_web = router.find_peers_by_capability("web_search")
    assert len(peers_with_web) == 1
    assert peers_with_web[0].node_id == "node_alpha"

    task = MeshTaskPayload(
        task_id="task_001",
        requester_node_id="local_root",
        target_node_id="node_alpha",
        action="search",
        input_data={"query": "quantum computing"}
    )
    dispatch_res = router.dispatch_mesh_task(task)
    assert dispatch_res["status"] == "dispatched"


def test_agent_mesh_api_endpoints():
    token = create_session()
    headers = {"Authorization": f"Bearer {token}"}

    # Register via API
    peer_payload = {
        "node_id": "node_beta",
        "endpoint_url": "http://192.168.1.50:9119",
        "display_name": "Beta Node",
        "capabilities": ["bcm", "obsidian_rag"],
        "status": "online"
    }
    reg_res = client.post("/api/mesh/peers/register", json=peer_payload, headers=headers)
    assert reg_res.status_code == 200
    assert reg_res.json()["status"] == "success"

    # List peers via API
    list_res = client.get("/api/mesh/peers", headers=headers)
    assert list_res.status_code == 200
    data = list_res.json()
    assert data["status"] == "success"
    assert any(p["node_id"] == "node_beta" for p in data["peers"])

    # Dispatch task via API
    dispatch_payload = {
        "task_id": "task_002",
        "requester_node_id": "local_root",
        "target_node_id": "node_beta",
        "action": "execute_trade_check",
        "input_data": {"symbol": "EURUSD"}
    }
    disp_res = client.post("/api/mesh/dispatch", json=dispatch_payload, headers=headers)
    assert disp_res.status_code == 200
    assert disp_res.json()["status"] == "dispatched"
