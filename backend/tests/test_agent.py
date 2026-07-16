import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from backend.agent import JarvisAgent, DEFAULT_SYSTEM_PROMPT
from backend import database

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    # Set up a temporary database file for the agent tests
    original_db_path = database.DB_PATH
    original_db_dir = database.DB_DIR
    
    test_db = tmp_path / "test_hermes_agent.db"
    database.DB_PATH = str(test_db)
    database.DB_DIR = str(tmp_path)
    
    database.init_db()
    
    yield
    
    # Restore original paths
    database.DB_PATH = original_db_path
    database.DB_DIR = original_db_dir

@pytest.fixture
def agent():
    # Instantiate agent for testing
    agent_inst = JarvisAgent()
    agent_inst.provider = "openrouter"
    agent_inst.api_key = "test_key"
    agent_inst.api_base = "https://openrouter.ai/api/v1"
    return agent_inst

def test_agent_initial_state(agent):
    import os
    assert agent.system_prompt == DEFAULT_SYSTEM_PROMPT
    assert agent.model == os.getenv("LLM_MODEL", "qwen3:8b")

def test_update_system_prompt(agent):
    new_prompt = "New prompt content"
    agent.update_system_prompt(new_prompt)
    assert agent.system_prompt == new_prompt


def test_provider_switch_restores_provider_specific_endpoint(agent):
    agent.provider = "openrouter"
    agent.api_base = "https://openrouter.example/v1"
    agent.openai_api_base = "https://openrouter.example/v1"
    agent.ollama_base_url = "http://ollama:11434"

    agent.update_runtime_config(provider="ollama")
    assert agent.api_base == "http://ollama:11434"

    agent.update_runtime_config(provider="openrouter")
    assert agent.api_base == "https://openrouter.example/v1"


def test_locked_provider_endpoint_ignores_persisted_dashboard_url(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://hermes-ollama:11434")
    monkeypatch.setenv("LLM_LOCK_PROVIDER_ENDPOINT", "true")
    database.save_app_settings({
        "provider": "ollama",
        "api_base": "http://127.0.0.1:11434",
        "ollama_base_url": "http://127.0.0.1:11434",
    })

    locked_agent = JarvisAgent()

    assert locked_agent.provider == "ollama"
    assert locked_agent.api_base == "http://hermes-ollama:11434"
    assert locked_agent.ollama_base_url == "http://hermes-ollama:11434"
    assert locked_agent.get_runtime_config()["provider_endpoint_locked"] is True

def test_clear_history(agent):
    session_id = "user_123"
    database.save_message(session_id, "user", "Hi")
    
    assert len(agent.get_history(session_id)) == 1
    agent.clear_history(session_id)
    assert len(agent.get_history(session_id)) == 0

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_respond_success(mock_post, agent):
    # Setup mock response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Здравствуйте, Сэр. Чем могу помочь?"
                }
            }
        ]
    }
    mock_post.return_value = mock_response

    response = await agent.respond("Привет", session_id="test_session")
    
    assert response == "Здравствуйте, Сэр. Чем могу помочь?"
    
    # Check if history is updated in the database
    history = agent.get_history("test_session")
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Привет"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Здравствуйте, Сэр. Чем могу помочь?"

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_respond_retries_when_cleaned_reasoning_is_empty(mock_post, agent):
    reasoning_only_response = MagicMock()
    reasoning_only_response.status_code = 200
    reasoning_only_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "<think>\nНужно кратко ответить на приветствие.\n</think>"
                },
                "finish_reason": "stop"
            }
        ]
    }

    final_response = MagicMock()
    final_response.status_code = 200
    final_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Дела хорошо, Сэр. Готова помочь."
                }
            }
        ]
    }
    mock_post.side_effect = [reasoning_only_response, final_response]

    response = await agent.respond("Как дела?", session_id="test_session_reasoning_retry")

    assert response == "Дела хорошо, Сэр. Готова помочь."
    assert mock_post.call_count == 2
    retry_payload = mock_post.call_args_list[1].kwargs["json"]
    assert "видимого финального ответа" in retry_payload["messages"][-1]["content"]

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_respond_retries_when_provider_content_is_empty(mock_post, agent):
    empty_response = MagicMock()
    empty_response.status_code = 200
    empty_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None
                },
                "finish_reason": "stop"
            }
        ]
    }

    final_response = MagicMock()
    final_response.status_code = 200
    final_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Всё в порядке, Сэр."
                }
            }
        ]
    }
    mock_post.side_effect = [empty_response, final_response]

    response = await agent.respond("Как дела?", session_id="test_session_empty_retry")

    assert response == "Всё в порядке, Сэр."
    assert mock_post.call_count == 2

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_respond_http_error(mock_post, agent):
    # Setup mock error response
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_post.return_value = mock_response

    response = await agent.respond("Привет", session_id="test_session")
    assert "Провайдер модели временно недоступен" in response

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_respond_openmodel_success(mock_post, agent):
    agent.api_base = "https://api.openmodel.ai/v1"
    
    # Setup mock response in Anthropic style
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "text",
                "text": "Здравствуйте, Сэр. Чем могу помочь из OpenModel?"
            }
        ],
        "usage": {
            "input_tokens": 10,
            "output_tokens": 15
        }
    }
    mock_post.return_value = mock_response

    response = await agent.respond("Привет", session_id="test_session_openmodel")
    assert response == "Здравствуйте, Сэр. Чем могу помочь из OpenModel?"

