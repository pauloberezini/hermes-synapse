"""
Unit tests for Phase 2 Paperclip Features:
  - FEAT-4: Org Chart Escalation Routing (backend/mesh.py)
  - FEAT-5: Atomic Task Engine & Checkout Locks (backend/database.py)
"""

import os
import shutil
import tempfile
import unittest
from backend import database as db
from backend.mesh import AgentMeshRouter, MeshPeerManifest, MeshTaskPayload


class TestPhase2TaskAndMesh(unittest.TestCase):

    def setUp(self):
        self.orig_db_path = db.DB_PATH
        self.orig_db_dir = db.DB_DIR
        self.test_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.test_dir, "test_phase2.db")
        db.DB_PATH = self.test_db_path
        db.DB_DIR = self.test_dir
        db.init_db()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        db.DB_PATH = self.orig_db_path
        db.DB_DIR = self.orig_db_dir
        db.init_db()

    def test_mesh_escalation_routing(self):
        """Verify FEAT-4: Escalating a failed task to supervisor or CEO node."""
        router = AgentMeshRouter()

        ceo_node = MeshPeerManifest(
            node_id="ceo_node",
            endpoint_url="http://localhost:8000",
            display_name="CEO Orchestrator",
            capabilities=["all"],
            reporting_role="CEO"
        )
        worker_node = MeshPeerManifest(
            node_id="worker_node",
            endpoint_url="http://localhost:8001",
            display_name="Worker Agent",
            capabilities=["python_sandbox"],
            reporting_role="Worker",
            escalation_peer_id="ceo_node"
        )

        router.register_peer(ceo_node)
        router.register_peer(worker_node)

        payload = MeshTaskPayload(
            task_id="task_101",
            requester_node_id="client_1",
            target_node_id="worker_node",
            action="execute_code",
            input_data={"script": "print('hello')"}
        )

        # Escalate failed task
        res = router.escalate_task(payload, failure_reason="Script execution syntax error 3x")
        self.assertEqual(res["status"], "dispatched")
        self.assertEqual(res["target_node_id"], "ceo_node")
        self.assertEqual(payload.escalation_count, 1)
        self.assertEqual(len(payload.escalation_history), 1)
        self.assertEqual(payload.escalation_history[0]["from_node_id"], "worker_node")
        self.assertEqual(payload.escalation_history[0]["to_node_id"], "ceo_node")

    def test_task_engine_lifecycle_and_atomic_checkout(self):
        """Verify FEAT-5: Task creation, retrieval, atomic checkout locking, and updates."""
        task_id = db.db_create_task(
            title="Implement REST API Endpoint",
            description="Build /api/tasks endpoint for Paperclip engine",
            status="BACKLOG",
            assigned_agent_id="code_dev"
        )
        self.assertGreater(task_id, 0)

        tasks = db.db_get_tasks(status="BACKLOG")
        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["title"], "Implement REST API Endpoint")

        # Agent 1 checks out task
        checkout_res = db.db_checkout_task(task_id, agent_id="agent_alpha", lock_duration_seconds=300)
        self.assertEqual(checkout_res["status"], "success")
        self.assertEqual(checkout_res["assigned_agent_id"], "agent_alpha")

        # Task is now IN_PROGRESS
        in_prog_tasks = db.db_get_tasks(status="IN_PROGRESS")
        self.assertEqual(len(in_prog_tasks), 1)

        # Agent 2 tries to checkout locked task -> returns status "locked"
        lock_res = db.db_checkout_task(task_id, agent_id="agent_beta", lock_duration_seconds=300)
        self.assertEqual(lock_res["status"], "locked")

        # Update task status to DONE
        updated = db.db_update_task(task_id, status="DONE")
        self.assertTrue(updated)

        done_tasks = db.db_get_tasks(status="DONE")
        self.assertEqual(len(done_tasks), 1)

        # Delete task
        deleted = db.db_delete_task(task_id)
        self.assertTrue(deleted)
        self.assertEqual(len(db.db_get_tasks()), 0)


if __name__ == "__main__":
    unittest.main()
