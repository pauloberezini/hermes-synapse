import pytest
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
    agent_inst.api_key = "test_key"
    agent_inst.api_base = "https://openrouter.ai/api/v1"
    return agent_inst

def test_agent_initial_state(agent):
    import os
    assert agent.system_prompt == DEFAULT_SYSTEM_PROMPT
    assert agent.model == os.getenv("LLM_MODEL", "google/gemini-2.5-pro")

def test_update_system_prompt(agent):
    new_prompt = "New prompt content"
    agent.update_system_prompt(new_prompt)
    assert agent.system_prompt == new_prompt

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
    assert "трудности при связи с сервером OpenRouter" in response

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

def test_suppress_tts(agent):
    session_id = "test_sess"
    assert agent.check_and_clear_suppress_tts(session_id) is False
    agent.suppress_tts_sessions.add(session_id)
    assert agent.check_and_clear_suppress_tts(session_id) is True
    assert agent.check_and_clear_suppress_tts(session_id) is False
