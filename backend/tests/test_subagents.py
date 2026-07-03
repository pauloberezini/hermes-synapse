import os
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.subagents import ResearchAgent, CodeAgent, AnalystAgent, execute_code

@pytest.fixture(autouse=True)
def mock_docker_disabled():
    with patch("docker.from_env") as mock_env:
        mock_env.side_effect = Exception("Docker disabled for unit tests")
        yield

def test_execute_code_success():
    res = execute_code("print('hello world')")
    assert res["success"] is True
    assert res["stdout"].strip() == "hello world"
    assert res["stderr"] == ""
    assert res["returncode"] == 0

def test_execute_code_syntax_error():
    res = execute_code("print('hello world") # Missing quote
    assert res["success"] is False
    assert "SyntaxError" in res["stderr"]
    assert res["returncode"] != 0

@pytest.mark.asyncio
async def test_research_agent_run():
    agent = ResearchAgent(api_key="fake-key", model="fake-model")
    
    with patch("backend.subagents.call_llm", new_callable=AsyncMock) as mock_call, \
         patch("backend.subagents.httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
         
        mock_call.return_value = "Тони Старк"
        
        # Mock Wikipedia and RSS response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = "<rss><channel><item><title>Тони Старк</title><description>Железный человек</description><link>url</link></item></channel></rss>"
        mock_response.json.return_value = {
            "query": {
                "search": [
                    {"title": "Тони Старк", "snippet": "Персонаж Marvel Comics, также известный как Железный человек"}
                ]
            }
        }
        mock_get.return_value = mock_response
        
        output = await agent.run("Расскажи про Тони Старка")
        
        # Assertions
        assert "Тони Старк" in output
        assert "Железный человек" in output
        mock_get.assert_called()

@pytest.mark.asyncio
async def test_code_agent_self_correction():
    agent = CodeAgent(api_key="fake-key", model="fake-model")
    
    # 1. First code fails (SyntaxError), second code succeeds
    bad_code = "```python\nprint('bad code\n```"
    good_code = "```python\nprint('good code')\n```"
    
    with patch("backend.subagents.call_llm", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = [bad_code, good_code]
        
        result = await agent.run_and_correct("Выведи good code")
        
        assert result["success"] is True
        assert result["stdout"].strip() == "good code"
        assert result["attempts"] == 2
        assert mock_call.call_count == 2

@pytest.mark.asyncio
async def test_analyst_agent_run():
    agent = AnalystAgent(api_key="fake-key", model="fake-model")
    
    # We will patch matplotlib and execute_code to avoid creating actual images during test
    with patch("backend.subagents.CodeAgent.run_and_correct", new_callable=AsyncMock) as mock_code_run, \
         patch("os.path.exists", return_value=True):
         
        mock_code_run.return_value = {
            "success": True,
            "stdout": "Plot saved\n",
            "stderr": "",
            "code": "plt.savefig('test_path.png')",
            "attempts": 1
        }
        
        result = await agent.run("Построй график продаж")
        
        assert result["success"] is True
        assert "plot_" in result["plot_url"]
        assert result["code"] == "plt.savefig('test_path.png')"
        mock_code_run.assert_called_once()
