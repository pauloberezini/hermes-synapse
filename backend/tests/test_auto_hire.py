"""Auto-hire: the planner can add a specialist in the same turn."""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from backend.database import (
    get_all_subagents,
    get_subagent,
    list_unused_auto_agents,
    save_session_metadata,
    save_subagent,
)
from backend.orchestrator import run_orchestration
from backend.plugins import hook
from backend.tools import call_subagent, create_subagent


@pytest.fixture(autouse=True)
def _auto_hire_on(monkeypatch):
    monkeypatch.setenv("AUTO_HIRE", "on")

PLAN = {
    "hire": [{
        "id": "options_analyst",
        "name": "Options Analyst",
        "mandate": "Analyse option chains: IV, Greeks, skew, defined-risk spreads.",
        "skills": ["market_monitor", "web_search", "agent_management", "shell_execution"],
        "reason": "No child covers options-chain analysis.",
    }],
    "steps": [{"agent": "options_analyst", "instructions": "Analyse AAPL calls: IV, Greeks, strikes."}],
}


def _desk(skills="market_monitor,web_search,shell_execution", parent_id=None):
    save_subagent(
        "desk", "Desk", "Spot trading desk. RSI and MACD only.", "parent-model",
        agent_type="orchestrator", parent_id=parent_id, skills=skills, x=100, y=100,
    )
    save_subagent(
        "quant", "Quant", "Compute RSI and MACD on spot prices.", "parent-model",
        agent_type="agent", parent_id="desk", skills="market_monitor", x=400, y=100,
    )
    save_session_metadata("216199859", "tg", agent_id="desk")


def _traces(result):
    return " ".join(f"{t.get('action', '')} {t.get('message', '')}" for t in result["traces"])


@pytest.fixture
def fallback_spy():
    import backend.plugins as plugins
    calls = []
    orig = plugins.hook

    def wrapped(name, *args, **kwargs):
        if name == "fallback_plan_steps":
            calls.append(kwargs.get("gap", args[3] if len(args) > 3 else None))
        return orig(name, *args, **kwargs)

    with patch("backend.plugins.hook", wrapped):
        yield calls


@pytest.mark.asyncio
async def test_planner_hire_creates_agent_and_runs_step():
    _desk()
    plan = json.dumps(PLAN)
    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.agent.agent_instance._respond_as_subagent", new_callable=AsyncMock) as mock_sub, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.side_effect = [plan, "IV 22, delta 0.4, defined-risk call spread."]
        mock_sub.return_value = "IV 22 delta 0.4"
        result = await run_orchestration("AAPL options, which calls to buy", "k", "parent-model", chat_id="216199859")

    prompt = mock_llm.call_args_list[0].args[0][0]["content"]
    assert "hire" in prompt
    assert "unrelated agent" in prompt
    row = get_subagent("options_analyst")
    assert row["parent_id"] == "desk"
    assert row["origin"] == "auto"
    assert "options" in (row["hire_reason"] or "").lower()
    assert row["last_used_at"]
    assert "agent_management" not in (row["skills"] or "")
    assert "shell_execution" not in (row["skills"] or "")
    assert "market_monitor" in row["skills"]
    assert "web_search" in row["skills"]
    assert mock_sub.called
    assert "New specialist" in result["response"]
    assert "options_analyst" in result["response"]
    assert "Hired" in _traces(result)


@pytest.mark.asyncio
async def test_second_identical_query_reuses_agent():
    _desk()
    plan = json.dumps(PLAN)
    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.agent.agent_instance._respond_as_subagent", new_callable=AsyncMock) as mock_sub, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.side_effect = [plan, "first", plan, "second"]
        mock_sub.return_value = "IV 22"
        await run_orchestration("AAPL options, which calls to buy", "k", "parent-model", chat_id="216199859")
        result = await run_orchestration("AAPL options, which calls to buy", "k", "parent-model", chat_id="216199859")

    rows = [a for a in get_all_subagents() if a["id"] == "options_analyst"]
    assert len(rows) == 1
    assert "Reused" in _traces(result)
    assert "New specialist" not in result["response"]


