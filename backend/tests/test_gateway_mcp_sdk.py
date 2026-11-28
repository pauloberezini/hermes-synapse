"""Official MCP Python SDK as a client of the Hermes stdio proxy."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

pytest.importorskip("mcp")

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, get_default_environment, stdio_client

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "backend" / "tests" / "gateway_fake_mcp.py"


def _proxy_params(tmp_path: Path, session_id: str) -> StdioServerParameters:
    env = get_default_environment()
    env.update({
        "PYTHONPATH": str(ROOT),
        "DATABASE_URL": "",
        "HERMES_SQLITE_PATH": str(tmp_path / "gateway.db"),
        "HERMES_GATEWAY_WAIT": "0",
        "HERMES_GATEWAY_SESSION_ID": session_id,
        "HERMES_GATEWAY_AGENT_NAME": "sdk-test",
    })
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "backend.gateway.stdio_proxy", "--", sys.executable, str(FAKE)],
        env=env,
        cwd=str(ROOT),
    )


def _text(result) -> str:
    parts = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


@pytest.mark.asyncio
async def test_official_sdk_lists_and_calls_readonly_through_proxy(tmp_path):
    params = _proxy_params(tmp_path, "sdk_ro")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            listed = await session.list_tools()
            names = [t.name for t in listed.tools]
            assert "ping" in names
            result = await session.call_tool("ping", {"msg": "hi"})
            assert getattr(result, "is_error", getattr(result, "isError", False)) is False
            assert "ran" in _text(result)


@pytest.mark.asyncio
async def test_official_sdk_high_risk_returns_pending_tool_error(tmp_path):
    params = _proxy_params(tmp_path, "sdk_wr")
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            first = await session.call_tool("execute_command", {"command": "echo sdk"})
            assert getattr(first, "is_error", getattr(first, "isError", False)) is True
            body = json.loads(_text(first))
            assert body["status"] == "PENDING_APPROVAL"
            assert body["request_id"]
            assert "Retry this tool" in body["error"]
