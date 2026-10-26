"""
Integration (IT) and Cross-Subsystem Tests for Docker jarvis-backend live log issues.

Validates:
1. IT: Subagent fast-fallback on HTTP 404 (model unavailable) without wasteful retry loops.
2. IT: Subagent pre-invocation model resolution mapping aliases (deepseek/deepseek-r1 -> deepseek/deepseek-r1-0528).
3. Cross: Subagent DB migration and fallback execution across Orchestrator -> Subagent.
4. Cross: Database undistilled log safety against tuple index errors.
5. Cross: Skill loop scheduled automation skipping at INFO level.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from backend.agent import JarvisAgent
from backend.database import _parse_decision_log_candidate, _migrate_deprecated_subagent_models
from backend.skill_loop import _is_scheduled_automation_log
from backend.llm_model_manager import (
    resolve_provider_model,
    resolve_provider_models,
    is_model_unavailable_error,
    is_model_rate_limited,
    mark_model_rate_limited,
    reset_endpoint_cooldowns,
)


# =====================================================================
# 1. IT: Subagent Fast-Fallback on Model Unavailable (HTTP 404)
# =====================================================================

@pytest.mark.asyncio
async def test_it_subagent_fast_fallback_on_404_no_wasteful_retries():
    """
    IT: Reproduces Docker live log issue:
    Subagent 'Quant Analyst' (deepseek/deepseek-r1) API returned 404 (attempt 1/2):
    {"error":{"message":"deepseek/deepseek-r1 is no longer available on OpenRouter...

    Verifies:
    - 404 model unavailable error triggers fast-fallback to the next candidate model.
    - No wasteful second retry occurs for the dead model (attempt 1/2 breaks immediately).
    - The unavailable model is marked rate-limited / unavailable.
    - Subagent successfully returns the result from the healthy fallback candidate model.
    """
    reset_endpoint_cooldowns()

    agent = JarvisAgent(
        model="deepseek/deepseek-chat",
        api_key="test-api-key",
        api_base="https://openrouter.ai/api/v1",
    )

    unavailable_model = "deepseek/deepseek-r1-test-unavail"
    fallback_model = "deepseek/deepseek-chat"

    subagent_def = {
        "id": "quant_analyst",
        "name": "Quant Analyst",
        "model": unavailable_model,
        "system_prompt": "You are a quantitative market analyst.",
        "skills": "market-analyst",
        "tools": [],
    }

    call_count = {"unavailable": 0, "fallback": 0}

    async def mock_post(url, headers=None, json=None, timeout=None):
        req_model = json.get("model")
        mock_resp = MagicMock()
        if req_model == unavailable_model:
            call_count["unavailable"] += 1
            mock_resp.status_code = 404
            mock_resp.text = (
                '{"error":{"message":"deepseek/deepseek-r1-test-unavail is no longer available on OpenRouter: '
                'no provider serves this model anymore. See available models at https://openrouter.ai/models","code":404}}'
            )
            mock_resp.json.return_value = {
                "error": {
                    "message": "deepseek/deepseek-r1-test-unavail is no longer available on OpenRouter: no provider serves this model anymore.",
                    "code": 404,
                }
            }
        else:
            call_count["fallback"] += 1
            mock_resp.status_code = 200
            mock_resp.text = '{"choices":[{"message":{"content":"Technical indicators: RSI 58.5, MACD Bullish"}}]}'
            mock_resp.json.return_value = {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Technical indicators: RSI 58.5, MACD Bullish",
                        }
                    }
                ]
            }
        return mock_resp

    with patch("httpx.AsyncClient.post", side_effect=mock_post), \
         patch("backend.rag.search_memory", return_value=[]), \
         patch("backend.database.save_message", return_value=123), \
         patch("backend.database.get_chat_history", return_value=[]), \
         patch("backend.governance.BudgetGuard.check", return_value=True), \
         patch("backend.activity_logger.log_activity", return_value=None), \
         patch.dict("os.environ", {"LLM_FALLBACK_MODEL": fallback_model}):
        
        result = await agent._respond_as_subagent(
            user_message="Analyze AUDUSD technicals",
            subagent=subagent_def,
            include_history=False,
        )

    # 1. Dead model should only be called ONCE before fast-fallback
    assert call_count["unavailable"] == 1, (
        f"Expected dead model to be called exactly once before fast-fallback, called {call_count['unavailable']} times"
    )
    # 2. Fallback model was called and succeeded
    assert call_count["fallback"] == 1
    assert "Technical indicators: RSI 58.5" in result
    # 3. Dead model marked as unavailable
    assert is_model_rate_limited(unavailable_model) is True


# =====================================================================
# 2. IT: Subagent Pre-invocation Model Resolution
# =====================================================================

def test_it_resolve_provider_model_maps_deprecated_slugs():
    """
    IT: Verifies that resolve_provider_model and resolve_provider_models correctly
    map legacy/unserved OpenRouter slugs to healthy supported models before dispatch.
    """
    assert resolve_provider_model("deepseek/deepseek-r1", "https://openrouter.ai/api/v1") == "deepseek/deepseek-r1-0528"
    assert resolve_provider_model("deepseek/deepseek-r1:free", "https://openrouter.ai/api/v1") == "deepseek/deepseek-r1-0528"

    resolved_list = resolve_provider_models(
        ["deepseek/deepseek-r1", "deepseek/deepseek-chat"],
        "https://openrouter.ai/api/v1",
    )
    assert resolved_list == ["deepseek/deepseek-r1-0528", "deepseek/deepseek-chat"]


# =====================================================================
# 3. Cross: Subagent DB Model Migration & Fallback Execution
# =====================================================================

def test_cross_subagent_db_migration_and_execution():
    """
    Cross: Verifies that database subagent model migration updates deprecated models
    across subagent records.
    """
    mock_cursor = MagicMock()
    _migrate_deprecated_subagent_models(mock_cursor, "%s")

    update_calls = [c for c in mock_cursor.execute.call_args_list if "UPDATE subagents" in str(c)]
    assert len(update_calls) == 2
    # Verify mapping queries for deepseek/deepseek-r1
    assert any("deepseek/deepseek-r1-0528" in str(c) for c in update_calls)


# =====================================================================
# 4. Cross: Database Undistilled Log Tuple Bounds Safety
# =====================================================================

def test_cross_database_undistilled_log_tuple_bounds_safety():
    """
    Cross: Verifies that _parse_decision_log_candidate does not raise IndexError
    when encountering empty or partial database rows.
    """
    assert _parse_decision_log_candidate(()) is None
    assert _parse_decision_log_candidate((1, "2026-10-24 10:00:00", "task_session")) is None
    assert _parse_decision_log_candidate(("not-an-id",)) is None


# =====================================================================
# 5. Cross: Skill Loop Scheduled Automation Log Skipping at INFO Level
# =====================================================================

def test_cross_skill_distiller_scheduled_automation_skipped_at_info():
    """
    Cross: Verifies that scheduled automation logs (task_session_*, scheduled=1)
    are identified as automation runs to prevent logging misleading [ERROR] messages.
    """
    row_scheduled_session = {
        "id": 2355,
        "session_id": "task_session_london",
        "description": "Session (London)",
        "content": "Confluence scan complete",
    }
    assert _is_scheduled_automation_log(row_scheduled_session) is True

    row_user_chat = {
        "id": 2356,
        "session_id": "user_session_456",
        "description": "User requested trade check",
        "content": "Can you check BTC?",
    }
    assert _is_scheduled_automation_log(row_user_chat) is False
