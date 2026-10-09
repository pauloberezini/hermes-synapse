"""Default model ollama/llama3 is an Ollama tag. OpenRouter has no such route and returns 404."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from backend.agent import JarvisAgent, classify_complexity, generate_chat_title
from backend.subagents import call_llm

OPENROUTER = "https://openrouter.ai/api/v1"
OLLAMA = "http://127.0.0.1:11434/v1"
# Live OpenRouter slug for the ollama `llama3` tag (Llama 3 8B class).
OPENROUTER_LLAMA3 = "meta-llama/llama-3.1-8b-instruct"


def _ok(content="ready"):
    resp = MagicMock()
    resp.status_code = 200
    resp.text = ""
    resp.json.return_value = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    resp.headers = {}
    return resp


def _not_found(model):
    resp = MagicMock()
    resp.status_code = 404
    resp.text = f'{{"error":{{"message":"No endpoints found for {model}.","code":404}}}}'
    resp.json.return_value = {"error": {"message": f"No endpoints found for {model}.", "code": 404}}
    resp.headers = {}
    return resp


def _posted_models(mock_post):
    models = []
    for call in mock_post.call_args_list:
        body = call.kwargs.get("json")
        if body is None and len(call.args) > 1 and isinstance(call.args[1], dict):
            body = call.args[1]
        if isinstance(body, dict) and body.get("model"):
            models.append(body["model"])
    return models


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
async def test_default_ollama_llama3_is_not_sent_to_openrouter(mock_post):
    """OpenRouter 404s ollama/llama3. The chat request must use a live slug."""

    def side_effect(*args, **kwargs):
        body = kwargs.get("json") or {}
        if body.get("model") == "ollama/llama3":
            return _not_found("ollama/llama3")
        return _ok("ready")

    mock_post.side_effect = side_effect
    agent = JarvisAgent(api_key="test-key", api_base=OPENROUTER, model="ollama/llama3")
    with patch.dict("os.environ", {"COMPLEXITY_ROUTING": "always_direct", "LLM_MODEL": "ollama/llama3"}):
        text = await agent.respond("hi", session_id="openrouter-llama3")

    assert text == "ready"
    posted = _posted_models(mock_post)
    assert posted
    assert "ollama/llama3" not in posted
    assert posted[0] == OPENROUTER_LLAMA3


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
async def test_ollama_llama3_stays_on_local_ollama(mock_post):
    mock_post.return_value = _ok("local")
    agent = JarvisAgent(api_key="test-key", api_base=OLLAMA, model="ollama/llama3")
    with patch.dict("os.environ", {"COMPLEXITY_ROUTING": "always_direct", "LLM_API_BASE": OLLAMA}):
        text = await agent.respond("hi", session_id="local-llama3")
    assert text == "local"
    assert _posted_models(mock_post) == ["ollama/llama3"]


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
async def test_call_llm_rewrites_ollama_llama3_on_openrouter(mock_post):
    mock_post.return_value = _ok("ok")
    with patch.dict("os.environ", {"LLM_API_BASE": OPENROUTER, "LLM_MODEL": "ollama/llama3"}):
        text = await call_llm([{"role": "user", "content": "hi"}], api_key="test-key", model="ollama/llama3")
    assert text == "ok"
    assert _posted_models(mock_post)[0] == OPENROUTER_LLAMA3


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
async def test_classifier_and_title_do_not_send_ollama_tag_to_openrouter(mock_post):
    mock_post.return_value = _ok("direct")
    with patch.dict("os.environ", {"COMPLEXITY_ROUTING": "auto", "LLM_MODEL": "ollama/llama3", "LLM_API_BASE": OPENROUTER}):
        await classify_complexity("hi", api_key="test-key", api_base=OPENROUTER)
        await generate_chat_title("hi", api_key="test-key", api_base=OPENROUTER, model="ollama/llama3")
    posted = _posted_models(mock_post)
    assert posted
    assert "ollama/llama3" not in posted


def _clear_models_cache():
    from backend import main
    main._models_cache["data"] = None
    main._models_cache["timestamp"] = 0


@pytest.mark.asyncio
async def test_models_fallback_labels_use_gemini_ids():
    """Offline /api/models must not advertise Gemini under the ollama tag (that 404s)."""
    from backend.main import get_models_api

    _clear_models_cache()
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=OSError("down")):
        models = await get_models_api()
    by_name = {m["name"]: m["id"] for m in models}
    assert by_name["Google: Gemini 2.5 Flash (default)"] == "google/gemini-2.5-flash"
    assert by_name["Google: Gemini 2.5 Pro"] == "google/gemini-2.5-pro"


@pytest.mark.asyncio
async def test_models_api_pins_gemini_ahead_of_other_ids():
    from backend.main import get_models_api

    _clear_models_cache()
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"data": [
        {"id": "aaa/first", "name": "First"},
        {"id": "google/gemini-2.5-pro", "name": "Google: Gemini 2.5 Pro"},
        {"id": "google/gemini-2.5-flash", "name": "Google: Gemini 2.5 Flash"},
    ]}
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=resp):
        models = await get_models_api()
    assert [m["id"] for m in models[:2]] == [
        "google/gemini-2.5-flash",
        "google/gemini-2.5-pro",
    ]
