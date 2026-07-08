import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.orchestrator import run_orchestration, AgentState

@pytest.mark.asyncio
async def test_orchestration_loop_success():
    # Mock call_llm inside orchestrator
    mock_plan = '{"steps": [{"agent": "research", "instructions": "поиск погоды"}, {"agent": "code", "instructions": "вычислить среднее"}]}'
    mock_synth = "Ответ Vexa: погода умеренная, среднее значение 5."
    
    # We will mock the sub-agents and call_llm
    with patch("backend.orchestrator.call_llm") as mock_call, \
         patch("backend.orchestrator.ResearchAgent.run", new_callable=AsyncMock) as mock_res_run, \
         patch("backend.orchestrator.CodeAgent.run_and_correct", new_callable=AsyncMock) as mock_code_run, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock) as mock_ws:
         
        mock_call.side_effect = [mock_plan, mock_synth]
        mock_res_run.return_value = "Погода в Москве: +15"
        mock_code_run.return_value = {
            "success": True,
            "stdout": "5.0\n",
            "stderr": "",
            "code": "print(5.0)",
            "attempts": 1
        }
        
        result = await run_orchestration(
            query="Найди погоду и посчитай среднее",
            api_key="fake-key",
            model="fake-model",
            chat_id="default"
        )
        
        # Assertions
        assert result["response"] == mock_synth
        assert len(result["steps"]) == 2
        assert result["steps"][0]["agent"] == "research"
        assert result["steps"][1]["agent"] == "code"
        
        # Verify sub-agents were called
        mock_res_run.assert_called_once_with("поиск погоды")
        mock_code_run.assert_called_once_with("вычислить среднее\n\nData from previous steps:\nStep 0 (Agent research) returned data:\nПогода в Москве: +15")
        
        # Verify traces are logged
        traces = result["traces"]
        assert any(t["agent"] == "Orchestrator" and t["action"] == "Planning" for t in traces)
        assert any(t["agent"] == "Research Agent" and t["action"] == "Search" for t in traces)
        assert any(t["agent"] == "Code Agent" and t["action"] == "Execute" for t in traces)
        assert any(t["agent"] == "Orchestrator" and t["action"] == "Finish" for t in traces)

@pytest.mark.asyncio
async def test_orchestration_loop_empty_plan():
    # If planner returns empty steps (simple greetings)
    mock_plan = '{"steps": []}'
    mock_synth = "Приветствую вас, Сэр. Чем могу помочь?"
    
    with patch("backend.orchestrator.call_llm") as mock_call, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock) as mock_ws:
         
        mock_call.side_effect = [mock_plan, mock_synth]
        
        result = await run_orchestration(
            query="Привет",
            api_key="fake-key",
            model="fake-model",
            chat_id="default"
        )
        
        assert result["response"] == mock_synth
        assert len(result["steps"]) == 0
        
        traces = result["traces"]
        assert any(t["agent"] == "Orchestrator" and t["action"] == "Planning" for t in traces)
        assert any(t["agent"] == "Router" and t["action"] == "Route" and "All plan steps completed" in t["message"] for t in traces)

@pytest.mark.asyncio
async def test_orchestration_loop_validation_retry_success():
    # First response: invalid json
    # Second response: valid steps json
    # Third response: synthesis response
    invalid_plan = '{"steps": [{"agent": "research"'
    valid_plan = '{"steps": [{"agent": "research", "instructions": "поиск погоды"}]}'
    mock_synth = "Ответ Vexa: погода отличная."
    
    with patch("backend.orchestrator.call_llm") as mock_call, \
         patch("backend.orchestrator.ResearchAgent.run", new_callable=AsyncMock) as mock_res_run, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock) as mock_ws:
         
        mock_call.side_effect = [invalid_plan, valid_plan, mock_synth]
        mock_res_run.return_value = "Погода: +25"
        
        result = await run_orchestration(
            query="Погода",
            api_key="fake-key",
            model="fake-model",
            chat_id="default"
        )
        
        assert result["response"] == mock_synth
        assert len(result["steps"]) == 1
        assert result["steps"][0]["agent"] == "research"
        
        # Verify that call_llm was called 3 times (1st invalid, 2nd valid, 3rd synthesis)
        assert mock_call.call_count == 3
        
        # Check that we logged a retry trace
        traces = result["traces"]
        assert any(t["agent"] == "Orchestrator" and t["action"] == "Planning" and "Retry" in t["message"] for t in traces)

@pytest.mark.asyncio
async def test_orchestration_loop_validation_retry_failure():
    # All 4 responses are invalid JSON
    # 5th response is the synthesis response
    invalid_plan = '{"steps": [invalid]'
    mock_synth = "Сэр, произошла ошибка."
    
    with patch("backend.orchestrator.call_llm") as mock_call, \
         patch("backend.websocket_manager.manager.broadcast", new_callable=AsyncMock) as mock_ws:
         
        # 4 invalid attempts, then 1 call to synthesis (since it falls back to empty steps and calls synth)
        mock_call.side_effect = [invalid_plan, invalid_plan, invalid_plan, invalid_plan, mock_synth]
        
        result = await run_orchestration(
            query="Привет",
            api_key="fake-key",
            model="fake-model",
            chat_id="default"
        )
        
        assert result["response"] == mock_synth
        assert len(result["steps"]) == 0
        
        # 4 planner attempts + 1 synthesis attempt = 5 calls
        assert mock_call.call_count == 5
        
        traces = result["traces"]
        assert any(t["agent"] == "Orchestrator" and t["action"] == "Planning" and "Failed to generate structured plan after" in t["message"] for t in traces)
