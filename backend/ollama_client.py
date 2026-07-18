"""Native asynchronous client for the Ollama HTTP API.

The rest of Hermes consumes a provider-neutral LLM contract.  This module owns
all Ollama-specific transport details: native NDJSON streaming, model lifecycle
operations, option placement and mid-stream error detection.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Optional

import httpx


class OllamaError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 502, code: str = "ollama_error"):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


@dataclass
class OllamaChatResult:
    model: str
    content: str = ""
    thinking: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    done_reason: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_duration: Optional[int] = None
    load_duration: Optional[int] = None


def normalize_ollama_base_url(value: Optional[str] = None) -> str:
    base = (value or os.getenv("OLLAMA_BASE_URL") or "http://127.0.0.1:11434").strip().rstrip("/")
    for suffix in ("/v1", "/api"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
    return base


def is_ollama_provider(api_base: str = "", provider: str = "") -> bool:
    configured = provider.strip().lower()
    base = (api_base or "").lower()
    if configured:
        return configured == "ollama"
    if base:
        return "ollama" in base or base.rstrip("/").endswith(":11434")
    return os.getenv("LLM_PROVIDER", "").strip().lower() == "ollama"


def normalize_keep_alive(value: Any) -> Any:
    """Ollama accepts numeric sentinels as numbers, not numeric strings."""
    if isinstance(value, str):
        normalized = value.strip()
        if re.fullmatch(r"[+-]?\d+", normalized):
            return int(normalized)
        return normalized
    return value


def installed_model_names(models: List[Dict[str, Any]]) -> List[str]:
    """Return unique Ollama model names while preserving server order."""
    names: List[str] = []
    seen: set[str] = set()
    for item in models:
        name = str(item.get("name") or item.get("model") or "").strip()
        if name and name.lower() not in seen:
            names.append(name)
            seen.add(name.lower())
    return names


def resolve_installed_model(requested: str, available: List[str]) -> Optional[str]:
    """Resolve exact names and Ollama's implicit ``:latest`` alias."""
    candidate = (requested or "").strip()
    if not candidate:
        return None

    by_lower = {name.lower(): name for name in available}
    exact = by_lower.get(candidate.lower())
    if exact:
        return exact

    if ":" not in candidate:
        return by_lower.get(f"{candidate}:latest".lower())
    return None


def select_installed_model(current: str, preferred: str, available: List[str]) -> Optional[str]:
    """Keep the current model when possible, otherwise use the configured default."""
    return (
        resolve_installed_model(current, available)
        or resolve_installed_model(preferred, available)
        or (available[0] if available else None)
    )


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])
    except Exception:
        pass
    return f"Ollama returned HTTP {response.status_code}."


def _normalize_tool_calls(tool_calls: Any) -> List[Dict[str, Any]]:
    normalized: List[Dict[str, Any]] = []
    for index, call in enumerate(tool_calls or []):
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        arguments = function.get("arguments", {})
        normalized.append({
            "id": call.get("id") or f"ollama_call_{index}",
            "type": "function",
            "function": {
                "name": function.get("name", ""),
                "arguments": arguments if isinstance(arguments, str) else json.dumps(arguments, ensure_ascii=False),
            },
        })
    return normalized


def _ollama_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result: List[Dict[str, Any]] = []
    for message in messages:
        role = str(message.get("role") or "user")
        item: Dict[str, Any] = {"role": role, "content": str(message.get("content") or "")}
        if role == "tool":
            item["tool_name"] = message.get("name") or message.get("tool_name") or "tool"
        if message.get("images"):
            item["images"] = message["images"]
        if message.get("thinking"):
            item["thinking"] = message["thinking"]
        if message.get("tool_calls"):
            calls = []
            for call in message["tool_calls"]:
                function = dict(call.get("function") or {})
                arguments = function.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}
                function["arguments"] = arguments
                calls.append({"function": function})
            item["tool_calls"] = calls
        result.append(item)
    return result


