"""API tests for approval evidence endpoints, redacted bundles, and resolve security."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.auth import create_session
from backend.evidence import EvidenceContext, build_bundle, redact_bundle
from backend.governance import ApprovalQueue
from backend.main import app


def _client() -> TestClient:
    token = create_session()
    return TestClient(app, headers={"Authorization": f"Bearer {token}"})


def test_list_items_have_hash_and_no_bundle_json() -> None:
    ctx = EvidenceContext()
    ctx.add_tool_result("web_search", "result body", capped_at=600)
    bundle = build_bundle("test_agent", "execute_command", {"command": "ls"}, ctx)
    req_id = ApprovalQueue.request_approval(
        "test_agent",
        "execute_command",
        {"command": "ls"},
        bundle=bundle,
    )

    client = _client()
    resp = client.get("/api/governance/approvals")
    assert resp.status_code == 200
    items = resp.json()
    item = next(i for i in items if i["id"] == req_id)
    assert "bundle_hash" in item and len(item["bundle_hash"]) == 64
    assert "flags" in item
    assert "tool_result_capped_600" in item["flags"]
    assert "description" in item
    assert "bundle_json" not in item
    assert "bundle" not in item


def test_get_by_id_returns_redacted_bundle() -> None:
    ctx = EvidenceContext()
    ctx.add_tool_result("read_file", "contact me at secret@company.com sk-abcdefghijklmnopqrstuvwxyz123")
    bundle = redact_bundle(build_bundle("test_agent", "execute_command", {"command": "curl a@b.com"}, ctx))
    req_id = ApprovalQueue.request_approval(
        "test_agent",
        "execute_command",
        {"command": "curl a@b.com"},
        bundle=bundle,
    )

    client = _client()
    resp = client.get(f"/api/governance/approvals/{req_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == req_id
    assert data["bundle_hash"] and len(data["bundle_hash"]) == 64
    assert data["bundle"] is not None
    assert "decisions" in data
    # Ensure PII is redacted in GET detail
    bundle_str = str(data["bundle"])
    assert "secret@company.com" not in bundle_str
    assert "sk-abcdefghijklmnopqrstuvwxyz123" not in bundle_str
    assert "a@b.com" not in bundle_str


def test_get_by_id_404() -> None:
    client = _client()
    resp = client.get("/api/governance/approvals/999999")
    assert resp.status_code == 404


def test_resolve_ignores_client_supplied_hash() -> None:
    bundle = build_bundle("test_agent", "execute_command", {"cmd": "id"}, None)
    req_id = ApprovalQueue.request_approval(
        "test_agent",
        "execute_command",
        {"cmd": "id"},
        bundle=bundle,
    )
    initial_hash = ApprovalQueue.get_detail(req_id)["bundle_hash"]
    assert initial_hash

    client = _client()
    resp = client.post(
        f"/api/governance/approvals/{req_id}/resolve",
        json={"decision": "APPROVED", "resolver_note": "approved", "bundle_hash": "evil_injected_hash"},
    )
    assert resp.status_code == 200
    after_detail = ApprovalQueue.get_detail(req_id)
    assert after_detail["status"] == "APPROVED"
    assert after_detail["bundle_hash"] == initial_hash
    assert after_detail["bundle_hash"] != "evil_injected_hash"


def test_unauthenticated_get_by_id_401() -> None:
    client = TestClient(app)
    resp = client.get("/api/governance/approvals/1")
    assert resp.status_code == 401
