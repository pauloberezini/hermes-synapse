"""Agent parent links are a DAG. A cycle must be refused on write and must not recurse at runtime."""
import sys

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from backend import database
from backend.auth import active_sessions
from backend.main import app
from backend.orchestrator import run_orchestration

client = TestClient(app)
client.headers = {"Authorization": "Bearer test-token"}
active_sessions.add("test-token")


def _save(agent_id, name, parent_id=None, agent_type="orchestrator"):
    database.save_subagent(
        agent_id, name, f"prompt {agent_id}", "test-model",
        agent_type=agent_type, parent_id=parent_id,
    )


def test_save_subagent_rejects_parent_cycle():
    _save("alpha", "Alpha")
    _save("beta", "Beta", parent_id="alpha")

    with pytest.raises(Exception, match="[Cc]ycle"):
        _save("alpha", "Alpha", parent_id="beta")

    assert database.get_subagent("alpha")["parent_id"] in (None, "")

    with pytest.raises(Exception, match="[Cc]ycle"):
        _save("alpha", "Alpha", parent_id="alpha")

    _save("gamma", "Gamma", parent_id="beta", agent_type="agent")
    with pytest.raises(Exception, match="[Cc]ycle"):
        _save("alpha", "Alpha", parent_id="gamma")

    # re-saving the existing edge is not a new cycle
    _save("beta", "Beta", parent_id="alpha")
    assert database.get_subagent("beta")["parent_id"] == "alpha"


def test_save_subagent_api_rejects_parent_cycle():
    _save("alpha", "Alpha")
    _save("beta", "Beta", parent_id="alpha")
    res = client.post("/api/subagents", json={
        "id": "alpha",
        "name": "Alpha",
        "system_prompt": "prompt alpha",
        "model": "test-model",
        "agent_type": "orchestrator",
        "parent_id": "beta",
    })
    assert res.status_code == 400
    assert "cycle" in res.json()["error"].lower()
    assert database.get_subagent("alpha")["parent_id"] in (None, "")


_CYCLE_COPY = {
    "en": "This link would cycle the agent graph.",
    "ru": "Эта связь замыкает цикл в графе агентов.",
    "he": "קישור זה סוגר מעגל בגרף הסוכנים.",
    "de": "Diese Verbindung würde einen Zyklus im Agentengraphen schließen.",
    "es": "Este enlace cerraría un ciclo en el grafo de agentes.",
    "fr": "Ce lien fermerait un cycle dans le graphe des agents.",
}


@pytest.mark.parametrize("lang", list(_CYCLE_COPY))
def test_cycle_error_follows_language(lang):
    _save("alpha", "Alpha")
    _save("beta", "Beta", parent_id="alpha")
    database.set_setting("language", lang)
    res = client.post("/api/subagents", json={
        "id": "alpha",
        "name": "Alpha",
        "system_prompt": "prompt alpha",
        "model": "test-model",
        "agent_type": "orchestrator",
        "parent_id": "beta",
    })
    assert res.status_code == 400
    assert res.json()["error"] == _CYCLE_COPY[lang]


def test_cycle_error_unknown_language_falls_back_to_english():
    _save("alpha", "Alpha")
    _save("beta", "Beta", parent_id="alpha")
    database.set_setting("language", "ja")
    res = client.post("/api/subagents", json={
        "id": "alpha",
        "name": "Alpha",
        "system_prompt": "prompt alpha",
        "model": "test-model",
        "agent_type": "orchestrator",
        "parent_id": "beta",
    })
    assert res.status_code == 400
    assert res.json()["error"] == _CYCLE_COPY["en"]


def _plant_cycle():
    """Write a mutual-parent cycle under the save guard (already-corrupt graph)."""
    _save("alpha", "Alpha")
    _save("beta", "Beta", parent_id="alpha")
    database._execute("UPDATE subagents SET parent_id = ? WHERE id = ?", ("beta", "alpha"))


async def _llm(messages, api_key, model):
    system = messages[0]["content"]
    if "Planner for 'Alpha'" in system:
        return '{"steps": [{"agent": "beta", "instructions": "delegate"}]}'
    if "Planner for 'Beta'" in system:
        return '{"steps": [{"agent": "alpha", "instructions": "delegate"}]}'
    return "synthesized"


