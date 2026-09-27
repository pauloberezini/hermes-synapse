import asyncio
import json
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from backend.subagents import call_llm
from backend.orchestrator import run_orchestration, AgentState


def _run_async(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()
    else:
        return asyncio.run(coro)


# ==============================================================================
# 1. IT TEST: call_llm reasoning extraction when content is empty or None
# ==============================================================================

def test_call_llm_extracts_reasoning_when_content_is_empty_it():
    """
    IT: When an LLM (e.g. Gemini 2.5 Flash, DeepSeek-R1, or OpenRouter reasoning models)
    returns an assistant message with content=None or content="" but has 'reasoning'
    or 'reasoning_content' or choices[0].text, call_llm must extract it rather than
    returning an empty string "".
    """
    async def _test():
        # Scenario A: 'reasoning' field present with content=None
        mock_resp_a = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "reasoning": "Reasoning tokens from Gemini/R1.",
                    }
                }
            ]
        }

        # Scenario B: 'reasoning_content' field present with content=""
        mock_resp_b = {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "reasoning_content": "Detailed reasoning output.",
                    }
                }
            ]
        }

        # Scenario C: text completion style choice
        mock_resp_c = {
            "choices": [
                {
                    "text": "Text completion format output."
                }
            ]
        }

        with patch("httpx.AsyncClient.post") as mock_post:
            # Test A
            req = httpx.Request("POST", "https://openrouter.ai/api/v1/chat/completions")
            mock_post.return_value = httpx.Response(200, json=mock_resp_a, request=req)
            res_a = await call_llm([{"role": "user", "content": "test"}], api_key="sk-test", model="google/gemini-2.5-flash")
            assert res_a == "Reasoning tokens from Gemini/R1."

            # Test B
            mock_post.return_value = httpx.Response(200, json=mock_resp_b, request=req)
            res_b = await call_llm([{"role": "user", "content": "test"}], api_key="sk-test", model="deepseek/deepseek-r1")
            assert res_b == "Detailed reasoning output."

            # Test C
            mock_post.return_value = httpx.Response(200, json=mock_resp_c, request=req)
            res_c = await call_llm([{"role": "user", "content": "test"}], api_key="sk-test", model="google/gemini-2.5-flash")
            assert res_c == "Text completion format output."

    _run_async(_test())


# ==============================================================================
# 2. IT TEST: call_llm blank response detection triggers fallback candidate
# ==============================================================================

def test_call_llm_blank_response_triggers_fallback_candidate_it():
    """
    IT: If a model returns an empty/whitespace-only response (content="", reasoning=""),
    call_llm must NOT return "" to caller. It must treat this as a failed response,
    log a warning, and fall back to the next model in the fallback chain.
    """
    async def _test():
        models_requested = []

        async def mock_post(url, json=None, headers=None):
            model = json.get("model")
            models_requested.append(model)
            req = httpx.Request("POST", url)

            if model == "deepseek/deepseek-chat":
                # Primary model returns empty content
                return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "   "}}]}, request=req)
            else:
                # Fallback model returns valid content
                return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Success from fallback!"}}]}, request=req)

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            with patch.dict("os.environ", {"LLM_FALLBACK_MODEL": "google/gemini-2.5-flash"}):
                res = await call_llm(
                    [{"role": "user", "content": "test"}],
                    api_key="sk-test",
                    model="deepseek/deepseek-chat"
                )

                assert res == "Success from fallback!"
                assert "deepseek/deepseek-chat" in models_requested
                assert "google/gemini-2.5-flash" in models_requested

    _run_async(_test())


# ==============================================================================
# 3. IT TEST: call_llm multi-model fallback chain prevents ping-ponging
# ==============================================================================

def test_call_llm_prevents_ping_pong_between_failing_models_it():
    """
    IT: When multiple models fail consecutively (e.g. 429), call_llm must progress
    forward through fallback_candidates without looping back to a previously failed model.
    """
    async def _test():
        models_called = []

        async def mock_post(url, json=None, headers=None):
            model = json.get("model")
            models_called.append(model)
            req = httpx.Request("POST", url)

            if model == "deepseek/deepseek-chat":
                # Model A: HTTP 429
                return httpx.Response(429, json={"error": {"message": "Rate limited"}}, request=req)
            elif model == "google/gemini-2.5-flash":
                # Model B: HTTP 429
                return httpx.Response(429, json={"error": {"message": "Rate limited"}}, request=req)
            elif model == "google/gemini-2.5-pro":
                # Model C: Succeeds
                return httpx.Response(200, json={"choices": [{"message": {"role": "assistant", "content": "Resolved by Model C"}}]}, request=req)
            return httpx.Response(500, request=req)

        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            with patch.dict("os.environ", {
                "LLM_FALLBACK_MODEL": "google/gemini-2.5-flash",
                "LLM_MODEL": "deepseek/deepseek-chat"
            }):
                res = await call_llm(
                    [{"role": "user", "content": "test"}],
                    api_key="sk-test",
                    model="deepseek/deepseek-chat"
                )

                assert res == "Resolved by Model C"
                # Check progression: deepseek-chat should not be retried after gemini-flash failed
                assert "deepseek/deepseek-chat" in models_called
                assert "google/gemini-2.5-flash" in models_called
                assert "google/gemini-2.5-pro" in models_called
                # Ensure no ping-pong: after gemini-flash, deepseek-chat was not selected again
                flash_idx = models_called.index("google/gemini-2.5-flash")
                assert "deepseek/deepseek-chat" not in models_called[flash_idx:]

    _run_async(_test())