def test_skill_cap_strips_foreign_and_never_grants_agent_management():
    _desk()
    from backend.agent_factory import ensure_specialist
    row = ensure_specialist(
        {
            "id": "options_analyst",
            "name": "Options Analyst",
            "mandate": "Analyse option chains.",
            "skills": ["market_monitor", "web_search", "agent_management", "shell_execution"],
        },
        parent_id="desk",
        parent_skills="market_monitor,web_search,shell_execution",
        reason="gap",
    )
    assert row is not None
    skills = set(row["skills"].split(",")) if row["skills"] else set()
    assert skills == {"market_monitor", "web_search"}
    assert "agent_management" not in skills


@pytest.mark.asyncio
async def test_planner_crash_hires_on_gap_and_skips_fallback(fallback_spy):
    _desk()
    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.agent.agent_instance._respond_as_subagent", new_callable=AsyncMock) as mock_sub, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.side_effect = ImportError("cannot import name 'resolve_provider_model'")
        mock_sub.return_value = "IV 18 delta 0.3 strikes listed"
        result = await run_orchestration("AAPL options which calls to buy", "k", "parent-model", chat_id="216199859")

    assert fallback_spy == []
    row = get_subagent("options_analyst") or next(
        (a for a in get_all_subagents() if a.get("origin") == "auto"), None
    )
    assert row and row["parent_id"] == "desk"
    assert "IV 18" in result["response"]
    assert "New specialist" in result["response"]


@pytest.mark.asyncio
async def test_planner_crash_without_gap_uses_fallback(fallback_spy):
    _desk()
    save_subagent(
        "forecast", "Search", "You answer weather forecasts.", "parent-model",
        agent_type="agent", parent_id="desk", skills="web_search", x=400, y=220,
    )
    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.agent.agent_instance._respond_as_subagent", new_callable=AsyncMock) as mock_sub, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.side_effect = ImportError("down")
        mock_sub.return_value = "sunny"
        await run_orchestration("what is the weather", "k", "parent-model", chat_id="216199859")

    assert fallback_spy
    assert all(g in (None, "") for g in fallback_spy)


@pytest.mark.asyncio
async def test_auto_hire_off_reports_gap_without_creating(monkeypatch):
    monkeypatch.setenv("AUTO_HIRE", "off")
    _desk()
    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.return_value = json.dumps(PLAN)
        result = await run_orchestration("AAPL options, which calls to buy", "k", "parent-model", chat_id="216199859")

    assert get_subagent("options_analyst") is None
    assert "specialist" in result["response"].lower()
    assert "options" in result["response"].lower()


@pytest.mark.asyncio
async def test_rate_limit_escalates_to_parent(monkeypatch):
    monkeypatch.setenv("AUTO_HIRE_MAX_PER_DAY", "1")
    save_subagent(
        "root", "Root", "Root orchestrator.", "parent-model",
        agent_type="orchestrator", parent_id=None, skills="market_monitor,web_search", x=0, y=0,
    )
    _desk(parent_id="root")
    save_subagent(
        "already", "Already", "existing auto hire", "parent-model",
        agent_type="agent", parent_id="desk", skills="market_monitor", x=400, y=300,
        origin="auto", hire_reason="seed",
    )
    plan = json.dumps({
        "hire": [{
            "id": "vol_analyst",
            "name": "Vol Analyst",
            "mandate": "Implied volatility only.",
            "skills": ["market_monitor"],
            "reason": "No vol desk.",
        }],
        "steps": [{"agent": "vol_analyst", "instructions": "Read IV."}],
    })
    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.agent.agent_instance._respond_as_subagent", new_callable=AsyncMock) as mock_sub, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.side_effect = [plan, "iv done"]
        mock_sub.return_value = "iv 20"
        await run_orchestration("need implied volatility", "k", "parent-model", chat_id="216199859")

    row = get_subagent("vol_analyst")
    assert row["parent_id"] == "root"
    assert row["origin"] == "auto"


