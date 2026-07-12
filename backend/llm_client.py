"""Unified LLM client with a normalized response contract.

This module centralizes the HTTP call to OpenAI-compatible (and Anthropic-style
``openmodel.ai``) chat endpoints and returns a single, well-typed
``NormalizedLLMResponse`` regardless of provider quirks.

Design goals (P0 audit — "empty model response" fix):

* Never silently collapse different failure modes into one "empty" answer.
  We distinguish: success / tool_call / empty / refusal / timeout /
  provider_error / parse_error.
* A tool-call turn with no visible text is NOT "empty" — it is ``tool_call``.
* Preserve reasoning text and content-block arrays instead of discarding them.
* Bounded retry with exponential backoff + jitter, only for *transient*
  failures (timeout / 429 / 5xx). Never retried by this layer after a
  side-effecting tool has already run (the caller controls that).
* Capture provider request id, finish reason, usage and latency.
* Mask secrets before anything is logged.

The module intentionally has no hard dependency on ``agent.py`` at import time;
provider translation + text extraction helpers are imported lazily so the two
modules do not create an import cycle.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("hermes.llm")

# ── Status taxonomy ───────────────────────────────────────────────────────────

STATUS_SUCCESS = "success"
STATUS_TOOL_CALL = "tool_call"
STATUS_EMPTY = "empty"
STATUS_REFUSAL = "refusal"
STATUS_TIMEOUT = "timeout"
STATUS_PROVIDER_ERROR = "provider_error"
STATUS_PARSE_ERROR = "parse_error"

# Statuses that are safe to retry with backoff (idempotent, transient).
_RETRYABLE_STATUSES = {STATUS_TIMEOUT, STATUS_PROVIDER_ERROR}
# HTTP statuses that are worth retrying.
_RETRYABLE_HTTP = {408, 409, 425, 429, 500, 502, 503, 504}


@dataclass
class LLMUsage:
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cost: Optional[float] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost": self.cost,
        }


@dataclass
class NormalizedLLMResponse:
    """Provider-agnostic normalized response.

    Mirrors the ``NormalizedLLMResponse`` TS type from the audit brief, adapted
    to Python naming.
    """

    status: str
    provider: str
    model: str
    content: Optional[str] = None
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    reasoning: Optional[str] = None
    finish_reason: Optional[str] = None
    request_id: Optional[str] = None
    usage: LLMUsage = field(default_factory=LLMUsage)
    latency_ms: Optional[int] = None
    retry_count: int = 0
    raw_response_available: bool = False
    # Human-safe, non-sensitive error summary (never contains secrets/bodies).
    error_message: Optional[str] = None
    # Kept in-process only for debugging; never serialized to the client.
    raw_response: Optional[Dict[str, Any]] = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    @property
    def is_success(self) -> bool:
        return self.status in (STATUS_SUCCESS, STATUS_TOOL_CALL)

    def to_public_dict(self) -> Dict[str, Any]:
        """Safe subset for logs / UI tech-details (no raw body, no secrets)."""
        return {
            "status": self.status,
            "provider": self.provider,
            "model": self.model,
            "finish_reason": self.finish_reason,
            "request_id": self.request_id,
            "usage": self.usage.as_dict(),
            "latency_ms": self.latency_ms,
            "retry_count": self.retry_count,
            "raw_response_available": self.raw_response_available,
            "has_tool_calls": self.has_tool_calls,
            "error_message": self.error_message,
        }


# ── Secret masking ────────────────────────────────────────────────────────────

_SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE),
    re.compile(r"(sk-[A-Za-z0-9]{2})[A-Za-z0-9\-]{6,}", re.IGNORECASE),
    re.compile(r"(sk-or-[A-Za-z0-9]{2})[A-Za-z0-9\-]{6,}", re.IGNORECASE),
    re.compile(r'((?:api[_-]?key|token|secret|password)"?\s*[:=]\s*"?)[^"\s,}]+', re.IGNORECASE),
]


def mask_secrets(text: Optional[str]) -> str:
    """Redact API keys / bearer tokens / obvious secrets from a string."""
    if not text:
        return ""
    masked = str(text)
    for pattern in _SECRET_PATTERNS:
        masked = pattern.sub(lambda m: f"{m.group(1)}***REDACTED***", masked)
    return masked


def _summarize_body(body: Optional[str], limit: int = 300) -> str:
    """Short, secret-masked summary of a provider body for server logs only."""
    if not body:
        return ""
    return mask_secrets(body)[:limit]


# ── Refusal detection ─────────────────────────────────────────────────────────

_REFUSAL_MARKERS = (
    "i can't help with that",
    "i cannot help with that",
    "i'm not able to help",
    "i am unable to assist",
    "i can't assist with",
    "не могу помочь с этим",
    "я не могу помочь",
    "это нарушает",
)


def _looks_like_refusal(text: str, finish_reason: Optional[str]) -> bool:
    if finish_reason in ("content_filter", "safety", "recitation"):
        return True
    lowered = (text or "").strip().lower()
    if not lowered:
        return False
    if len(lowered) > 400:  # long text is an answer, not a refusal boilerplate
        return False
    return any(marker in lowered for marker in _REFUSAL_MARKERS)


# ── Reasoning / content extraction ────────────────────────────────────────────

def _extract_reasoning(message: Dict[str, Any]) -> Optional[str]:
    """Pull reasoning text from the various provider shapes."""
    for key in ("reasoning", "reasoning_content", "thinking"):
        value = message.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    content = message.get("content")
    if isinstance(content, list):
        parts: List[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("reasoning", "thinking"):
                text = block.get("text") or block.get("content")
                if isinstance(text, str):
                    parts.append(text)
        if parts:
            return "\n".join(parts).strip()
    return None


# ── Configuration helpers ─────────────────────────────────────────────────────

def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def _float_env(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (TypeError, ValueError):
        return default


def get_request_timeout() -> float:
    return _float_env("LLM_REQUEST_TIMEOUT", 60.0)


def get_max_retries() -> int:
    # Number of *additional* attempts after the first, for transient errors.
    return max(0, min(5, _int_env("LLM_MAX_RETRIES", 2)))


def _provider_name(api_base: str, is_openmodel: bool) -> str:
    base = (api_base or "").lower()
    if is_openmodel:
        return "openmodel"
    if any(m in base for m in ("localhost", "127.0.0.1", "0.0.0.0", "ollama",
                               "lmstudio", "lm-studio", "localai", "vllm",
                               "host.docker.internal")):
        return "local"
    if "openrouter" in base:
        return "openrouter"
    return "provider"


def _extract_request_id(response: httpx.Response, data: Dict[str, Any]) -> Optional[str]:
    for header in ("x-request-id", "x-request-id", "request-id", "openai-request-id"):
        value = response.headers.get(header)
        if value:
            return value
    rid = data.get("id") if isinstance(data, dict) else None
    return rid if isinstance(rid, str) else None


def _backoff_delay(attempt: int, base: float = 0.5, cap: float = 8.0) -> float:
    """Exponential backoff with full jitter."""
    expo = min(cap, base * (2 ** attempt))
    return random.uniform(0.0, expo)


# ── Core parse: single provider payload → NormalizedLLMResponse ───────────────

def normalize_openai_response(
    data: Dict[str, Any],
    *,
    provider: str,
    model: str,
    request_id: Optional[str] = None,
    latency_ms: Optional[int] = None,
    retry_count: int = 0,
) -> NormalizedLLMResponse:
    """Turn a parsed OpenAI-compatible JSON body into a normalized response.

    Imports agent helpers lazily to avoid an import cycle.
    """
    from backend.agent import (  # local import — avoids circular dependency
        _clean_model_output,
        _extract_message_text,
        _normalize_tool_calls,
    )

    resp = NormalizedLLMResponse(
        status=STATUS_EMPTY,
        provider=provider,
        model=model,
        request_id=request_id,
        latency_ms=latency_ms,
        retry_count=retry_count,
        raw_response_available=True,
        raw_response=data,
    )

    usage = data.get("usage") or {}
    if isinstance(usage, dict):
        resp.usage.input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        resp.usage.output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
        resp.usage.total_tokens = usage.get("total_tokens")

    choices = data.get("choices")
    if not isinstance(choices, list) or not choices:
        resp.status = STATUS_PARSE_ERROR
        resp.error_message = "Provider returned no choices."
        return resp

    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
    resp.finish_reason = choice.get("finish_reason") or choice.get("stop_reason")

    # Tool calls first — a tool call turn is never "empty".
    resp.tool_calls = _normalize_tool_calls(message.get("tool_calls"))

    # Reasoning (kept, not discarded).
    resp.reasoning = _extract_reasoning(message)

    # Explicit refusal field (OpenAI style).
    refusal = message.get("refusal")
    if isinstance(refusal, str) and refusal.strip():
        resp.status = STATUS_REFUSAL
        resp.content = refusal.strip()
        return resp

    raw_text = _extract_message_text(message.get("content"))
    cleaned = _clean_model_output(raw_text)
    # Non-destructive fallback: if cleanup nukes everything but the model DID
    # return visible text, keep the raw visible text rather than "".
    if not cleaned.strip() and raw_text.strip():
        cleaned = raw_text.strip()
    resp.content = cleaned

    if resp.tool_calls:
        resp.status = STATUS_TOOL_CALL
        return resp

    if cleaned.strip():
        if _looks_like_refusal(cleaned, resp.finish_reason):
            resp.status = STATUS_REFUSAL
        else:
            resp.status = STATUS_SUCCESS
        return resp

    # No visible text and no tool calls.
    if resp.finish_reason in ("content_filter", "safety", "recitation"):
        resp.status = STATUS_REFUSAL
        resp.error_message = f"Blocked by provider safety filter ({resp.finish_reason})."
    elif resp.reasoning:
        # Reasoning-only: treat as empty so caller can retry for a visible answer,
        # but record the finish reason for diagnostics.
        resp.status = STATUS_EMPTY
        resp.error_message = "Model returned reasoning only, no visible answer."
    else:
        resp.status = STATUS_EMPTY
        if resp.finish_reason == "length":
            resp.error_message = "Response truncated (max_tokens reached) before any text."
        else:
            resp.error_message = "Provider returned an empty message content."
    return resp


def normalize_stream_chunks(
    chunks: List[Dict[str, Any]], *, provider: str, model: str,
    request_id: Optional[str] = None, latency_ms: Optional[int] = None,
) -> NormalizedLLMResponse:
    """Collapse captured OpenAI-compatible SSE chunks into the same contract.

    Transport code can feed decoded ``data:`` payloads here. An interrupted
    stream without a terminal finish reason is classified as ``provider_error``
    instead of being mistaken for a successful empty response.
    """
    content: List[str] = []
    reasoning: List[str] = []
    tool_calls: Dict[int, Dict[str, Any]] = {}
    finish_reason: Optional[str] = None
    usage: Dict[str, Any] = {}
    saw_choice = False
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        usage.update(chunk.get("usage") or {})
        choices = chunk.get("choices") or []
        if not choices or not isinstance(choices[0], dict):
            continue
        saw_choice = True
        choice = choices[0]
        finish_reason = choice.get("finish_reason") or finish_reason
        delta = choice.get("delta") if isinstance(choice.get("delta"), dict) else {}
        text = delta.get("content")
        if isinstance(text, str):
            content.append(text)
        thought = delta.get("reasoning") or delta.get("reasoning_content")
        if isinstance(thought, str):
            reasoning.append(thought)
        for call in delta.get("tool_calls") or []:
            if not isinstance(call, dict):
                continue
            idx = int(call.get("index", 0))
            current = tool_calls.setdefault(idx, {"id": call.get("id") or f"call_{idx}", "type": "function", "function": {"name": "", "arguments": ""}})
            fn = call.get("function") or {}
            current["function"]["name"] += fn.get("name") or ""
            current["function"]["arguments"] += fn.get("arguments") or ""
    if not saw_choice or finish_reason is None:
        return NormalizedLLMResponse(
            status=STATUS_PROVIDER_ERROR, provider=provider, model=model,
            content="".join(content) or None, reasoning="".join(reasoning) or None,
            request_id=request_id, latency_ms=latency_ms,
            raw_response_available=bool(chunks),
            error_message="Model stream ended before a terminal chunk.",
        )
    body = {
        "choices": [{"message": {"content": "".join(content), "reasoning": "".join(reasoning) or None,
                                    "tool_calls": list(tool_calls.values())},
                     "finish_reason": finish_reason}],
        "usage": usage,
    }
    return normalize_openai_response(body, provider=provider, model=model,
                                     request_id=request_id, latency_ms=latency_ms)


# ── Public async entry point ──────────────────────────────────────────────────

async def call_llm_normalized(
    *,
    api_base: str,
    api_key: str,
    model: str,
    messages: List[Dict[str, Any]],
    temperature: float = 0.2,
    max_tokens: Optional[int] = None,
    tools: Optional[List[Dict[str, Any]]] = None,
    timeout: Optional[float] = None,
    max_retries: Optional[int] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> NormalizedLLMResponse:
    """Call the provider once (with transient-retry) and return a normalized response.

    This function does not run the tool loop; it performs a single logical
    completion (possibly retried on transient failure) and returns the parsed,
    normalized result. Cancellation propagates naturally via ``asyncio``.
    """
    from backend.agent import (  # lazy import to avoid cycle
        _sanitize_messages_for_provider,
        translate_to_anthropic_payload,
        translate_to_openai_response,
    )

    is_openmodel = "openmodel.ai" in (api_base or "")
    provider = _provider_name(api_base, is_openmodel)
    url = f"{api_base}/messages" if is_openmodel else f"{api_base}/chat/completions"
    timeout = timeout if timeout is not None else get_request_timeout()
    max_retries = max_retries if max_retries is not None else get_max_retries()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/pauloberezini/hermes",
        "X-Title": "Hermes Personal Assistant",
    }
    if extra_headers:
        headers.update(extra_headers)

    payload: Dict[str, Any] = {
        "model": model,
        "messages": _sanitize_messages_for_provider(messages),
        "temperature": temperature,
    }
    if max_tokens is not None:
        payload["max_tokens"] = max_tokens
    if tools:
        payload["tools"] = tools

    actual_payload = translate_to_anthropic_payload(payload) if is_openmodel else payload

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=timeout)

    last: Optional[NormalizedLLMResponse] = None
    try:
        for attempt in range(max_retries + 1):
            start = time.time()
            try:
                response = await client.post(url, json=actual_payload, headers=headers)
            except (httpx.TimeoutException, asyncio.TimeoutError):
                latency = int((time.time() - start) * 1000)
                last = NormalizedLLMResponse(
                    status=STATUS_TIMEOUT, provider=provider, model=model,
                    latency_ms=latency, retry_count=attempt,
                    error_message=f"Request timed out after {timeout:.0f}s.",
                )
            except httpx.HTTPError as exc:
                latency = int((time.time() - start) * 1000)
                last = NormalizedLLMResponse(
                    status=STATUS_PROVIDER_ERROR, provider=provider, model=model,
                    latency_ms=latency, retry_count=attempt,
                    error_message="Network error contacting provider.",
                )
                logger.warning("LLM network error (attempt %s): %s", attempt,
                               mask_secrets(str(exc)))
            else:
                latency = int((time.time() - start) * 1000)
                status_code = response.status_code
                if status_code != 200:
                    body = _summarize_body(response.text)
                    logger.warning(
                        "LLM provider HTTP %s (attempt %s): %s",
                        status_code, attempt, body,
                    )
                    last = NormalizedLLMResponse(
                        status=STATUS_PROVIDER_ERROR, provider=provider, model=model,
                        latency_ms=latency, retry_count=attempt,
                        finish_reason=f"http_{status_code}",
                        request_id=response.headers.get("x-request-id"),
                        error_message=f"Provider returned HTTP {status_code}.",
                    )
                    if status_code not in _RETRYABLE_HTTP:
                        return last  # non-transient: fail fast
                else:
                    try:
                        raw_data = response.json()
                    except Exception:
                        return NormalizedLLMResponse(
                            status=STATUS_PARSE_ERROR, provider=provider, model=model,
                            latency_ms=latency, retry_count=attempt,
                            request_id=response.headers.get("x-request-id"),
                            error_message="Provider response was not valid JSON.",
                        )
                    data = translate_to_openai_response(raw_data) if is_openmodel else raw_data
                    request_id = _extract_request_id(response, raw_data)
                    normalized = normalize_openai_response(
                        data, provider=provider, model=model,
                        request_id=request_id, latency_ms=latency,
                        retry_count=attempt,
                    )
                    return normalized

            # Decide whether to retry this transient failure.
            if attempt < max_retries and last and last.status in _RETRYABLE_STATUSES:
                await asyncio.sleep(_backoff_delay(attempt))
                continue
            break
        return last or NormalizedLLMResponse(
            status=STATUS_PROVIDER_ERROR, provider=provider, model=model,
            error_message="No response from provider.",
        )
    finally:
        if owns_client:
            await client.aclose()