# ==============================================================================
# 4. CROSS TEST: Orchestrator synthesis resilience with secondary fallback
# ==============================================================================

def test_orchestrator_synthesis_resilience_secondary_fallback_cross():
    """
    Cross: In run_orchestration, when sub-agents produce outputs, and the primary
    synthesis LLM call returns empty or fails, the orchestrator must utilize secondary
    synthesis fallback to produce a synthesized answer rather than falling back to
    unformatted raw stdout.
    """
    async def _test():
        call_count = 0
        models_called = []

        async def mock_call_llm(messages, api_key, model, **kwargs):
            nonlocal call_count
            call_count += 1
            models_called.append(model)

            # Step 1: Planning step
            if any("EXCLUSIVELY in JSON" in m.get("content", "") for m in messages if m.get("role") == "system"):
                return json.dumps({
                    "steps": [
                        {"agent": "research", "instructions": "Fetch test market quotes"}
                    ]
                })

            # Synthesis step:
            # Primary synthesis model fails / returns empty
            if model == "deepseek/deepseek-chat":
                raise Exception("Synthesis primary model timeout")

            # Fallback synthesis model succeeds
            return "### Synthesized Market Summary\nAll assets are in normal trading range."

        with patch("backend.orchestrator.call_llm", side_effect=mock_call_llm):
            with patch("backend.subagents.ResearchAgent.run", new_callable=AsyncMock) as mock_exec:
                mock_exec.return_value = "Market data: BTC at $95,000, ETH at $2,700."

                with patch.dict("os.environ", {"LLM_FALLBACK_MODEL": "google/gemini-2.5-flash"}):
                    res = await run_orchestration(
                        query="Give me a market update",
                        api_key="sk-test",
                        model="deepseek/deepseek-chat",
                        chat_id="test_chat_synthesis"
                    )

                    assert "response" in res
                    final_resp = res["response"]
                    # Must be synthesized, NOT raw sub-agent dump
                    assert "### Synthesized Market Summary" in final_resp
                    assert "All assets are in normal trading range." in final_resp
                    assert "### Sub-agents execution results:" not in final_resp

    _run_async(_test())


# ==============================================================================
# 5. CROSS TEST: Orchestrator synthesis clean formatting when all models fail
# ==============================================================================

def test_orchestrator_synthesis_clean_formatting_when_all_fail_cross():
    """
    Cross: In run_orchestration, if all synthesis attempts fail, the final response
    must be cleanly structured with subagent result sections rather than an unformatted
    stdout dump.
    """
    async def _test():
        async def mock_call_llm(messages, api_key, model, **kwargs):
            # Planning step succeeds
            if any("EXCLUSIVELY in JSON" in m.get("content", "") for m in messages if m.get("role") == "system"):
                return json.dumps({
                    "steps": [
                        {"agent": "research", "instructions": "Search news"},
                        {"agent": "code", "instructions": "Run calculations"}
                    ]
                })

            # All synthesis attempts fail
            raise Exception("All synthesis models unavailable")

        with patch("backend.orchestrator.call_llm", side_effect=mock_call_llm):
            with patch("backend.subagents.ResearchAgent.run", new_callable=AsyncMock) as mock_res:
                mock_res.return_value = "Search result: Key inflation report released."

                with patch("backend.subagents.CodeAgent.run_and_correct", new_callable=AsyncMock) as mock_code:
                    mock_code.return_value = {
                        "stdout": "Calculated volatility index: 14.2",
                        "success": True,
                        "code": "print('Calculated volatility index: 14.2')",
                        "attempts": 1
                    }

                    res = await run_orchestration(
                        query="Analyze inflation data",
                        api_key="sk-test",
                        model="deepseek/deepseek-chat",
                        chat_id="test_chat_clean_fallback"
                    )

                    final_resp = res["response"]
                    # Must contain structured markdown headers for the subagent results
                    assert "Search Agent" in final_resp or "research" in final_resp.lower()
                    assert "Key inflation report released" in final_resp
                    assert "Calculated volatility index: 14.2" in final_resp

    _run_async(_test())