@pytest.mark.asyncio
async def test_parent_cycle_is_caught_by_stack(monkeypatch):
    monkeypatch.setenv("AUTO_HIRE_MAX_PER_DAY", "1")
    save_subagent(
        "root", "Root", "Root.", "parent-model",
        agent_type="orchestrator", parent_id=None, skills="market_monitor", x=0, y=0,
    )
    _desk(parent_id="root")
    from backend.database import _execute
    _execute("UPDATE subagents SET parent_id = ? WHERE id = ?", ("desk", "root"))
    save_subagent(
        "full_desk", "Full Desk", "seed", "m",
        agent_type="agent", parent_id="desk", skills="", origin="auto", hire_reason="seed",
    )
    save_subagent(
        "full_root", "Full Root", "seed", "m",
        agent_type="agent", parent_id="root", skills="", origin="auto", hire_reason="seed",
    )
    plan = json.dumps({
        "hire": [{"id": "newbie", "name": "Newbie", "mandate": "Brand new competence xyzzy.", "skills": [], "reason": "missing"}],
        "steps": [{"agent": "newbie", "instructions": "do it"}],
    })
    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.return_value = plan
        result = await run_orchestration("xyzzy competence", "k", "parent-model", chat_id="216199859")

    assert get_subagent("newbie") is None
    assert "cycle" in (result["response"] + _traces(result)).lower()


def test_create_subagent_uses_factory_dedup_and_caps():
    _desk(skills="web_search,market_monitor")
    save_subagent(
        "options_analyst", "Options Analyst", "Analyse option chains.", "m",
        agent_type="agent", parent_id="desk", skills="market_monitor",
    )
    reused = create_subagent(
        "options_new", "Options Analyst", "Analyse option chains.",
        parent_id="desk", skills="web_search,agent_management,shell_execution",
    )
    assert get_subagent("options_new") is None
    assert "options_analyst" in reused

    created = create_subagent(
        "news_bot", "News Bot", "Read the news wires.",
        parent_id="desk", skills="web_search,agent_management,shell_execution",
    )
    row = get_subagent("news_bot")
    assert row["parent_id"] == "desk"
    assert row["origin"] == "manual"
    assert row["skills"] == "web_search"
    assert "created" in created or "news_bot" in created


def test_fallback_hook_returns_none_when_gap_set():
    assert hook("fallback_plan_steps", "buy calls", [], "", gap="options", default=None) is None


def test_getters_return_hire_columns_and_unused_list():
    save_subagent(
        "old_auto", "Old", "mandate", "m",
        agent_type="agent", parent_id="desk", skills="", origin="auto", hire_reason="because",
    )
    save_subagent(
        "hand", "Hand", "mandate", "m",
        agent_type="agent", parent_id="desk", skills="",
    )
    got = get_subagent("old_auto")
    assert got["origin"] == "auto"
    assert got["hire_reason"] == "because"
    assert got["last_used_at"] in (None, "")
    unused = [a["id"] for a in list_unused_auto_agents()]
    assert unused == ["old_auto"]


def test_orchestrator_always_has_agent_management():
    from backend.agent import management_tools_for
    tools = management_tools_for({"id": "desk", "agent_type": "orchestrator", "skills": "web_search"})
    assert "create_subagent" in tools
    assert "list_subagents" in tools
    assert "call_subagent" in tools
    assert management_tools_for({"id": "quant", "agent_type": "agent", "skills": ""}) == set()
    assert management_tools_for({"id": "x_orchestrator", "agent_type": "agent"}) == set()
    assert "create_subagent" in management_tools_for({"agent_type": "sub-orchestrator"})


def _no_plugins(monkeypatch):
    monkeypatch.setattr("backend.agent_factory.collect", lambda *a, **k: [])
    monkeypatch.setattr("backend.agent_factory.hook", lambda *a, default=None, **k: default)


def test_gap_is_generic_without_plugins(monkeypatch):
    _no_plugins(monkeypatch)
    from backend.agent_factory import gap_spec, keyword_gap
    spec = gap_spec("AAPL calls", "options", "")
    assert spec["id"] == "options"
    assert keyword_gap("the market", []) == "market"


def test_plugin_gap_hooks_win(monkeypatch):
    def _hook(name, *args, default=None, **kwargs):
        if name == "gap_spec":
            return {"id": "custom_one", "name": "Custom"}
        return default

    def _collect(name, *args, **kwargs):
        if name == "gap_stopwords":
            return [("market",)]
        return []

    monkeypatch.setattr("backend.agent_factory.hook", _hook)
    monkeypatch.setattr("backend.agent_factory.collect", _collect)
    from backend.agent_factory import gap_spec, keyword_gap
    assert gap_spec("q", "options", "")["id"] == "custom_one"
    assert keyword_gap("the market", []) is None


