"""
Unit tests for FEAT-6: Heartbeat Pulse & Resumable Checkpoint Loop (backend/orchestrator.py).
"""

import os
import shutil
import tempfile
import unittest
from unittest.mock import patch, AsyncMock
from backend import database as db
from backend.orchestrator import AgentState, run_orchestration_pulse


class TestFeat6PulseEngine(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        db.init_db()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        db.init_db()

    def test_agent_state_checkpoint_serialization(self):
        """Verify AgentState serializes to dict and restores from task checkpoint."""
        state = AgentState(query="Build crypto trading bot", chat_id="session_101")
        state.steps = [
            {"agent": "research", "instructions": "Search BTC prices"},
            {"agent": "code", "instructions": "Calculate RSI indicator"}
        ]
        state.current_step_idx = 1
        state.results = [{"step": 0, "agent": "research", "output": "BTC is $65,000"}]

        # Create task in DB
        task_id = db.db_create_task(title="Crypto Trading Bot", status="IN_PROGRESS")
        saved = state.save_to_task(task_id)
        self.assertTrue(saved)

        # Reload state from task checkpoint
        restored = AgentState.load_from_task(task_id)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.query, "Build crypto trading bot")
        self.assertEqual(len(restored.steps), 2)
        self.assertEqual(restored.current_step_idx, 1)
        self.assertEqual(restored.results[0]["output"], "BTC is $65,000")

    @patch("backend.orchestrator.run_orchestration", new_callable=AsyncMock)
    def test_run_orchestration_pulse(self, mock_run_orch):
        """Verify pulse execution steps through plan and updates checkpoint."""
        mock_run_orch.return_value = {
            "response": "Pulse synthesis response",
            "steps": [{"agent": "research", "instructions": "Search news"}]
        }

        task_id = db.db_create_task(title="Pulse Test Task", status="TODO")
        import asyncio
        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(
            run_orchestration_pulse(task_id, api_key="dummy_key", model="dummy_model", max_steps_per_pulse=1)
        )
        loop.close()

        self.assertEqual(res["status"], "completed")
        self.assertEqual(res["task_id"], task_id)
        self.assertEqual(res["response"], "Pulse synthesis response")

        # Verify task in DB updated to DONE
        tasks = db.db_get_tasks()
        task = next(t for t in tasks if t["id"] == task_id)
        self.assertEqual(task["status"], "DONE")


if __name__ == "__main__":
    unittest.main()
