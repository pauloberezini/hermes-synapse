"""
Unit tests for Paperclip-inspired Governance Module (backend/governance.py and backend/presets.py).
Uses standard unittest library for zero-dependency execution.
"""

import os
import shutil
import tempfile
import unittest
from backend import database as db
from backend.governance import BudgetGuard, BudgetExceededError, ApprovalQueue
from backend.presets import list_presets, load_preset


class TestGovernanceModule(unittest.TestCase):

    def setUp(self):
        self.orig_db_path = db.DB_PATH
        self.orig_db_dir = db.DB_DIR
        self.test_dir = tempfile.mkdtemp()
        self.test_db_path = os.path.join(self.test_dir, "test_governance.db")
        db.DB_PATH = self.test_db_path
        db.DB_DIR = self.test_dir
        db.init_db()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)
        db.DB_PATH = self.orig_db_path
        db.DB_DIR = self.orig_db_dir
        db.init_db()

    def test_budget_guard_under_limit(self):
        """Verify BudgetGuard allows execution when spend is below cap."""
        session_id = "test_session_1"
        with db._get_conn() as conn:
            conn.cursor().execute(
                "INSERT INTO session_metadata (session_id, title, daily_budget_usd) VALUES (?, ?, ?)",
                (session_id, "Test Session", 5.0),
            )
            conn.commit()

        # Checking estimated $0.05 spend should pass without raising
        BudgetGuard.check(session_id, estimated_cost_usd=0.05)

    def test_budget_guard_exceeded(self):
        """Verify BudgetGuard raises BudgetExceededError when cap is hit."""
        session_id = "test_session_2"
        with db._get_conn() as conn:
            conn.cursor().execute(
                "INSERT INTO session_metadata (session_id, title, daily_budget_usd) VALUES (?, ?, ?)",
                (session_id, "Test Session", 0.10),
            )
            conn.cursor().execute(
                "INSERT INTO messages (session_id, role, content, cost_usd) VALUES (?, ?, ?, ?)",
                (session_id, "assistant", "Spent message", 0.09),
            )
            conn.commit()

        with self.assertRaises(BudgetExceededError):
            BudgetGuard.check(session_id, estimated_cost_usd=0.02)

    def test_approval_queue_lifecycle(self):
        """Verify requesting, counting, and resolving human approval requests."""
        req_id = ApprovalQueue.request_approval(
            agent_id="code_agent",
            action_name="execute_shell",
            payload={"command": "rm -rf /tmp/test"},
            description="Clean temp files",
        )
        self.assertGreater(req_id, 0)
        self.assertEqual(ApprovalQueue.count_pending(), 1)

        pending = ApprovalQueue.get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["agent_id"], "code_agent")
        self.assertEqual(pending[0]["action_name"], "execute_shell")

        # Approve request
        ok = ApprovalQueue.resolve(req_id, decision="APPROVED", resolver_note="Verified safe")
        self.assertTrue(ok)
        self.assertEqual(ApprovalQueue.count_pending(), 0)
        self.assertEqual(ApprovalQueue.get_status(req_id), "APPROVED")

    def test_team_archetype_presets(self):
        """Verify list_presets and load_preset."""
        presets = list_presets()
        self.assertGreaterEqual(len(presets), 3)
        preset_ids = [p["id"] for p in presets]
        self.assertIn("hedge_fund", preset_ids)
        self.assertIn("engineering_shop", preset_ids)
        self.assertIn("osint_bureau", preset_ids)

        loaded = load_preset("hedge_fund")
        self.assertTrue(loaded)

        subagents = db.get_all_subagents()
        subagent_ids = [s["id"] for s in subagents]
        self.assertIn("fund_lead", subagent_ids)
        self.assertIn("quant_analyst", subagent_ids)
        self.assertIn("risk_compliance", subagent_ids)


if __name__ == "__main__":
    unittest.main()
