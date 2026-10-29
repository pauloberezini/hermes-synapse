"""Integration tests for approvals demo hardening phase 2.

Drives the agent entry points and the governance HTTP routes. The model is stubbed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.agent import JarvisAgent
from backend.auth import create_session
from backend.governance import ApprovalQueue, gate_tool
from backend.main import app
from backend.websocket_manager import manager

_ROOT = Path(__file__).resolve().parents[2]
_VERIFIER = _ROOT / "scripts" / "verify_decision_log.py"


def _client() -> TestClient:
    token = create_session()
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def _agent() -> JarvisAgent:
    agent = JarvisAgent()
    agent.api_key = "test_key"
    agent.api_base = "https://openrouter.ai/api/v1"
    agent.model = "test-model"
    return agent


def _llm_post(*bodies: dict):
    queue = list(bodies)

    async def _post(self, *args, **kwargs):
        response = MagicMock()
        response.status_code = 200
        response.text = ""
        response.headers = {}
        response.json.return_value = queue.pop(0)
        return response

    return _post


def _tool_turn(command: str) -> dict:
    return {
        "choices": [{
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "execute_command",
                        "arguments": json.dumps({"command": command}),
                    },
                }],
            }
        }]
    }


def _text_turn(text: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


class _AllowSkill:
    async def check_entitlement(self, user_id: str, skill_id: str) -> bool:
        return True


@pytest.mark.asyncio
async def test_direct_respond_sets_jarvis_name_and_direct_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPLEXITY_ROUTING", "always_direct")
    with patch("httpx.AsyncClient.post", _llm_post(_tool_turn("uname -a"), _text_turn("done"))), \
         patch("backend.rag.search_memory", return_value=[]), \
         patch("backend.marketplace.billing_adapter.get_billing_adapter", return_value=_AllowSkill()):
        await _agent().respond("run uname", session_id="chat42")

    pending = ApprovalQueue.get_pending()
    row = next(item for item in pending if item["agent_id"] == "chat42")
    detail = ApprovalQueue.get_detail(row["id"])
    assert detail is not None
    assert row["agent_name"] == "Jarvis"
    assert detail["bundle"]["links"]["agent"] == "Jarvis"
    assert detail["bundle"]["links"]["session_id"] == "chat42"
    assert detail["bundle"]["plan"]["agent"] == "jarvis"
    assert detail["bundle"]["plan"]["step_count"] == 1
    assert "run uname" in detail["bundle"]["plan"]["instructions"]
    assert "direct_route" in detail["bundle"]["flags"]
    assert "plan_missing" not in detail["bundle"]["flags"]


@pytest.mark.asyncio
async def test_subagent_respond_keeps_session_key_and_shows_sysops(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPLEXITY_ROUTING", "always_direct")
    with patch("httpx.AsyncClient.post", _llm_post(_tool_turn("uname -a"), _text_turn("done"))), \
         patch("backend.rag.search_memory", return_value=[]), \
         patch("backend.marketplace.billing_adapter.get_billing_adapter", return_value=_AllowSkill()):
        await _agent()._respond_as_subagent(
            "run uname",
            {
                "id": "sysops",
                "name": "Sys Ops",
                "system_prompt": "ops",
                "model": "test-model",
                "skills": "shell_execution",
                "agent_type": "custom",
            },
            chat_id="chat42_sysops",
            include_history=False,
        )

    row = next(item for item in ApprovalQueue.get_pending() if item["agent_id"] == "chat42_sysops")
    detail = ApprovalQueue.get_detail(row["id"])
    assert detail is not None
    assert row["agent_name"] == "Sys Ops"
    assert row["agent_id"] == "chat42_sysops"
    assert detail["bundle"]["plan"]["agent"] == "sysops"
    assert "direct_route" in detail["bundle"]["flags"]
    assert "direct_route" in row["flags"]


def test_approvals_api_returns_agent_name_and_session() -> None:
    from backend.agent import approval_context

    with approval_context("Sys Ops", "run uname", "sysops"):
        raw = gate_tool("chat42_sysops", "execute_command", {"command": "uname -a"})
    request_id = json.loads(raw or "")["request_id"]
    client = _client()
    listed = client.get("/api/governance/approvals", params={"pending_only": "true"})
    assert listed.status_code == 200
    row = next(item for item in listed.json() if item["id"] == request_id)
    assert row["agent_name"] == "Sys Ops"
    assert row["agent_id"] == "chat42_sysops"
    detail = client.get(f"/api/governance/approvals/{request_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["agent_name"] == "Sys Ops"
    assert body["bundle"]["links"]["session_id"] == "chat42_sysops"


def test_verify_api_fails_after_evidence_edit() -> None:
    from backend.database import _execute
    from backend.evidence import build_bundle

    bundle = build_bundle("agent", "execute_command", {"command": "echo hi"}, None)
    request_id = ApprovalQueue.request_approval(
        "agent",
        "execute_command",
        {"command": "echo hi"},
        bundle=bundle,
    )
    client = _client()
    clean = client.get("/api/governance/decisions/verify")
    assert clean.status_code == 200
    assert clean.json()["ok"] is True

    stored = _execute("SELECT bundle_json FROM approval_evidence WHERE request_id = ?", (request_id,))
    edited = json.loads(stored[0][0])
    edited["inputs"] = {"command": "tampered"}
    _execute("DROP TRIGGER IF EXISTS approval_evidence_no_update")
    _execute(
        "UPDATE approval_evidence SET bundle_json = ? WHERE request_id = ?",
        (json.dumps(edited), request_id),
    )
    broken = client.get("/api/governance/decisions/verify")
    assert broken.json()["ok"] is False
    assert broken.json()["error"] == "bundle_hash mismatch"


def test_verify_api_fails_when_bundled_evidence_row_is_deleted() -> None:
    from backend.database import _execute
    from backend.evidence import build_bundle

    bundle = build_bundle("agent", "execute_command", {"command": "echo hi"}, None)
    request_id = ApprovalQueue.request_approval(
        "agent",
        "execute_command",
        {"command": "echo hi"},
        bundle=bundle,
    )
    client = _client()
    clean = client.get("/api/governance/decisions/verify")
    assert clean.status_code == 200
    assert clean.json()["ok"] is True

    _execute("DELETE FROM approval_evidence WHERE request_id = ?", (request_id,))
    broken = client.get("/api/governance/decisions/verify")
    assert broken.json()["ok"] is False
    assert broken.json()["error"] == "evidence missing"


def test_export_zip_verifies_and_resolve_emits_one_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from backend.agent import approval_context

    events: list[dict] = []

    def _record(msg: dict) -> None:
        events.append(msg)

    monkeypatch.setattr("backend.websocket_manager.broadcast_sync", _record)

    class _FakeClient:
        async def send_text(self, _text: str) -> None:
            return None

    fake = _FakeClient()
    manager.active_connections.add(fake)  # type: ignore[arg-type]
    try:
        with approval_context("Sys Ops", "run uname", "sysops"):
            first = json.loads(gate_tool("session_a", "execute_command", {"command": "echo hi"}) or "")
        client = _client()
        resolved = client.post(
            f"/api/governance/approvals/{first['request_id']}/resolve",
            json={"decision": "APPROVED", "resolver_note": "ok"},
        )
        assert resolved.status_code == 200
        with approval_context("Sys Ops", "run uname", "sysops"):
            other = json.loads(gate_tool("session_b", "execute_command", {"command": "echo hi"}) or "")
        exported = client.get("/api/governance/decisions/export.zip")
    finally:
        manager.active_connections.discard(fake)  # type: ignore[arg-type]

    approved = [event for event in events if event.get("status") == "APPROVED"]
    assert approved == [{
        "type": "approval_update",
        "id": first["request_id"],
        "status": "APPROVED",
    }]
    assert other["status"] == "PENDING_APPROVAL"
    assert other["request_id"] != first["request_id"]
    assert ApprovalQueue.get_status(first["request_id"]) == "APPROVED"

    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("application/zip")
    path = tmp_path / "decisions.zip"
    path.write_bytes(exported.content)
    verified = subprocess.run(
        [sys.executable, str(_VERIFIER), str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert verified.returncode == 0, verified.stderr
    assert verified.stdout.startswith("ok checked=")
