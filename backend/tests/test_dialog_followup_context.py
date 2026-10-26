"""A short reply to an assistant question keeps that question on the planner query."""

from unittest.mock import AsyncMock, patch

import pytest

from backend.context_manager import continuation_query
from backend.orchestrator import run_orchestration

USER = "да проверь пожалуйста и отвечай мне на руском"
QUESTION = "Would you like me to query similar historical market conditions for further insights?"


def _report() -> str:
    head = "HEAD_NOT_IN_TAIL " + ("x" * 1600)
    return f"{head}\nAUDUSD report.\n{QUESTION}"


@pytest.fixture
def incident_history() -> list[dict[str, str]]:
    return [
        {"role": "assistant", "content": _report()},
        {"role": "user", "content": USER},
    ]


def _stub_history(monkeypatch: pytest.MonkeyPatch, history: list) -> None:
    monkeypatch.setattr("backend.database.get_chat_history", lambda *a, **k: history)
    monkeypatch.setattr("backend.plugins.tool_hints", lambda: {})


def test_incident_reply_keeps_question_tail(monkeypatch: pytest.MonkeyPatch, incident_history: list) -> None:
    _stub_history(monkeypatch, incident_history)
    wrapped = continuation_query(USER, "12225")
    assert wrapped.startswith("[Dialog continuation]\n")
    assert QUESTION in wrapped
    assert "AUDUSD" in wrapped
    assert "HEAD_NOT_IN_TAIL" not in wrapped
    assert wrapped.endswith(f"[Current user message]:\n{USER}")


def test_ticker_in_query_stays_raw(monkeypatch: pytest.MonkeyPatch, incident_history: list) -> None:
    monkeypatch.setattr(
        "backend.database.get_chat_history",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("symbol gate reads history")),
    )
    monkeypatch.setattr("backend.plugins.tool_hints", lambda: {"symbol_pattern": r"\b(AUDUSD|BTC)\b"})
    query = "check AUDUSD"
    assert continuation_query(query, "chat") == query


@pytest.mark.parametrize(
    ("query", "chat_id"),
    [
        ("да проверь", "task_abc"),
        ("Execute scheduled task: Autonomous AI Hedge Fund Manager", "chat"),
        ("да проверь", "desk_scheduled_1"),
    ],
)
def test_scheduled_turns_stay_raw(monkeypatch: pytest.MonkeyPatch, query: str, chat_id: str) -> None:
    monkeypatch.setattr(
        "backend.database.get_chat_history",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("scheduled gate reads history")),
    )
    assert continuation_query(query, chat_id) == query


def test_no_question_stays_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_history(
        monkeypatch,
        [
            {"role": "assistant", "content": "AUDUSD is flat."},
            {"role": "user", "content": "да"},
        ],
    )
    assert continuation_query("да", "chat") == "да"


def test_long_query_stays_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "backend.database.get_chat_history",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("length gate reads history")),
    )
    query = "да " + ("x" * 400)
    assert len(query) > 400
    assert continuation_query(query, "chat") == query


def test_query_at_cap_wraps(monkeypatch: pytest.MonkeyPatch) -> None:
    query = "д" + ("." * 399)
    assert len(query) == 400
    _stub_history(
        monkeypatch,
        [
            {"role": "assistant", "content": "Go ahead?"},
            {"role": "user", "content": query},
        ],
    )
    wrapped = continuation_query(query, "chat")
    assert wrapped.startswith("[Dialog continuation]\n")
    assert wrapped.endswith(query)


def test_history_error_returns_query(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: object, **_k: object) -> list:
        raise RuntimeError("db down")

    monkeypatch.setattr("backend.database.get_chat_history", _boom)
    monkeypatch.setattr("backend.plugins.tool_hints", lambda: {})
    assert continuation_query("да проверь", "chat") == "да проверь"


def test_empty_history_stays_raw(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_history(monkeypatch, [])
    assert continuation_query("да", "chat") == "да"


@pytest.mark.asyncio
async def test_run_orchestration_plans_the_wrapped_query() -> None:
    def marked(query: str, chat_id: str) -> str:
        assert chat_id == "chat-1"
        return f"MARKED {query}"

    plan = '{"steps": [{"agent": "research", "instructions": "look"}]}'
    with patch("backend.context_manager.continuation_query", side_effect=marked), \
         patch("backend.orchestrator.call_llm", side_effect=[plan, "done"]) as mock_call, \
         patch("backend.orchestrator.ResearchAgent.run", new_callable=AsyncMock) as mock_run, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock):
        mock_run.return_value = "found"
        result = await run_orchestration("hello", "k", "m", chat_id="chat-1")

    planner_user = mock_call.call_args_list[0].args[0][1]["content"]
    synth_user = mock_call.call_args_list[1].args[0][1]["content"]
    assert planner_user == "Query: MARKED hello"
    assert "Original query: \"MARKED hello\"" in synth_user
    mock_run.assert_called_once_with("look")
    assert result["response"] == "done"
