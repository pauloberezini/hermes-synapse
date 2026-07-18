import hashlib
import json
from types import SimpleNamespace

import pytest

from backend import (
    autonomy,
    capability_broker,
    control_plane,
    database,
    mcp_client,
    mcp_governance,
    mcp_openapi_proxy,
)


@pytest.fixture()
def governed_runtime(tmp_path, monkeypatch):
    db_path = str(tmp_path / "governed.db")
    workspace = tmp_path / "workspace"
    capability_root = tmp_path / "capabilities"
    workspace.mkdir()
    for module in (database, autonomy, control_plane, mcp_governance):
        monkeypatch.setattr(module, "DB_PATH", db_path)
    monkeypatch.setenv("PROJECT_WORKSPACE_ROOT", str(workspace))
    monkeypatch.setenv("AUTONOMY_CAPABILITY_ROOT", str(capability_root))
    database.init_db()
    autonomy._init_schema()
    mcp_governance._init_schema()
    return workspace


def _missing_visual_doctor():
    return {
        "status": "ready",
        "ready": 0,
        "total": 1,
        "checked_at": "now",
        "capabilities": [{
            "id": "visual_validation",
            "label": "Browser visual validation",
            "required": False,
            "status": "missing",
            "active_provider": None,
            "providers": [],
            "install_available": True,
        }],
    }


def test_capability_proposal_is_deduplicated_and_digest_bound(governed_runtime, monkeypatch):
    monkeypatch.setattr(autonomy, "doctor_capabilities", _missing_visual_doctor)

    first = autonomy.propose_capability("visual_validation")
    second = autonomy.propose_capability("visual_validation")

    assert first["id"] == second["id"]
    assert first["control_task"]["risk_class"] == "R3"
    assert first["plan"]["recipe"]["version"] == "1.57.0"
    assert first["plan"]["recipe_digest"] == capability_broker.recipe_digest("visual_validation")
    assert first["plan"]["isolation"]["shell"] is False


def test_approved_capability_executes_and_records_evidence(governed_runtime, monkeypatch):
    monkeypatch.setattr(autonomy, "doctor_capabilities", _missing_visual_doctor)
    proposal = autonomy.propose_capability("visual_validation")
    task_id = proposal["control_task"]["id"]
    control_plane.approve_task(task_id)
    monkeypatch.setattr(
        capability_broker,
        "install_capability",
        lambda capability_id, expected_digest: {
            "status": "installed",
            "capability_id": capability_id,
            "recipe_digest": expected_digest,
        },
    )

    result = autonomy.execute_approved_capability(task_id)

    assert result["status"] == "installed"
    assert autonomy.get_capability_proposal(proposal["id"])["status"] == "installed"
    assert control_plane.get_task(task_id)["status"] == "done"
    assert control_plane.list_events(limit=1)[0]["event_type"] == "task_completed"


def test_broker_rejects_disabled_or_changed_recipe(governed_runtime, monkeypatch):
    digest = capability_broker.recipe_digest("visual_validation")
    monkeypatch.setenv("AUTONOMY_INSTALL_ENABLED", "false")
    with pytest.raises(RuntimeError, match="disabled"):
        capability_broker.install_capability("visual_validation", digest)

    monkeypatch.setenv("AUTONOMY_INSTALL_ENABLED", "true")
    with pytest.raises(RuntimeError, match="recipe changed"):
        capability_broker.install_capability("visual_validation", "wrong-digest")


def test_package_verification_requires_version_license_and_integrity(governed_runtime, tmp_path, monkeypatch):
    recipe = capability_broker.recipe_for("visual_validation")
    staging = tmp_path / "staging"
    package_dir = staging / "node_modules" / "@playwright" / "test"
    command = staging / recipe["command"]
    package_dir.mkdir(parents=True)
    command.parent.mkdir(parents=True, exist_ok=True)
    command.write_text("#!/bin/sh\n", encoding="utf-8")
    package_dir.joinpath("package.json").write_text(
        json.dumps({"version": recipe["version"], "license": recipe["license"]}),
        encoding="utf-8",
    )
    lock_path = staging / "package-lock.json"
    lock_path.write_text(
        json.dumps({
            "packages": {
                "node_modules/@playwright/test": {"integrity": recipe["integrity"]},
            },
        }),
        encoding="utf-8",
    )
    recipe["lockfile_sha256"] = hashlib.sha256(lock_path.read_bytes()).hexdigest()
    monkeypatch.setattr(
        capability_broker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="Version 1.57.0", stderr=""),
    )

    result = capability_broker._verify_npm_install(staging, "visual_validation", recipe)
    assert result["version"] == "1.57.0"

    package_dir.joinpath("package.json").write_text(
        json.dumps({"version": "latest", "license": recipe["license"]}),
        encoding="utf-8",
    )
    with pytest.raises(RuntimeError, match="version"):
        capability_broker._verify_npm_install(staging, "visual_validation", recipe)


def test_mcp_policy_blocks_shells_plaintext_secrets_and_unsafe_http(governed_runtime):
    with pytest.raises(ValueError, match="built-in OpenAPI bridge"):
        mcp_governance.validate_server_config(
            "unsafe",
            {"command": "npx", "args": ["-y", "unknown-package"], "env": {}},
        )
    with pytest.raises(ValueError, match="must be stored as the reference"):
        mcp_governance.validate_server_config(
            "private-api",
            {
                "command": "python3",
                "args": ["/app/backend/mcp_openapi_proxy.py"],
                "env": {
                    "OPENAPI_URL": "https://example.com/openapi.json",
                    "STATIC_BEARER_TOKEN": "plain-text-secret",
                },
            },
        )
    with pytest.raises(ValueError, match="HTTPS"):
        mcp_governance.build_openapi_config("public-http", "http://example.com/openapi.json")
    with pytest.raises(ValueError, match="blocked network"):
        mcp_governance.build_openapi_config("metadata", "http://169.254.169.254/openapi.json")


def test_mcp_client_inherits_no_application_secrets(governed_runtime, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "must-not-leak")
    monkeypatch.setenv("STATIC_BEARER_TOKEN", "runtime-secret")
    client = mcp_client.MCPServerClient(
        "reviewed-api",
        mcp_governance.build_openapi_config(
            "reviewed-api",
            "https://example.com/openapi.json",
            "STATIC_BEARER_TOKEN",
        ),
    )

    assert client.env["STATIC_BEARER_TOKEN"] == "runtime-secret"
    assert "TELEGRAM_BOT_TOKEN" not in client.env


def test_mcp_connection_proposal_is_r4_and_deduplicated(governed_runtime):
    config = mcp_governance.build_openapi_config(
        "reviewed-api",
        "https://example.com/openapi.json",
    )
    first = mcp_governance.create_connection_proposal("reviewed-api", config)
    second = mcp_governance.create_connection_proposal("reviewed-api", config)

    assert first["id"] == second["id"]
    task = control_plane.get_task(first["control_task_id"])
    assert task["risk_class"] == "R4"
    assert task["approvals_required"] == 2
    assert task["tool_name"] is None


def test_openapi_proxy_blocks_cross_origin_and_metadata_networks():
    with pytest.raises(ValueError, match="origin differs"):
        mcp_openapi_proxy.validate_outbound_url(
            "https://other.example/api",
            allowed_origin=("https", "approved.example", 443),
        )
    with pytest.raises(ValueError, match="blocked network"):
        mcp_openapi_proxy.validate_outbound_url("http://169.254.169.254/latest/meta-data")
