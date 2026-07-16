import json
from unittest.mock import patch

import pytest

from backend import control_plane, database


@pytest.fixture()
def control_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "control-plane.db")
    monkeypatch.setattr(database, "DB_PATH", db_path)
    monkeypatch.setattr(control_plane, "DB_PATH", db_path)
    database.init_db()
    return db_path


def test_risk_policy_defaults_unknown_tools_to_r4(control_db):
    assert control_plane.classify_tool_risk("get_system_stats") == "R0"
    assert control_plane.classify_tool_risk("add_calendar_event") == "R3"
    assert control_plane.classify_tool_risk("execute_command") == "R4"
    assert control_plane.classify_tool_risk("untrusted_plugin_action") == "R4"


def test_r3_action_is_queued_until_approved(control_db):
    with patch("backend.tools.execute_tool") as execute:
        result = json.loads(control_plane.execute_governed_tool(
            "add_calendar_event", {"title": "Review", "date": "2026-07-17"}, "dashboard"
        ))
        assert result["status"] == "awaiting_approval"
        assert result["risk_class"] == "R3"
        execute.assert_not_called()

        task = control_plane.approve_task(result["task_id"])
        assert task["status"] == "approved"
        execute.return_value = json.dumps({"status": "success"})
        completed = json.loads(control_plane.execute_governed_tool(
            "add_calendar_event", task["tool_arguments"], "dashboard", approved_task_id=task["id"]
        ))
        assert completed["status"] == "success"
        assert control_plane.get_task(task["id"])["status"] == "done"


def test_r4_requires_two_explicit_confirmations(control_db):
    pending = json.loads(control_plane.execute_governed_tool(
        "execute_command", {"command": "uname -a"}, "dashboard"
    ))
    first = control_plane.approve_task(pending["task_id"])
    assert first["status"] == "awaiting_approval"
    assert first["approval_count"] == 1
    second = control_plane.approve_task(pending["task_id"])
    assert second["status"] == "approved"
    assert second["approval_count"] == 2


def test_kill_switch_blocks_new_tool_execution(control_db):
    control_plane.set_kill_switch(True, "incident test")
    result = json.loads(control_plane.execute_governed_tool("get_system_stats", {}, "dashboard"))
    assert result["status"] == "killed"
    assert "incident test" in result["reason"]

    state = control_plane.set_kill_switch(False, "test complete")
    assert state["kill_switch"] is False


def test_evidence_ledger_hashes_results_and_redacts_secret_fields(control_db):
    task = control_plane.create_tool_task(
        "get_weather", {"location": "Minsk", "api_key": "must-not-leak"}, "dashboard"
    )
    assert task["tool_arguments"]["api_key"] == "[REDACTED]"
    control_plane.start_task(task["id"])
    control_plane.finish_task(task["id"], '{"temperature": 20}')
    event = control_plane.list_events(limit=1)[0]
    assert event["evidence_id"].startswith("EV-")
    assert len(event["output_hash"]) == 64
