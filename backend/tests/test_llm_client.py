"""Unit + integration tests for the normalized LLM client (P0)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend import llm_client as lc
from backend.llm_client import (
    NormalizedLLMResponse,
    call_llm_normalized,
    mask_secrets,
    normalize_openai_response,
    normalize_stream_chunks,
)


def _make_body(content=None, tool_calls=None, finish_reason="stop", usage=None,
               refusal=None, reasoning=None):
    message = {"role": "assistant"}
    if content is not None:
        message["content"] = content
    if tool_calls is not None:
        message["tool_calls"] = tool_calls
    if refusal is not None:
        message["refusal"] = refusal
    if reasoning is not None:
        message["reasoning"] = reasoning
    body = {"choices": [{"message": message, "finish_reason": finish_reason}]}
    if usage is not None:
        body["usage"] = usage
    return body


# ── normalize_openai_response: response variants ──────────────────────────────

def test_normalize_plain_text_success():
    r = normalize_openai_response(
        _make_body("Готово, Сэр.", usage={"prompt_tokens": 10, "completion_tokens": 5}),
        provider="openrouter", model="m",
    )
    assert r.status == lc.STATUS_SUCCESS
    assert r.content == "Готово, Сэр."
    assert r.usage.input_tokens == 10
    assert r.usage.output_tokens == 5


def test_normalize_content_block_array():
    r = normalize_openai_response(
        _make_body([{"type": "text", "text": "Часть 1"}, {"type": "text", "text": "Часть 2"}]),
        provider="p", model="m",
    )
    assert r.status == lc.STATUS_SUCCESS
    assert "Часть 1" in r.content and "Часть 2" in r.content


def test_normalize_tool_call_without_text_is_tool_call_not_empty():
    tool_calls = [{"id": "c1", "type": "function",
                   "function": {"name": "get_weather", "arguments": {"location": "Minsk"}}}]
    r = normalize_openai_response(_make_body(None, tool_calls=tool_calls),
                                  provider="p", model="m")
    assert r.status == lc.STATUS_TOOL_CALL
    assert r.has_tool_calls
    assert r.status != lc.STATUS_EMPTY


def test_normalize_empty_content():
    r = normalize_openai_response(_make_body(None), provider="p", model="m")
    assert r.status == lc.STATUS_EMPTY
    assert r.error_message


def test_normalize_reasoning_only_is_empty_but_keeps_reasoning():
    r = normalize_openai_response(_make_body(None, reasoning="думаю..."),
                                  provider="p", model="m")
    assert r.status == lc.STATUS_EMPTY
    assert r.reasoning == "думаю..."


def test_normalize_refusal_field():
    r = normalize_openai_response(_make_body(None, refusal="I can't help with that."),
                                  provider="p", model="m")
    assert r.status == lc.STATUS_REFUSAL
    assert r.content == "I can't help with that."


def test_normalize_content_filter_finish_reason():
    r = normalize_openai_response(_make_body(None, finish_reason="content_filter"),
                                  provider="p", model="m")
    assert r.status == lc.STATUS_REFUSAL


def test_normalize_length_truncation_is_empty_with_reason():
    r = normalize_openai_response(_make_body(None, finish_reason="length"),
                                  provider="p", model="m")
    assert r.status == lc.STATUS_EMPTY
    assert "truncat" in (r.error_message or "").lower()


def test_normalize_malformed_no_choices_is_parse_error():
    r = normalize_openai_response({"id": "x"}, provider="p", model="m")
    assert r.status == lc.STATUS_PARSE_ERROR


def test_reasoning_only_visible_answer_kept():
    # An unfinished <think> block with a trailing visible answer keeps the answer.
    r = normalize_openai_response(
        _make_body("<think>план...\nОтвет: Привет, Сэр."),
        provider="p", model="m",
    )
    # cleanup keeps text after unfinished think; may or may not strip marker but
    # must not be empty.
    assert r.status in (lc.STATUS_SUCCESS,)
    assert r.content.strip()


# ── Secret masking ────────────────────────────────────────────────────────────

def test_mask_secrets_bearer_and_keys():
    assert "REDACTED" in mask_secrets("Authorization: Bearer sk-or-abcdef123456")
    assert "sk-or-abcdef123456" not in mask_secrets("Bearer sk-or-abcdef123456")
    assert "REDACTED" in mask_secrets('{"api_key": "supersecretvalue"}')


# ── call_llm_normalized: HTTP integration (mocked) ────────────────────────────

def _mock_response(status_code=200, json_body=None, headers=None, text=""):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.headers = headers or {}
    resp.json.return_value = json_body or {}
    resp.text = text
    return resp


@pytest.mark.asyncio
async def test_call_success():
    resp = _mock_response(200, _make_body("Привет, Сэр.", usage={"prompt_tokens": 3, "completion_tokens": 2}),
                          headers={"x-request-id": "req_123"})
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=resp)):
        r = await call_llm_normalized(
            api_base="https://openrouter.ai/api/v1", api_key="k", model="m",
            messages=[{"role": "user", "content": "hi"}], max_retries=0,
        )
    assert r.status == lc.STATUS_SUCCESS
    assert r.content == "Привет, Сэр."
    assert r.request_id == "req_123"
    assert r.latency_ms is not None


@pytest.mark.asyncio
async def test_call_timeout_retries_then_fails():
    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=httpx.TimeoutException("t"))), \
         patch("backend.llm_client._backoff_delay", return_value=0):
        r = await call_llm_normalized(
            api_base="https://openrouter.ai/api/v1", api_key="k", model="m",
            messages=[{"role": "user", "content": "hi"}], max_retries=2,
        )
    assert r.status == lc.STATUS_TIMEOUT
    assert r.retry_count == 2


@pytest.mark.asyncio
async def test_call_provider_error_non_retryable_fails_fast():
    resp = _mock_response(400, {}, text="bad request Bearer sk-secret123456")
    post = AsyncMock(return_value=resp)
    with patch("httpx.AsyncClient.post", new=post):
        r = await call_llm_normalized(
            api_base="https://openrouter.ai/api/v1", api_key="k", model="m",
            messages=[{"role": "user", "content": "hi"}], max_retries=3,
        )
    assert r.status == lc.STATUS_PROVIDER_ERROR
    assert post.call_count == 1  # 400 is not retried
    # error message must not leak the body/secret
    assert "sk-secret" not in (r.error_message or "")


@pytest.mark.asyncio
async def test_call_5xx_retries():
    resp = _mock_response(503, {}, text="unavailable")
    post = AsyncMock(return_value=resp)
    with patch("httpx.AsyncClient.post", new=post), \
         patch("backend.llm_client._backoff_delay", return_value=0):
        r = await call_llm_normalized(
            api_base="https://openrouter.ai/api/v1", api_key="k", model="m",
            messages=[{"role": "user", "content": "hi"}], max_retries=2,
        )
    assert r.status == lc.STATUS_PROVIDER_ERROR
    assert post.call_count == 3  # 1 + 2 retries


@pytest.mark.asyncio
async def test_call_parse_error():
    resp = _mock_response(200)
    resp.json.side_effect = ValueError("no json")
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=resp)):
        r = await call_llm_normalized(
            api_base="https://openrouter.ai/api/v1", api_key="k", model="m",
            messages=[{"role": "user", "content": "hi"}], max_retries=0,
        )
    assert r.status == lc.STATUS_PARSE_ERROR


@pytest.mark.asyncio
async def test_call_cancellation_propagates():
    async def _slow(*a, **k):
        await asyncio.sleep(10)

    with patch("httpx.AsyncClient.post", new=AsyncMock(side_effect=_slow)):
        task = asyncio.create_task(call_llm_normalized(
            api_base="https://openrouter.ai/api/v1", api_key="k", model="m",
            messages=[{"role": "user", "content": "hi"}], max_retries=0,
        ))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


def test_public_dict_has_no_raw_body():
    r = NormalizedLLMResponse(status=lc.STATUS_SUCCESS, provider="p", model="m",
                              content="x", raw_response={"secret": "body"})
    public = r.to_public_dict()
    assert "raw_response" not in public
    assert public["status"] == lc.STATUS_SUCCESS


def test_normalize_streaming_chunks():
    result = normalize_stream_chunks([
        {"choices": [{"delta": {"content": "При"}, "finish_reason": None}]},
        {"choices": [{"delta": {"content": "вет"}, "finish_reason": "stop"}],
         "usage": {"prompt_tokens": 2, "completion_tokens": 2}},
    ], provider="p", model="m")
    assert result.status == lc.STATUS_SUCCESS
    assert result.content == "Привет"
    assert result.usage.total_tokens is None


def test_interrupted_stream_is_provider_error():
    result = normalize_stream_chunks([
        {"choices": [{"delta": {"content": "partial"}, "finish_reason": None}]},
    ], provider="p", model="m")
    assert result.status == lc.STATUS_PROVIDER_ERROR
    assert result.content == "partial"
