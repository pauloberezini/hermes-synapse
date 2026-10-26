"""Tests verifying WebSocket broadcast of approval_update events on create, resolve, and consume."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
import pytest

from backend.governance import ApprovalQueue
from backend.identity import Principal
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