class OllamaClient:
    def __init__(
        self,
        base_url: Optional[str] = None,
        *,
        timeout: float = 120.0,
        api_key: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self.base_url = normalize_ollama_base_url(base_url)
        self.timeout = timeout
        self.api_key = api_key if api_key is not None else os.getenv("OLLAMA_API_KEY", "")
        self._client = client

    def _headers(self, headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        result = dict(headers or {})
        if self.api_key:
            result.setdefault("Authorization", f"Bearer {self.api_key}")
        return result

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout)
        try:
            kwargs["headers"] = self._headers(kwargs.get("headers"))
            response = await client.request(method, f"{self.base_url}{path}", **kwargs)
            if response.status_code >= 400:
                raise OllamaError(_error_message(response), status_code=response.status_code)
            return response
        except httpx.TimeoutException as exc:
            raise OllamaError("Ollama request timed out.", status_code=504, code="timeout") from exc
        except httpx.ConnectError as exc:
            raise OllamaError(
                f"Cannot connect to Ollama at {self.base_url}.",
                status_code=503,
                code="connection_error",
            ) from exc
        except httpx.RequestError as exc:
            raise OllamaError("Ollama request failed.", status_code=502, code="transport_error") from exc
        finally:
            if owns_client:
                await client.aclose()

    async def status(self) -> Dict[str, Any]:
        try:
            version_response = await self._request("GET", "/api/version")
            tags_response = await self._request("GET", "/api/tags")
            ps_response = await self._request("GET", "/api/ps")
            tags = tags_response.json().get("models", [])
            running = ps_response.json().get("models", [])
            return {
                "available": True,
                "base_url": self.base_url,
                "version": version_response.json().get("version"),
                "models_count": len(tags),
                "running_count": len(running),
            }
        except OllamaError as exc:
            return {
                "available": False,
                "base_url": self.base_url,
                "error": str(exc),
                "code": exc.code,
            }

    async def list_models(self) -> List[Dict[str, Any]]:
        response = await self._request("GET", "/api/tags")
        models = response.json().get("models", [])
        return sorted(models if isinstance(models, list) else [], key=lambda item: str(item.get("name", "")).lower())

    async def list_running(self) -> List[Dict[str, Any]]:
        response = await self._request("GET", "/api/ps")
        models = response.json().get("models", [])
        return models if isinstance(models, list) else []

    async def show_model(self, model: str) -> Dict[str, Any]:
        response = await self._request("POST", "/api/show", json={"model": model})
        return response.json()

    async def delete_model(self, model: str) -> None:
        await self._request("DELETE", "/api/delete", json={"model": model})

    async def unload_model(self, model: str) -> None:
        await self._request(
            "POST",
            "/api/generate",
            json={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
        )

    async def pull_model(self, model: str, *, insecure: bool = False) -> AsyncIterator[Dict[str, Any]]:
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=None)
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/api/pull",
                json={"model": model, "insecure": insecure, "stream": True},
                headers=self._headers(),
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    try:
                        message = json.loads(body).get("error")
                    except Exception:
                        message = None
                    raise OllamaError(message or f"Ollama returned HTTP {response.status_code}.", status_code=response.status_code)
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise OllamaError("Ollama returned invalid pull progress data.") from exc
                    if event.get("error"):
                        raise OllamaError(str(event["error"]))
                    yield event
        except httpx.ConnectError as exc:
            raise OllamaError(f"Cannot connect to Ollama at {self.base_url}.", status_code=503, code="connection_error") from exc
        except httpx.RequestError as exc:
            raise OllamaError("Ollama pull stream was interrupted.", status_code=502, code="interrupted_stream") from exc
        finally:
            if owns_client:
                await client.aclose()

    async def chat(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        num_ctx: Optional[int] = None,
        keep_alive: Any = None,
        think: Any = None,
        stream_callback: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> OllamaChatResult:
        options: Dict[str, Any] = {"temperature": temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        options["num_ctx"] = num_ctx or int(os.getenv("OLLAMA_NUM_CTX", "8192"))
        payload: Dict[str, Any] = {
            "model": model,
            "messages": _ollama_messages(messages),
            "stream": stream_callback is not None,
            "options": options,
            "keep_alive": normalize_keep_alive(
                keep_alive if keep_alive is not None else os.getenv("OLLAMA_KEEP_ALIVE", "5m")
            ),
        }
        if tools:
            payload["tools"] = tools
        configured_think = think if think is not None else os.getenv("OLLAMA_THINK", "false")
        if isinstance(configured_think, str):
            lowered = configured_think.lower()
            payload["think"] = True if lowered == "true" else False if lowered == "false" else configured_think
        else:
            payload["think"] = configured_think

        if stream_callback is None:
            response = await self._request("POST", "/api/chat", json=payload)
            data = response.json()
            if data.get("error"):
                raise OllamaError(str(data["error"]))
            message = data.get("message") or {}
            return OllamaChatResult(
                model=data.get("model") or model,
                content=str(message.get("content") or ""),
                thinking=str(message.get("thinking") or ""),
                tool_calls=_normalize_tool_calls(message.get("tool_calls")),
                done_reason=data.get("done_reason"),
                prompt_tokens=data.get("prompt_eval_count"),
                completion_tokens=data.get("eval_count"),
                total_duration=data.get("total_duration"),
                load_duration=data.get("load_duration"),
            )

        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=None)
        result = OllamaChatResult(model=model)
        try:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload, headers=self._headers()) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    try:
                        message = json.loads(body).get("error")
                    except Exception:
                        message = None
                    raise OllamaError(message or f"Ollama returned HTTP {response.status_code}.", status_code=response.status_code)
                saw_done = False
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError as exc:
                        raise OllamaError("Ollama returned invalid NDJSON stream data.") from exc
                    if chunk.get("error"):
                        raise OllamaError(str(chunk["error"]))
                    message = chunk.get("message") or {}
                    content = str(message.get("content") or "")
                    thinking = str(message.get("thinking") or "")
                    tool_calls = _normalize_tool_calls(message.get("tool_calls"))
                    result.content += content
                    result.thinking += thinking
                    result.tool_calls.extend(tool_calls)
                    await stream_callback({
                        "content": content,
                        "thinking": thinking,
                        "tool_calls": tool_calls,
                        "done": bool(chunk.get("done")),
                    })
                    if chunk.get("done"):
                        saw_done = True
                        result.model = chunk.get("model") or model
                        result.done_reason = chunk.get("done_reason")
                        result.prompt_tokens = chunk.get("prompt_eval_count")
                        result.completion_tokens = chunk.get("eval_count")
                        result.total_duration = chunk.get("total_duration")
                        result.load_duration = chunk.get("load_duration")
                if not saw_done:
                    raise OllamaError("Ollama stream ended before the terminal event.", code="interrupted_stream")
                return result
        except httpx.TimeoutException as exc:
            raise OllamaError("Ollama generation timed out.", status_code=504, code="timeout") from exc
        except httpx.ConnectError as exc:
            raise OllamaError(f"Cannot connect to Ollama at {self.base_url}.", status_code=503, code="connection_error") from exc
        except httpx.RequestError as exc:
            raise OllamaError("Ollama generation stream was interrupted.", status_code=502, code="interrupted_stream") from exc
        finally:
            if owns_client:
                await client.aclose()