def test_calculate_cost():
    from backend.agent import calculate_cost
    # gemini-2.5-pro
    cost = calculate_cost("google/gemini-2.5-pro", 1000, 2000)
    assert cost == pytest.approx((1000 * 0.075 / 1_000_000) + (2000 * 0.30 / 1_000_000))
    
    # gemini-2.5-flash
    cost_flash = calculate_cost("google/gemini-2.5-flash", 1000, 2000)
    assert cost_flash == pytest.approx((1000 * 0.0375 / 1_000_000) + (2000 * 0.15 / 1_000_000))

def test_local_provider_message_sanitization_and_qwen_reasoning_cleanup():
    from backend.agent import (
        _clean_model_output,
        _normalize_tool_calls,
        _parse_tool_arguments,
        _sanitize_message_for_provider,
    )

    assert _clean_model_output("<think>\nreasoning only") == ""
    assert _clean_model_output("<think>hidden</think>\nГотово, Сэр.") == "Готово, Сэр."

    raw_call = {
        "id": "abc",
        "function": {
            "name": "get_weather",
            "arguments": {"location": "Minsk", "days_ahead": 0},
        },
    }
    normalized = _normalize_tool_calls([raw_call])
    assert isinstance(normalized[0]["function"]["arguments"], str)
    assert _parse_tool_arguments(normalized[0]["function"]["arguments"]) == {"location": "Minsk", "days_ahead": 0}

    sanitized = _sanitize_message_for_provider({
        "role": "assistant",
        "content": None,
        "reasoning_content": "private local-model trace",
        "thinking": "qwen trace",
        "tool_calls": [raw_call],
    })
    assert "reasoning_content" not in sanitized
    assert "thinking" not in sanitized
    assert sanitized["content"] == ""
    assert sanitized["tool_calls"][0]["function"]["arguments"] == '{"location": "Minsk", "days_ahead": 0}'


def test_visible_answer_retry_disables_thinking_and_has_safe_budget():
    from backend.agent import _visible_answer_retry_budget, _visible_answer_retry_options

    options = _visible_answer_retry_options({"provider": "ollama", "think": "true", "num_ctx": 131072})

    assert options["think"] is False
    assert options["num_ctx"] == 131072
    assert _visible_answer_retry_budget(256) == 512
    assert _visible_answer_retry_budget(2048) == 2048
    assert _visible_answer_retry_budget(9000) == 4096


@pytest.mark.asyncio
async def test_ollama_reasoning_only_retry_forces_visible_answer(agent):
    from backend.llm_client import LLMUsage, NormalizedLLMResponse, STATUS_EMPTY, STATUS_SUCCESS

    agent.provider = "ollama"
    agent.api_base = "http://ollama:11434"
    agent.ollama_base_url = agent.api_base
    agent.ollama_think = "true"
    agent.max_tokens = 256
    agent.auto_rag = False
    first = NormalizedLLMResponse(
        status=STATUS_EMPTY,
        provider="ollama",
        model=agent.model,
        reasoning="internal trace",
        finish_reason="length",
        usage=LLMUsage(input_tokens=10, output_tokens=256),
        error_message="Model returned reasoning only, no visible answer.",
    )
    recovered = NormalizedLLMResponse(
        status=STATUS_SUCCESS,
        provider="ollama",
        model=agent.model,
        content="Привет. Я Vexa.",
        finish_reason="stop",
        usage=LLMUsage(input_tokens=20, output_tokens=8),
    )

    with patch("backend.llm_client.call_llm_normalized", new=AsyncMock(side_effect=[first, recovered])) as call:
        response = await agent.respond("Привет", session_id="ollama_reasoning_recovery")

    assert response == "Привет. Я Vexa."
    assert call.await_count == 2
    assert call.await_args_list[0].kwargs["provider_options"]["think"] == "true"
    assert call.await_args_list[1].kwargs["provider_options"]["think"] is False
    assert call.await_args_list[1].kwargs["max_tokens"] == 512

