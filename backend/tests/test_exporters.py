"""
Unit tests for backend.exporters package (ShareGPT, OpenAI, Alpaca exporters).
"""
import json
import pytest
from backend.exporters import get_exporter
from backend.exporters.sharegpt import ShareGPTExporter
from backend.exporters.openai import OpenAIExporter
from backend.exporters.alpaca import AlpacaExporter


def test_exporter_factory():
    sharegpt = get_exporter("sharegpt")
    assert isinstance(sharegpt, ShareGPTExporter)

    openai = get_exporter("openai")
    assert isinstance(openai, OpenAIExporter)

    alpaca = get_exporter("alpaca")
    assert isinstance(alpaca, AlpacaExporter)

    # Default fallback
    unknown = get_exporter("unknown_format")
    assert isinstance(unknown, ShareGPTExporter)


def test_sharegpt_export_jsonl():
    exporter = ShareGPTExporter()
    session_id = "test_session_123"
    messages = [
        {"role": "system", "content": "You are a helpful AI assistant."},
        {"role": "user", "content": "Hello, build a function for me."},
        {"role": "assistant", "content": "Sure, here is the function..."}
    ]
    decision_logs = [
        {
            "user_message": "Hello, build a function for me.",
            "traces": [{"type": "thought", "message": "Analyzing request..."}]
        }
    ]

    result_jsonl = exporter.export(session_id, messages, decision_logs, extension="jsonl")
    assert isinstance(result_jsonl, str)

    parsed = json.loads(result_jsonl)
    assert parsed["id"] == session_id
    assert "conversations" in parsed
    conversations = parsed["conversations"]

    assert len(conversations) == 4
    assert conversations[0] == {"from": "system", "value": "You are a helpful AI assistant."}
    assert conversations[1] == {"from": "human", "value": "Hello, build a function for me."}
    assert conversations[2] == {"from": "thought", "value": "Analyzing request..."}
    assert conversations[3] == {"from": "gpt", "value": "Sure, here is the function..."}


def test_sharegpt_export_json_dict():
    exporter = ShareGPTExporter()
    session_id = "test_session_json"
    messages = [
        {"role": "human", "content": "What is Python?"},
        {"role": "gpt", "content": "Python is a programming language."}
    ]

    result_dict = exporter.export(session_id, messages, [], extension="json")
    assert isinstance(result_dict, dict)
    assert result_dict["id"] == session_id
    assert len(result_dict["conversations"]) == 2
    assert result_dict["conversations"][0]["from"] == "human"
    assert result_dict["conversations"][1]["from"] == "gpt"


def test_openai_exporter():
    exporter = OpenAIExporter()
    session_id = "test_openai"
    messages = [
        {"role": "user", "content": "Explain gravity."},
        {"role": "assistant", "content": "Gravity is a fundamental force..."}
    ]

    result_jsonl = exporter.export(session_id, messages, [], extension="jsonl")
    parsed = json.loads(result_jsonl)
    assert parsed["id"] == session_id
    assert len(parsed["messages"]) == 2
    assert parsed["messages"][0]["role"] == "user"
    assert parsed["messages"][1]["role"] == "assistant"


def test_alpaca_exporter():
    exporter = AlpacaExporter()
    session_id = "test_alpaca"
    messages = [
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": "What is 2+2?"},
        {"role": "assistant", "content": "4"}
    ]

    result_dict = exporter.export(session_id, messages, [], extension="json")
    assert isinstance(result_dict, list)
    assert len(result_dict) == 1
    assert result_dict[0]["instruction"] == "What is 2+2?"
    assert result_dict[0]["input"] == "Be concise."
    assert result_dict[0]["output"] == "4"
