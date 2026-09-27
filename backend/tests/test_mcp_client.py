import pytest
import asyncio
import os
import json
from unittest.mock import patch, MagicMock
from backend.mcp_client import MCPServerClient, _find_executable

def test_find_executable_fallback():
    # Test built-in system executable lookup
    python_exec = _find_executable("python3")
    assert python_exec is not None
    assert "python" in python_exec

    # Test non-existent executable returns original command string
    missing = _find_executable("nonexistent_binary_xyz_123")
    assert missing == "nonexistent_binary_xyz_123"


def test_mcp_client_missing_command_graceful_handling():
    async def _run():
        config = {
            "command": "nonexistent_binary_xyz_123",
            "args": ["--version"]
        }
        client = MCPServerClient("test_missing", config)
        
        # Should log error and return without raising FileNotFoundError
        await client.start()
        assert client.process is None

        # Call tool on unstarted client returns structured JSON error
        res = await client.call_tool("dummy_tool", {})
        parsed = json.loads(res)
        assert "error" in parsed
        assert any(k in parsed["error"] for k in ("not running", "not connected"))

    asyncio.run(_run())


def test_mcp_client_http_server_error_handling():
    async def _run():
        config = {
            "url": "http://127.0.0.1:9999/invalid_mcp_endpoint"
        }
        client = MCPServerClient("test_http_fail", config)
        
        # Should catch connection error gracefully
        await client.start()
        assert len(client.tools) == 0
        assert client.is_connected is False

    asyncio.run(_run())