@pytest.mark.asyncio
@patch("backend.agent.asyncio.to_thread", new_callable=AsyncMock)
@patch("backend.tools.execute_tool")
@patch("httpx.AsyncClient.post")
async def test_respond_sanitizes_qwen_tool_messages_between_local_calls(mock_post, mock_execute_tool, mock_to_thread, agent):
    agent.api_base = "http://localhost:11434/v1"
    agent.model = "qwen3:6b"

    tool_response = MagicMock()
    tool_response.status_code = 200
    tool_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "reasoning_content": "I should call weather.",
                    "tool_calls": [
                        {
                            "id": "call_weather",
                            "type": "function",
                            "function": {
                                "name": "get_weather",
                                "arguments": {"location": "Minsk", "days_ahead": 0},
                            },
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 20, "completion_tokens": 5},
    }

    final_response = MagicMock()
    final_response.status_code = 200
    final_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "<think>hidden</think>\nВ Минске сейчас прохладно, Сэр.",
                }
            }
        ],
        "usage": {"prompt_tokens": 30, "completion_tokens": 10},
    }

    mock_post.side_effect = [tool_response, final_response]
    mock_execute_tool.return_value = '{"status": "mock", "temperature": "+20°C"}'
    mock_to_thread.side_effect = lambda fn, *args, **kwargs: fn(*args, **kwargs)

    response = await agent.respond("Какая погода в Минске?", session_id="local_qwen_tool")

    assert response == "В Минске сейчас прохладно, Сэр."
    assert mock_execute_tool.call_args.args[1] == {"location": "Minsk", "days_ahead": 0}

    second_payload = mock_post.call_args_list[1].kwargs["json"]
    assistant_message = next(msg for msg in second_payload["messages"] if msg["role"] == "assistant")
    assert "reasoning_content" not in assistant_message
    assert "thinking" not in assistant_message
    assert assistant_message["content"] == ""
    assert json.loads(assistant_message["tool_calls"][0]["function"]["arguments"]) == {"location": "Minsk", "days_ahead": 0}

@pytest.mark.asyncio
async def test_classify_complexity():
    from backend.agent import classify_complexity
    
    # Test env overrides
    with patch.dict("os.environ", {"COMPLEXITY_ROUTING": "always_direct"}):
        res = await classify_complexity("test message", "api_key", "api_base")
        assert res == "direct"
        
    with patch.dict("os.environ", {"COMPLEXITY_ROUTING": "always_agent"}):
        res = await classify_complexity("test message", "api_key", "api_base")
        assert res == "agent"
        
    # Normal message with auto
    with patch.dict("os.environ", {"COMPLEXITY_ROUTING": "auto"}):
        # Test keyword matching fallback (on exception/failure)
        with patch("httpx.AsyncClient.post", side_effect=Exception("network error")):
            # Message has keyword matching 'orchestrate'
            res = await classify_complexity("сравни Bitcoin и Ethereum", "api_key", "api_base")
            assert res == "orchestrate"
            
            # Message has keyword matching 'agent'
            res = await classify_complexity("найди курс биткоина", "api_key", "api_base")
            assert res == "agent"
            
            # Normal message (direct fallback)
            res = await classify_complexity("Привет, как дела?", "api_key", "api_base")
            assert res == "direct"

@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_classify_complexity_llm_success(mock_post):
    from backend.agent import classify_complexity
    
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "agent"
                }
            }
        ]
    }
    mock_post.return_value = mock_resp
    
    with patch.dict("os.environ", {"COMPLEXITY_ROUTING": "auto"}):
        res = await classify_complexity("hi", "key", "base")
        assert res == "agent"

