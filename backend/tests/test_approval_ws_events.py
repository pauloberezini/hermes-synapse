"""Tests verifying WebSocket broadcast of approval_update events on create, resolve, and consume."""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from backend.auth import create_session
from backend.governance import ApprovalQueue
from backend.identity import Principal
from backend.main import app
from backend.websocket_manager import manager


@pytest.mark.asyncio
async def test_websocket_broadcasts_on_create_resolve_consume(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict] = []

    async def _mock_broadcast(msg: dict) -> None:
        events.append(msg)

    monkeypatch.setattr(manager, "broadcast", _mock_broadcast)

    # 1. Create approval request
    req_id = ApprovalQueue.request_approval(
        agent_id="test_agent",
        action_name="execute_command",
        payload={"command": "echo hi"},
    )
    # Let async event loop task fire
    await asyncio.sleep(0.01)

    assert any(e.get("type") == "approval_update" and e.get("id") == req_id and e.get("status") == "PENDING" for e in events)

    # 2. Resolve approval request
    admin = Principal(subject="alice", roles=("admin",))
    ApprovalQueue.resolve(req_id, "APPROVED", principal=admin)
    await asyncio.sleep(0.01)

    assert any(e.get("type") == "approval_update" and e.get("id") == req_id and e.get("status") == "APPROVED" for e in events)

    # 3. Consume approval request
    ApprovalQueue.consume(req_id)
    await asyncio.sleep(0.01)

    assert any(e.get("type") == "approval_update" and e.get("id") == req_id and e.get("status") == "CONSUMED" for e in events)


def test_resolve_route_emits_one_approved_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """The route does not broadcast on its own. The queue emits the only APPROVED event."""
    events: list[dict] = []

    def _record_sync(msg: dict) -> None:
        events.append(msg)

    async def _record_async(msg: dict) -> None:
        events.append(msg)

    monkeypatch.setattr("backend.websocket_manager.broadcast_sync", _record_sync)
    monkeypatch.setattr(manager, "broadcast", _record_async)

    class _FakeClient:
        async def send_text(self, _text: str) -> None:
            return None

    fake = _FakeClient()
    manager.active_connections.add(fake)  # type: ignore[arg-type]
    try:
        req_id = ApprovalQueue.request_approval(
            agent_id="ws_once",
            action_name="execute_command",
            payload={"command": "echo once"},
        )
        events.clear()
        token = create_session()
        client = TestClient(app, headers={"Authorization": f"Bearer {token}"})
        response = client.post(
            f"/api/governance/approvals/{req_id}/resolve",
            json={"decision": "APPROVED", "resolver_note": "ok"},
        )
        assert response.status_code == 200
    finally:
        manager.active_connections.discard(fake)  # type: ignore[arg-type]

    approved = [event for event in events if event.get("status") == "APPROVED" and event.get("id") == req_id]
    assert approved == [{"type": "approval_update", "id": req_id, "status": "APPROVED"}]
