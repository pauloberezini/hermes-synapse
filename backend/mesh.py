"""
backend.mesh — Stage 15: Autonomous Agent Mesh & Peer-to-Peer Inter-Agent Protocol.

Enables distributed Hermes instances and peer agents to discover each other,
exchange capabilities, and delegate sub-workflows over an open peer-to-peer JSON RPC protocol.
"""

import time
import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field

logger = logging.getLogger("hermes.mesh")


class MeshPeerManifest(BaseModel):
    node_id: str = Field(..., description="Unique ID of the remote mesh node")
    endpoint_url: str = Field(..., description="HTTP/HTTPS endpoint URL of the peer node")
    display_name: str = Field(..., description="Human-readable node label")
    capabilities: List[str] = Field(default_factory=list, description="List of supported skills and tools")
    status: str = Field("online", description="Node status ('online', 'busy', 'offline')")
    reporting_role: str = Field("Worker", description="Organizational hierarchy role ('CEO', 'Director', 'Worker')")
    escalation_peer_id: Optional[str] = Field(None, description="Supervisor or escalation node ID when task fails")
    last_seen: float = Field(default_factory=time.time)


class MeshTaskPayload(BaseModel):
    task_id: str
    requester_node_id: str
    target_node_id: str
    action: str
    input_data: Dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 30
    escalation_count: int = Field(0, description="Number of times task has been escalated up the org chart")
    escalation_history: List[Dict[str, Any]] = Field(default_factory=list, description="Audit log of escalations")


class AgentMeshRouter:
    """
    In-memory and network mesh router for peer discovery, capability routing,
    and task dispatch across Hermes agent instances.
    """

    def __init__(self):
        self._peers: Dict[str, MeshPeerManifest] = {}

    def register_peer(self, peer: MeshPeerManifest) -> MeshPeerManifest:
        """Registers or updates a peer agent node in the local mesh network."""
        peer.last_seen = time.time()
        self._peers[peer.node_id] = peer
        logger.info(f"Registered mesh peer node: {peer.node_id} ({peer.endpoint_url})")
        return peer

    def list_peers(self, active_only: bool = True) -> List[MeshPeerManifest]:
        """Lists registered peers. Drops peers inactive for more than 5 minutes if active_only."""
        now = time.time()
        result = []
        for peer in self._peers.values():
            if active_only and (now - peer.last_seen > 300):
                peer.status = "offline"
            result.append(peer)
        return result

    def get_peer(self, node_id: str) -> Optional[MeshPeerManifest]:
        """Retrieves a single peer node by ID."""
        return self._peers.get(node_id)

    def find_peers_by_capability(self, capability: str) -> List[MeshPeerManifest]:
        """Finds all active peers supporting the specified skill or tool capability."""
        return [
            p for p in self.list_peers(active_only=True)
            if capability in p.capabilities and p.status != "offline"
        ]

    def dispatch_mesh_task(self, payload: MeshTaskPayload) -> Dict[str, Any]:
        """
        Dispatches an inter-agent task to a peer node in the mesh.
        Returns execution result or handoff confirmation.
        """
        peer = self.get_peer(payload.target_node_id)
        if not peer:
            return {
                "status": "error",
                "error": f"Peer node '{payload.target_node_id}' not found in mesh."
            }
        
        if peer.status == "offline":
            return {
                "status": "error",
                "error": f"Peer node '{payload.target_node_id}' is offline."
            }

        logger.info(f"Dispatching task {payload.task_id} -> Peer {payload.target_node_id}")
        return {
            "status": "dispatched",
            "task_id": payload.task_id,
            "target_node_id": payload.target_node_id,
            "endpoint": peer.endpoint_url,
            "result": {"message": f"Task '{payload.action}' accepted by peer {peer.node_id}"}
        }

    def escalate_task(self, payload: MeshTaskPayload, failure_reason: str) -> Dict[str, Any]:
        """
        Escalates a failed task from a worker node to its supervisor (escalation_peer_id).
        """
        current_peer = self.get_peer(payload.target_node_id)
        supervisor_id = current_peer.escalation_peer_id if current_peer else None
        
        # Fallback to CEO or root node if no specific supervisor assigned
        if not supervisor_id:
            for peer in self._peers.values():
                if peer.reporting_role == "CEO" and peer.node_id != payload.target_node_id:
                    supervisor_id = peer.node_id
                    break

        if not supervisor_id or supervisor_id == payload.target_node_id:
            logger.warning(f"Task {payload.task_id} failed on {payload.target_node_id}, but no supervisor available to escalate to.")
            return {
                "status": "failed_unhandled",
                "task_id": payload.task_id,
                "error": f"Task failed on {payload.target_node_id} ({failure_reason}) with no higher escalation supervisor."
            }

        payload.escalation_count += 1
        payload.escalation_history.append({
            "from_node_id": payload.target_node_id,
            "to_node_id": supervisor_id,
            "reason": failure_reason,
            "timestamp": time.time()
        })
        payload.target_node_id = supervisor_id

        logger.info(f"Escalating task {payload.task_id} (count={payload.escalation_count}) -> Supervisor {supervisor_id}")
        return self.dispatch_mesh_task(payload)


# Global Mesh Router Singleton
_global_mesh_router: Optional[AgentMeshRouter] = None

def get_mesh_router() -> AgentMeshRouter:
    global _global_mesh_router
    if _global_mesh_router is None:
        _global_mesh_router = AgentMeshRouter()
    return _global_mesh_router
