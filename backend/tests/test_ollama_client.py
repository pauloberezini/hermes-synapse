import json

import httpx
import pytest

from backend.ollama_client import (
    OllamaClient,
    OllamaError,
    installed_model_names,
    is_ollama_provider,
    normalize_keep_alive,
    normalize_ollama_base_url,
    resolve_installed_model,
    select_installed_model,
)


def test_normalize_base_url_and_provider_detection(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert normalize_ollama_base_url("http://localhost:11434/v1/") == "http://localhost:11434"
    assert normalize_ollama_base_url("http://ollama:11434/api") == "http://ollama:11434"
    assert is_ollama_provider("http://127.0.0.1:11434")
    assert is_ollama_provider("https://provider.example/v1", "ollama")


def test_normalize_keep_alive_numeric_sentinels():
    assert normalize_keep_alive("-1") == -1
    assert normalize_keep_alive(" 0 ") == 0
    assert normalize_keep_alive("20m") == "20m"


def test_installed_model_resolution_prefers_current_then_configured_default():
    models = [
        {"name": "hf.co/unsloth/Qwen3.6:Q4"},
        {"model": "hermes-brain:latest"},
        {"name": "HERMES-BRAIN:latest"},
    ]
    names = installed_model_names(models)

    assert names == ["hf.co/unsloth/Qwen3.6:Q4", "hermes-brain:latest"]
    assert resolve_installed_model("hermes-brain", names) == "hermes-brain:latest"
    assert select_installed_model("missing", "hermes-brain", names) == "hermes-brain:latest"
    assert select_installed_model("hf.co/unsloth/Qwen3.6:Q4", "hermes-brain", names) == names[0]


@pytest.mark.asyncio
async def test_native_chat_sends_numeric_keep_alive_as_number():
    captured = {}

    async def handler(request: httpx.Request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "qwen3:8b",
            "message": {"role": "assistant", "content": "ok"},
            "done": True,
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        await OllamaClient("http://ollama:11434", client=http_client).chat(
            model="qwen3:8b",
            messages=[{"role": "user", "content": "hello"}],
            keep_alive="-1",
        )

    assert captured["keep_alive"] == -1


@pytest.mark.asyncio
async def test_native_chat_places_options_and_normalizes_response():
    captured = {}

    async def handler(request: httpx.Request):
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={
            "model": "qwen3:8b",
            "message": {"role": "assistant", "content": "Привет", "thinking": "short plan"},
            "done": True,
            "done_reason": "stop",
            "prompt_eval_count": 11,
            "eval_count": 4,
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        result = await OllamaClient("http://ollama:11434", client=http_client).chat(
            model="qwen3:8b",
            messages=[{"role": "user", "content": "hello"}],
            temperature=0.3,
            max_tokens=128,
            num_ctx=16384,
            keep_alive="20m",
            think="low",
        )

    assert captured["options"] == {"temperature": 0.3, "num_predict": 128, "num_ctx": 16384}
    assert captured["keep_alive"] == "20m"
    assert captured["think"] == "low"
    assert captured["stream"] is False
    assert result.content == "Привет"
    assert result.prompt_tokens == 11
    assert result.completion_tokens == 4


@pytest.mark.asyncio
async def test_native_chat_stream_emits_chunks_and_terminal_usage():
    events = []
    ndjson = (
        '{"model":"qwen3:8b","message":{"content":"При","thinking":"plan"},"done":false}\n'
        '{"model":"qwen3:8b","message":{"content":"вет"},"done":true,"done_reason":"stop",'
        '"prompt_eval_count":7,"eval_count":2}\n'
    )

    async def handler(request: httpx.Request):
        payload = json.loads(request.content)
        assert payload["stream"] is True
        return httpx.Response(200, content=ndjson, headers={"content-type": "application/x-ndjson"})

    async def on_chunk(chunk):
        events.append(chunk)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        result = await OllamaClient("http://ollama:11434", client=http_client).chat(
            model="qwen3:8b",
            messages=[{"role": "user", "content": "hello"}],
            stream_callback=on_chunk,
        )

    assert result.content == "Привет"
    assert result.thinking == "plan"
    assert result.prompt_tokens == 7
    assert result.completion_tokens == 2
    assert events[-1]["done"] is True


@pytest.mark.asyncio
async def test_native_chat_reports_midstream_error():
    ndjson = '{"message":{"content":"partial"},"done":false}\n{"error":"model runner crashed"}\n'

    async def handler(_request: httpx.Request):
        return httpx.Response(200, content=ndjson)

    async def on_chunk(_chunk):
        return None

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(OllamaError, match="runner crashed"):
            await OllamaClient("http://ollama:11434", client=http_client).chat(
                model="qwen3:8b",
                messages=[{"role": "user", "content": "hello"}],
                stream_callback=on_chunk,
            )


@pytest.mark.asyncio
async def test_model_lifecycle_endpoints_use_native_api():
    calls = []

    async def handler(request: httpx.Request):
        assert request.headers["authorization"] == "Bearer local-secret"
        calls.append((request.method, request.url.path, json.loads(request.content) if request.content else None))
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": "zeta"}, {"name": "alpha"}]})
        return httpx.Response(200, json={"status": "success"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        client = OllamaClient("http://ollama:11434", api_key="local-secret", client=http_client)
        models = await client.list_models()
        await client.delete_model("alpha")
        await client.unload_model("zeta")

    assert [model["name"] for model in models] == ["alpha", "zeta"]
    assert ("DELETE", "/api/delete", {"model": "alpha"}) in calls
    assert ("POST", "/api/generate", {"model": "zeta", "prompt": "", "stream": False, "keep_alive": 0}) in calls


@pytest.mark.asyncio
async def test_structured_ollama_error_is_exposed_without_provider_body():
    async def handler(_request: httpx.Request):
        return httpx.Response(404, json={"error": "model 'missing' not found"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        with pytest.raises(OllamaError) as error:
            await OllamaClient("http://ollama:11434", client=http_client).show_model("missing")
    assert error.value.status_code == 404
    assert "not found" in str(error.value)
