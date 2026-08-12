"""
Unit tests for backend/context_manager.py
"""

import unittest
from backend.context_manager import (
    estimate_tokens,
    compress_step_context,
    build_subagent_messages,
)

class TestContextManager(unittest.TestCase):

    def test_estimate_tokens(self):
        self.assertEqual(estimate_tokens(""), 0)
        self.assertGreater(estimate_tokens("Hello World"), 0)
        # Non-ASCII tokens
        ru_text = "Привет мир! Это тестовая строка на русском языке."
        self.assertGreater(estimate_tokens(ru_text), 10)

    def test_compress_step_context(self):
        results = [
            {"step": 0, "agent": "research", "output": "A" * 5000},
            {"step": 1, "agent": "code", "output": {"stdout": "Success: 42\n" + "B" * 4000}},
            {"step": 2, "agent": "failed_agent", "error": "Connection error"}
        ]
        compressed = compress_step_context(results, max_chars_per_step=500)
        self.assertIn("Data from previous steps:", compressed)
        self.assertIn("...[truncated long step report]", compressed)
        self.assertIn("...[truncated output]", compressed)
        self.assertIn("Connection error", compressed)

    def test_build_subagent_messages_budget_enforcement(self):
        system_prompt = "You are a helpful assistant."
        system_info = "Time: 2026-08-09"
        lang_directive = "[LANGUAGE DIRECTIVE]: You MUST respond exclusively in Russian."
        history = [
            {"role": "user", "content": "Turn 1 " + "X" * 2000},
            {"role": "assistant", "content": "Response 1 " + "Y" * 2000},
            {"role": "user", "content": "Turn 2 " + "Z" * 2000},
        ]
        user_content = "Execute trade on Bybit"

        messages = build_subagent_messages(
            system_prompt=system_prompt,
            system_info=system_info,
            lang_directive=lang_directive,
            history=history,
            user_content=user_content,
            max_tokens=2000
        )

        self.assertGreater(len(messages), 1)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[-1]["content"], user_content)
        # Total estimated tokens across output messages must stay within budget
        total_est = sum([estimate_tokens(m["content"]) for m in messages])
        self.assertLessEqual(total_est, 2500)

if __name__ == "__main__":
    unittest.main()