def test_unused_flag_handles_str_and_datetime():
    from backend.database import _is_unused_auto
    old = datetime.now(timezone.utc) - timedelta(days=40)
    fresh = datetime.now(timezone.utc)
    assert _is_unused_auto("auto", None) is True
    assert _is_unused_auto("auto", old) is True
    assert _is_unused_auto("auto", old.strftime("%Y-%m-%d %H:%M:%S")) is True
    assert _is_unused_auto("auto", fresh) is False
    assert _is_unused_auto("manual", None) is False
    assert _is_unused_auto("manual", old) is False


def test_pending_prefix_migrates_to_hire_status():
    from backend.database import backfill_pending_hires
    save_subagent(
        "waiting", "Waiting", "mandate", "m",
        agent_type="agent", hire_reason="PENDING: x",
    )
    save_subagent(
        "x_orchestrator", "Named", "mandate", "m",
        agent_type="agent",
    )
    save_subagent("xorchestrator", "Plain", "mandate", "m", agent_type="agent")
    backfill_pending_hires()
    row = get_subagent("waiting")
    assert row["hire_status"] == "pending"
    assert row["hire_reason"] == "x"
    assert get_subagent("x_orchestrator")["agent_type"] == "orchestrator"
    assert get_subagent("xorchestrator")["agent_type"] == "agent"


@pytest.mark.asyncio
async def test_ask_mode_pending_until_confirm(monkeypatch):
    monkeypatch.setenv("AUTO_HIRE", "ask")
    _desk()
    plan = json.dumps(PLAN)
    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.agent.agent_instance._respond_as_subagent", new_callable=AsyncMock) as mock_sub, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.return_value = plan
        result = await run_orchestration("AAPL options, which calls to buy", "k", "parent-model", chat_id="216199859")

    row = get_subagent("options_analyst")
    assert row["hire_status"] == "pending"
    assert "PENDING:" not in (row["hire_reason"] or "")
    assert not mock_sub.called
    assert "confirm" in result["response"].lower()
    refused = json.loads(call_subagent("options_analyst", "go"))
    assert "error" in refused

    from fastapi.testclient import TestClient
    from backend.auth import active_sessions
    from backend.main import app
    active_sessions.add("test-token")
    client = TestClient(app)
    client.headers = {"Authorization": "Bearer test-token"}
    confirmed = client.post("/api/subagents/options_analyst/confirm")
    assert confirmed.status_code == 200
    assert get_subagent("options_analyst")["hire_status"] == "active"

    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.agent.agent_instance._respond_as_subagent", new_callable=AsyncMock) as mock_sub, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.side_effect = [plan, "IV 22 confirmed"]
        mock_sub.return_value = "IV 22"
        result = await run_orchestration("AAPL options, which calls to buy", "k", "parent-model", chat_id="216199859")
    assert mock_sub.called
    assert "IV 22" in result["response"]


@pytest.mark.asyncio
async def test_router_skips_pending_agent():
    _desk()
    save_subagent(
        "options_analyst", "Options Analyst", "Analyse option chains.", "m",
        agent_type="agent", parent_id="desk", skills="market_monitor", origin="auto",
    )
    from backend.database import set_hire_status
    set_hire_status("options_analyst", "pending")
    plan = json.dumps({"steps": [{"agent": "options_analyst", "instructions": "go"}]})
    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.agent.agent_instance._respond_as_subagent", new_callable=AsyncMock) as mock_sub, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.return_value = plan
        result = await run_orchestration("go", "k", "parent-model", chat_id="216199859")
    assert not mock_sub.called
    assert "confirm" in result["response"].lower()


@pytest.mark.asyncio
async def test_unset_auto_hire_defaults_to_ask(monkeypatch):
    monkeypatch.delenv("AUTO_HIRE", raising=False)
    from backend.agent_factory import auto_hire_mode
    assert auto_hire_mode() == "ask"
    _desk()
    with patch("backend.orchestrator.call_llm", new_callable=AsyncMock) as mock_llm, \
         patch("backend.agent.agent_instance._respond_as_subagent", new_callable=AsyncMock) as mock_sub, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_llm.return_value = json.dumps(PLAN)
        await run_orchestration("AAPL options, which calls to buy", "k", "parent-model", chat_id="216199859")
    assert get_subagent("options_analyst")["hire_status"] == "pending"
    assert not mock_sub.called
