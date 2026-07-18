import json

import pytest

from backend import autonomy, database


@pytest.fixture()
def autonomy_workspace(tmp_path, monkeypatch):
    database_path = str(tmp_path / "autonomy.db")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    monkeypatch.setattr(database, "DB_PATH", database_path)
    monkeypatch.setattr(autonomy, "DB_PATH", database_path)
    monkeypatch.setenv("PROJECT_WORKSPACE_ROOT", str(workspace))
    database.init_db()
    return workspace


def test_index_is_incremental_and_does_not_persist_source(autonomy_workspace):
    source = autonomy_workspace / "service.py"
    source.write_text(
        "import sqlite3\n\nSECRET_SENTINEL = 'not-indexed'\n\ndef load_project():\n    return sqlite3.connect(':memory:')\n",
        encoding="utf-8",
    )

    first = autonomy.index_project()
    second = autonomy.index_project()
    matches = autonomy.search_project_memory("load_project sqlite3")

    assert first["indexed"] == 1
    assert second["indexed"] == 0
    assert second["unchanged"] == 1
    assert matches[0]["path"] == "service.py"
    assert "load_project" in matches[0]["symbols"]

    with autonomy._connect() as connection:
        persisted = json.dumps(
            [dict(row) for row in connection.execute("SELECT * FROM project_memory_files")],
            ensure_ascii=False,
        )
    assert "SECRET_SENTINEL" not in persisted
    assert "not-indexed" not in persisted


def test_workspace_cannot_escape_configured_root(autonomy_workspace, tmp_path):
    with pytest.raises(ValueError, match="configured root"):
        autonomy.index_project(str(tmp_path))


def test_plan_contains_specialist_contracts_and_bounded_verification(autonomy_workspace):
    plan = autonomy.build_plan(
        "Update the frontend and backend, then test the Docker deployment and retain codebase memory."
    )

    assert plan["tier"] in {"verify", "auditor"}
    assert {"frontend_validation", "backend_validation", "containers", "codebase_graph"}.issubset(
        plan["capabilities"]
    )
    assert {step["agent"] for step in plan["steps"]}.issubset(plan["role_contracts"])
    verifier = next(step for step in plan["steps"] if step["agent"] == "verifier")
    assert verifier["max_attempts"] == 3


def test_runtime_plan_records_attempts_and_evidence(autonomy_workspace):
    plan = autonomy.save_runtime_plan(
        "Implement a safe change",
        [{"agent": "code", "instructions": "Implement it", "acceptance": ["Tests pass"]}],
    )
    autonomy.update_runtime_step(plan["id"], 0, status="running")
    autonomy.update_runtime_step(
        plan["id"],
        0,
        status="completed",
        result_summary="pytest passed",
    )

    stored = autonomy.get_plan(plan["id"])
    assert stored["status"] == "running"
    assert stored["steps"][0]["attempts"] == 1
    assert stored["steps"][0]["result_summary"] == "pytest passed"
