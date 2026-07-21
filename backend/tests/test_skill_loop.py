import os
import json
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from backend.database import (
    save_decision_log,
    get_decision_logs,
    db_save_distilled_skill,
    db_get_distilled_skills,
    db_is_log_distilled,
    db_get_undistilled_successful_logs
)
from backend.skill_loop import SkillDistiller, slugify, get_skill_distiller
from backend.main import app


@pytest.fixture
def sample_decision_log():
    import uuid
    tag = uuid.uuid4().hex[:6]
    msg = f"Automate daily backup of user settings and sync with remote storage {tag}"
    log_entry = {
        "timestamp": "2026-07-21 12:00:00",
        "session_id": f"test_session_{tag}",
        "model": "google/gemini-2.5-flash",
        "latency_ms": 450,
        "success": True,
        "error": None,
        "prompt_tokens_estimate": 120,
        "user_message": msg,
        "assistant_response": "Successfully executed daily backup procedure and verified remote synchronization.",
        "traces": [
            {"action": "read_user_config", "result": "Loaded 12 settings"},
            {"action": "create_backup_archive", "result": "Archive created at /tmp/backup.zip"},
            {"action": "upload_remote", "result": "Uploaded to S3 bucket /backups"}
        ],
        "agent_id": "jarvis",
        "completion_tokens_estimate": 80,
        "cost_usd": 0.0012
    }
    save_decision_log(log_entry)
    logs = get_decision_logs(limit=10)
    for l in logs:
        if l.get("user_message") == msg:
            return l
    return logs[0]


@pytest.fixture(autouse=True)
def disable_external_llm_api(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")


def test_slugify():
    assert slugify("Skill: Backup User Settings") == "skill_backup_user_settings"
    assert slugify("Test 123!@# Special Chars") == "test_123_special_chars"


def test_heuristic_distillation(sample_decision_log):
    distiller = SkillDistiller(api_key=None)
    skill_dict = distiller._heuristic_distillation(sample_decision_log)

    assert "skill_name" in skill_dict
    assert "title" in skill_dict
    assert "trigger_conditions" in skill_dict
    assert "content" in skill_dict

    content = skill_dict["content"]
    assert "# Skill:" in content
    assert "## Trigger Conditions" in content
    assert "## Procedure & Pitfalls" in content
    assert "## Verification Checklist" in content
    assert "read_user_config" in content or "Execute Action" in content


def test_parse_skill_markdown(sample_decision_log):
    distiller = SkillDistiller(api_key=None)
    md_sample = (
        "# Skill: Test Automated Backup\n\n"
        "## Trigger Conditions\n"
        "- User wants to backup data\n\n"
        "## Procedure & Pitfalls\n"
        "1. Step one\n"
        "2. Step two\n\n"
        "## Verification Checklist\n"
        "- [ ] Verified backup file\n"
    )
    parsed = distiller._parse_skill_markdown(md_sample, sample_decision_log)
    assert parsed["title"] == "Test Automated Backup"
    assert parsed["skill_name"].startswith("test_automated_backup")
    assert "User wants to backup data" in parsed["trigger_conditions"]
    assert parsed["content"] == md_sample


def test_save_and_index_skill(sample_decision_log, tmp_path):
    with patch("backend.skill_loop.SKILLS_DIR", str(tmp_path)), \
         patch("backend.memory.QdrantMemoryEngine.index_document", return_value=True):

        distiller = SkillDistiller(api_key=None)
        skill_dict = distiller.distill_log_entry(sample_decision_log)
        saved = distiller.save_and_index_skill(skill_dict)

        assert os.path.exists(saved["file_path"])
        assert saved["file_path"].startswith(str(tmp_path))

        with open(saved["file_path"], "r", encoding="utf-8") as f:
            file_content = f.read()
        assert file_content == skill_dict["content"]

        distilled_db = db_get_distilled_skills(limit=10)
        matching = [s for s in distilled_db if s["skill_name"] == saved["skill_name"]]
        assert len(matching) > 0
        assert db_is_log_distilled(sample_decision_log["id"])


def test_undistilled_logs_filtering():
    # Insert log with < 3 steps (should be ignored)
    short_log = {
        "timestamp": "2026-07-21 12:05:00",
        "session_id": "test_session_2",
        "model": "google/gemini-2.5-flash",
        "latency_ms": 100,
        "success": True,
        "error": None,
        "prompt_tokens_estimate": 10,
        "user_message": "Simple hello query",
        "assistant_response": "Hello world",
        "traces": [{"action": "greet", "result": "Hi"}]
    }
    save_decision_log(short_log)

    undistilled = db_get_undistilled_successful_logs(min_steps=3, limit=10)
    for log in undistilled:
        assert len(log["traces"]) >= 3
        assert log["success"] is True


def test_process_undistilled_logs(sample_decision_log, tmp_path):
    with patch("backend.skill_loop.SKILLS_DIR", str(tmp_path)), \
         patch("backend.memory.QdrantMemoryEngine.index_document", return_value=True), \
         patch("backend.skill_loop.get_skill_distiller", return_value=SkillDistiller(api_key=None)):

        distiller = get_skill_distiller()
        distilled_list = distiller.process_undistilled_logs(min_steps=3, limit=5)

        assert len(distilled_list) > 0
        # Re-running process_undistilled_logs should return 0 new skills since they are now marked as distilled
        new_distilled = distiller.process_undistilled_logs(min_steps=3, limit=5)
        # All returned previously should not be re-distilled
        distilled_log_ids = [d["decision_log_id"] for d in distilled_list if d.get("decision_log_id")]
        for d in new_distilled:
            assert d.get("decision_log_id") not in distilled_log_ids


def test_skill_loop_api_endpoints(sample_decision_log, tmp_path):
    from backend.auth import active_sessions
    active_sessions.add("test-token")

    client = TestClient(app)
    client.headers = {"Authorization": "Bearer test-token"}

    with patch("backend.skill_loop.SKILLS_DIR", str(tmp_path)), \
         patch("backend.memory.QdrantMemoryEngine.index_document", return_value=True), \
         patch("backend.skill_loop.get_skill_distiller", return_value=SkillDistiller(api_key=None)):

        # Test GET /api/skills/distilled
        resp = client.get("/api/skills/distilled")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

        # Test POST /api/skills/distill/{log_id}
        log_id = sample_decision_log["id"]
        resp_single = client.post(f"/api/skills/distill/{log_id}")
        assert resp_single.status_code == 200
        assert resp_single.json()["status"] in ("success", "already_distilled")

        # Test POST /api/skills/distill/auto
        resp_auto = client.post("/api/skills/distill/auto?min_steps=3&limit=5")
        assert resp_auto.status_code == 200
        assert "distilled_count" in resp_auto.json()
