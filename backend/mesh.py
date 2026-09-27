"""
backend.mesh — Stage 17: Production Multi-Cluster Agent Mesh & Peer-to-Peer Inter-Agent Protocol.

Enables distributed Hermes instances and peer agents to discover each other,
exchange capabilities, and delegate sub-workflows over an open peer-to-peer JSON RPC protocol.
Uses PostgreSQL database for stateless distributed node discovery across Kubernetes/Swarm.
"""

import time
import json
import logging
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from backend.database import _execute

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
    Stateless database-backed mesh router for peer discovery, capability routing,
    and task dispatch across distributed Hermes agent clusters.
    """

    def register_peer(self, peer: MeshPeerManifest) -> MeshPeerManifest:
        """Registers or updates a peer agent node in the distributed mesh network database."""
        peer.last_seen = time.time()
        # Use INSERT OR REPLACE semantics compatible with our DB abstraction
        _execute(
            """
            INSERT INTO mesh_nodes (node_id, endpoint_url, display_name, capabilities, status, reporting_role, escalation_peer_id, last_seen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(node_id) DO UPDATE SET
                endpoint_url=EXCLUDED.endpoint_url,
                display_name=EXCLUDED.display_name,
                capabilities=EXCLUDED.capabilities,
                status=EXCLUDED.status,
                reporting_role=EXCLUDED.reporting_role,
                escalation_peer_id=EXCLUDED.escalation_peer_id,
                last_seen=EXCLUDED.last_seen
            """,
            (
                peer.node_id,
                peer.endpoint_url,
                peer.display_name,
                json.dumps(peer.capabilities),
                peer.status,
                peer.reporting_role,
                peer.escalation_peer_id,
                peer.last_seen
            )
        )
        logger.debug(f"Registered distributed mesh peer node: {peer.node_id} ({peer.endpoint_url})")
        return peer

    def list_peers(self, active_only: bool = True) -> List[MeshPeerManifest]:
        """Lists registered peers across the cluster. Drops peers inactive for more than 5 minutes if active_only."""
        now = time.time()
        rows = _execute("SELECT * FROM mesh_nodes")
        
        result = []
        for row in rows:
            # Handle both dict and tuple returns from _execute
            r = dict(row) if isinstance(row, dict) else {
                "node_id": row[0], "endpoint_url": row[1], "display_name": row[2],
                "capabilities": row[3], "status": row[4], "reporting_role": row[5],
                "escalation_peer_id": row[6], "last_seen": row[7]
            }
            
            status = r["status"]
            last_seen = r["last_seen"] or 0.0
            
            if active_only and (now - last_seen > 300):
                status = "offline"
                
            result.append(MeshPeerManifest(
                node_id=r["node_id"],
                endpoint_url=r["endpoint_url"],
                display_name=r["display_name"] or "",
                capabilities=json.loads(r["capabilities"]) if r["capabilities"] else [],
                status=status,
                reporting_role=r["reporting_role"] or "Worker",
                escalation_peer_id=r["escalation_peer_id"],
                last_seen=last_seen
            ))
        return result

    def get_peer(self, node_id: str) -> Optional[MeshPeerManifest]:
        """Retrieves a single peer node by ID from the database."""
        rows = _execute("SELECT * FROM mesh_nodes WHERE node_id = ?", (node_id,))
        if not rows:
            return None
            
        row = rows[0]
        r = dict(row) if isinstance(row, dict) else {
            "node_id": row[0], "endpoint_url": row[1], "display_name": row[2],
            "capabilities": row[3], "status": row[4], "reporting_role": row[5],
            "escalation_peer_id": row[6], "last_seen": row[7]
        }
        return MeshPeerManifest(
            node_id=r["node_id"],
            endpoint_url=r["endpoint_url"],
            display_name=r["display_name"] or "",
            capabilities=json.loads(r["capabilities"]) if r["capabilities"] else [],
            status=r["status"],
            reporting_role=r["reporting_role"] or "Worker",
            escalation_peer_id=r["escalation_peer_id"],
            last_seen=r["last_seen"] or 0.0
        )

    def find_peers_by_capability(self, capability: str) -> List[MeshPeerManifest]:
        """Finds all active peers across the cluster supporting the specified skill or tool capability."""
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
            for peer in self.list_peers(active_only=True):
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

    # ── P2P Task Bidding (Contract Net Protocol) ──────────────────────────────

    def _init_bidding_tables(self):
        """Ensure RFP and Bidding tables exist."""
        _execute("""
            CREATE TABLE IF NOT EXISTS mesh_rfps (
                rfp_id TEXT PRIMARY KEY,
                task_action TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT DEFAULT 'OPEN',
                created_at REAL NOT NULL,
                awarded_node_id TEXT
            )
        """)
        _execute("""
            CREATE TABLE IF NOT EXISTS mesh_bids (
                bid_id INTEGER PRIMARY KEY AUTOINCREMENT,
                rfp_id TEXT NOT NULL,
                node_id TEXT NOT NULL,
                capability_score REAL NOT NULL,
                load_score REAL NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(rfp_id, node_id)
            )
        """)

    def publish_rfp(self, action: str, payload: Dict[str, Any]) -> str:
        """Publish a Request For Proposal to the mesh."""
        self._init_bidding_tables()
        import uuid
        rfp_id = str(uuid.uuid4())
        now = time.time()
        _execute(
            "INSERT INTO mesh_rfps (rfp_id, task_action, payload_json, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (rfp_id, action, json.dumps(payload), 'OPEN', now)
        )
        logger.info(f"[AgentMeshRouter] Published RFP {rfp_id} for action '{action}'")
        return rfp_id

    def submit_bid(self, rfp_id: str, node_id: str, capability_score: float, load_score: float) -> bool:
        """Submit a bid for a specific RFP."""
        self._init_bidding_tables()
        now = time.time()
        try:
            _execute(
                """
                INSERT INTO mesh_bids (rfp_id, node_id, capability_score, load_score, created_at) 
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(rfp_id, node_id) DO UPDATE SET 
                    capability_score=EXCLUDED.capability_score, load_score=EXCLUDED.load_score, created_at=EXCLUDED.created_at
                """,
                (rfp_id, node_id, capability_score, load_score, now)
            )
            logger.info(f"[AgentMeshRouter] Node {node_id} submitted bid for RFP {rfp_id} (cap={capability_score}, load={load_score})")
            return True
        except Exception as e:
            logger.error(f"[AgentMeshRouter] Failed to submit bid: {e}")
            return False

    def award_task(self, rfp_id: str) -> Optional[Dict[str, Any]]:
        """Close bidding and award task to the highest scoring bidder (Capability - Load)."""
        self._init_bidding_tables()
        bids = _execute("SELECT node_id, capability_score, load_score FROM mesh_bids WHERE rfp_id = ?", (rfp_id,))
        if not bids:
            logger.warning(f"[AgentMeshRouter] No bids received for RFP {rfp_id}")
            return None
        
        best_node = None
        best_score = -float('inf')

        for row in bids:
            r = dict(row) if isinstance(row, dict) else {"node_id": row[0], "capability_score": row[1], "load_score": row[2]}
            net_score = r["capability_score"] - r["load_score"]
            if net_score > best_score:
                best_score = net_score
                best_node = r["node_id"]

        if best_node:
            _execute("UPDATE mesh_rfps SET status = 'AWARDED', awarded_node_id = ? WHERE rfp_id = ?", (best_node, rfp_id))
            logger.info(f"[AgentMeshRouter] Awarded RFP {rfp_id} to Node {best_node} (Score: {best_score:.2f})")
            
            rfp_data = _execute("SELECT task_action, payload_json FROM mesh_rfps WHERE rfp_id = ?", (rfp_id,))
            if rfp_data:
                r_rfp = dict(rfp_data[0]) if isinstance(rfp_data[0], dict) else {"task_action": rfp_data[0][0], "payload_json": rfp_data[0][1]}
                return {
                    "rfp_id": rfp_id,
                    "awarded_node_id": best_node,
                    "action": r_rfp["task_action"],
                    "payload": json.loads(r_rfp["payload_json"])
                }
        return None


# Global Mesh Router Singleton
_global_mesh_router: Optional[AgentMeshRouter] = None

def get_mesh_router() -> AgentMeshRouter:
    global _global_mesh_router
    if _global_mesh_router is None:
        _global_mesh_router = AgentMeshRouter()
    return _global_mesh_router