@pytest.mark.asyncio
async def test_mutual_parents_do_not_recurse():
    _plant_cycle()
    # ponytail: cap the stack so a missing guard fails this test in one second
    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(80)
    try:
        with patch("backend.orchestrator.call_llm", side_effect=_llm) as mock_llm, \
             patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
            result = await run_orchestration("do the thing", "key", "test-model", chat_id="alpha")
    finally:
        sys.setrecursionlimit(old_limit)

    assert mock_llm.call_count < 8
    assert any(
        t.get("action") == "Cycle" or "cycle" in str(t.get("message", "")).lower()
        for t in result["traces"]
    )


@pytest.mark.asyncio
async def test_acyclic_sub_orchestrator_still_runs():
    _save("alpha", "Alpha")
    _save("beta", "Beta", parent_id="alpha")
    _save("gamma", "Gamma", parent_id="beta", agent_type="agent")

    async def llm(messages, api_key, model):
        system = messages[0]["content"]
        if "Planner for 'Alpha'" in system:
            return '{"steps": [{"agent": "beta", "instructions": "delegate"}]}'
        if "Planner for 'Beta'" in system:
            return '{"steps": [{"agent": "gamma", "instructions": "work"}]}'
        return "synthesized"

    with patch("backend.orchestrator.call_llm", side_effect=llm) as mock_llm, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock), \
         patch("backend.agent.agent_instance._respond_as_subagent", new_callable=AsyncMock, return_value="gamma done"):
        result = await run_orchestration("do the thing", "key", "test-model", chat_id="alpha")

    assert result["response"] == "synthesized"
    assert mock_llm.call_count == 4
    assert not any(t.get("action") == "Cycle" for t in result["traces"])


def _skill_set(value):
    if not value:
        return set()
    return {s.strip() for s in str(value).split(",") if s.strip()}


@pytest.mark.asyncio
async def test_nested_orchestrator_receives_skill_intersection():
    """A sub-orchestrator is capped by its parent's skills, and its leaf sees that intersection."""
    database.save_subagent(
        "skill_a", "SkillA", "p", "test-model",
        agent_type="orchestrator", skills="web_search,shell",
    )
    database.save_subagent(
        "skill_b", "SkillB", "p", "test-model",
        agent_type="sub-orchestrator", parent_id="skill_a", skills="shell,python_sandbox",
    )
    database.save_subagent(
        "skill_c", "SkillC", "p", "test-model",
        agent_type="agent", parent_id="skill_b", skills="web_search,shell,python_sandbox",
    )
    captured = {}

    async def llm(messages, api_key, model):
        system = messages[0]["content"]
        if "Planner for 'SkillA'" in system:
            return '{"steps": [{"agent": "skill_b", "instructions": "delegate"}]}'
        if "Planner for 'SkillB'" in system:
            return '{"steps": [{"agent": "skill_c", "instructions": "work"}]}'
        return "synthesized"

    async def fake_sub(instructions, agent_meta, parent_skills=None, chat_id=None, **kwargs):
        captured["id"] = agent_meta["id"]
        captured["parent_skills"] = parent_skills
        return "done"

    try:
        with patch("backend.orchestrator.call_llm", side_effect=llm), \
             patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock), \
             patch("backend.agent.agent_instance._respond_as_subagent", side_effect=fake_sub):
            result = await run_orchestration("do the thing", "key", "test-model", chat_id="skill_a")
    finally:
        for agent_id in ("skill_c", "skill_b", "skill_a"):
            database.delete_subagent(agent_id)

    assert result["response"] == "synthesized"
    assert captured["id"] == "skill_c"
    # skill_a {web_search, shell} ∩ skill_b {shell, python_sandbox} = {shell}
    assert _skill_set(captured["parent_skills"]) == {"shell"}


@pytest.mark.asyncio
async def test_empty_skill_cap_grants_no_skill_tools():
    from backend.agent import agent_instance

    payload = {}

    async def _mock_post(url, json=None, headers=None):
        payload["body"] = json
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        return resp

    with patch("httpx.AsyncClient.post", side_effect=_mock_post), \
         patch("backend.rag.search_memory", return_value=[]):
        await agent_instance._respond_as_subagent(
            "hi",
            {
                "id": "leaf",
                "name": "Leaf",
                "system_prompt": "x",
                "model": "google/gemini-2.5-flash",
                "skills": "web_search,shell_execution",
                "agent_type": "agent",
            },
            parent_skills="",
            session_id="test_empty_skill_cap",
            include_history=False,
        )

    names = [t.get("function", {}).get("name") for t in (payload["body"].get("tools") or [])]
    assert "web_search" not in names
    assert "execute_command" not in names