def test_translate_to_anthropic_payload():
    from backend.agent import translate_to_anthropic_payload
    import json
    
    openai_payload = {
        "model": "claude-3-5-sonnet",
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi", "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"location": "Tel Aviv"}'
                    }
                }
            ]},
            {"role": "tool", "tool_call_id": "call_1", "content": "sunny"}
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather info",
                    "parameters": {
                        "type": "object",
                        "properties": {"location": {"type": "string"}},
                        "required": ["location"]
                    }
                }
            }
        ],
        "temperature": 0.5,
        "max_tokens": 123
    }
    
    anthropic = translate_to_anthropic_payload(openai_payload)
    
    assert anthropic["model"] == "claude-3-5-sonnet"
    assert anthropic["system"] == "You are a helpful assistant."
    assert anthropic["temperature"] == 0.5
    assert anthropic["max_tokens"] == 123
    assert len(anthropic["messages"]) == 3
    
    # Check messages translation
    assert anthropic["messages"][0] == {"role": "user", "content": "Hello"}
    assert anthropic["messages"][1]["role"] == "assistant"
    assert anthropic["messages"][1]["content"][0] == {"type": "text", "text": "Hi"}
    assert anthropic["messages"][1]["content"][1]["type"] == "tool_use"
    assert anthropic["messages"][1]["content"][1]["name"] == "get_weather"
    
    assert anthropic["messages"][2]["role"] == "user"
    assert anthropic["messages"][2]["content"][0]["type"] == "tool_result"
    assert anthropic["messages"][2]["content"][0]["tool_use_id"] == "call_1"
    assert anthropic["messages"][2]["content"][0]["content"] == "sunny"
    
    # Check tools translation
    assert len(anthropic["tools"]) == 1
    assert anthropic["tools"][0]["name"] == "get_weather"
    assert anthropic["tools"][0]["input_schema"]["properties"] == {"location": {"type": "string"}}

def test_translate_to_openai_response():
    from backend.agent import translate_to_openai_response
    import json
    
    anthropic_response = {
        "content": [
            {"type": "text", "text": "Let me check that."},
            {"type": "tool_use", "id": "call_123", "name": "get_weather", "input": {"location": "Haifa"}}
        ],
        "usage": {
            "input_tokens": 15,
            "output_tokens": 25
        }
    }
    
    openai_resp = translate_to_openai_response(anthropic_response)
    
    assert openai_resp["choices"][0]["message"]["content"] == "Let me check that."
    tool_calls = openai_resp["choices"][0]["message"]["tool_calls"]
    assert len(tool_calls) == 1
    assert tool_calls[0]["id"] == "call_123"
    assert tool_calls[0]["type"] == "function"
    assert tool_calls[0]["function"]["name"] == "get_weather"
    assert json.loads(tool_calls[0]["function"]["arguments"]) == {"location": "Haifa"}
    assert openai_resp["usage"]["prompt_tokens"] == 15
    assert openai_resp["usage"]["completion_tokens"] == 25

@pytest.mark.asyncio
@patch("backend.agent.asyncio.to_thread", new_callable=AsyncMock)
@patch("backend.tools.execute_tool")
@patch("httpx.AsyncClient.post")
async def test_respond_caps_tool_loop_iterations(mock_post, mock_execute_tool, mock_to_thread, agent):
    """A model that keeps requesting tools must be stopped at the iteration cap
    instead of looping forever (audit P0 runaway-loop guard)."""
    agent.max_tool_iterations = 3

    def _tool_call_response(*args, **kwargs):
        r = MagicMock()
        r.status_code = 200
        r.json.return_value = {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [{
                        "id": "call_loop",
                        "type": "function",
                        "function": {"name": "get_weather",
                                     "arguments": {"location": "Minsk", "days_ahead": 0}},
                    }],
                }
            }],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1},
        }
        return r

    mock_post.side_effect = _tool_call_response
    mock_execute_tool.return_value = '{"status": "ok"}'
    mock_to_thread.return_value = '{"status": "ok"}'

    response = await agent.respond("погода?", session_id="loop_cap")

    # The loop must stop; the model was called at most cap+1 times.
    assert mock_post.call_count <= agent.max_tool_iterations + 1
    assert "остановлен" in response.lower() or response.strip()


@pytest.mark.asyncio
@patch("httpx.AsyncClient.post")
async def test_respond_timeout_returns_graceful_message(mock_post, agent):
    import httpx as _httpx
    mock_post.side_effect = _httpx.TimeoutException("timed out")
    response = await agent.respond("Привет", session_id="timeout_sess")
    # No stack trace leaks to the user; a graceful message is returned.
    assert "Traceback" not in response
    assert response.strip()


def test_calculate_cost_delegates_to_cost_module():
    from backend.agent import calculate_cost
    from backend.cost import calculate_cost as cost_calc
    assert calculate_cost("google/gemini-2.5-pro", 1000, 2000) == cost_calc(
        "google/gemini-2.5-pro", 1000, 2000
    )


def test_keyword_route_precedence():
    from backend.agent import _keyword_route
    assert _keyword_route("сравни Bitcoin и Ethereum") == "orchestrate"
    assert _keyword_route("найди курс биткоина") == "agent"
    assert _keyword_route("Привет, как дела?") == "direct"


def test_suppress_tts(agent):
    session_id = "test_sess"
    assert agent.check_and_clear_suppress_tts(session_id) is False
    agent.suppress_tts_sessions.add(session_id)
    assert agent.check_and_clear_suppress_tts(session_id) is True
    assert agent.check_and_clear_suppress_tts(session_id) is False
