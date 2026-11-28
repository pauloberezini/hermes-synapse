#!/usr/bin/env python3
"""Minimal NDJSON MCP server for gateway tests. No network."""

from __future__ import annotations

import json
import sys

TOOLS = [
    {
        "name": "ping",
        "description": "echo",
        "inputSchema": {"type": "object", "properties": {"msg": {"type": "string"}}},
        "annotations": {"readOnlyHint": True, "destructiveHint": False},
    },
    {
        "name": "execute_command",
        "description": "run a shell command",
        "inputSchema": {"type": "object", "properties": {"command": {"type": "string"}}},
    },
    {
        "name": "drop_table",
        "description": "destructive write",
        "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}}},
    },
]


def reply(req: dict, result=None, error=None) -> None:
    if req.get("id") is None:
        return
    msg: dict = {"jsonrpc": "2.0", "id": req["id"]}
    if error:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        req = json.loads(line)
        method = req.get("method")
        if method == "initialize":
            reply(req, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-upstream", "version": "0"},
            })
        elif method == "tools/list":
            reply(req, {"tools": TOOLS})
        elif method == "tools/call":
            params = req.get("params") or {}
            reply(req, {
                "content": [{
                    "type": "text",
                    "text": json.dumps({
                        "ran": params.get("name"),
                        "args": params.get("arguments") or {},
                    }),
                }],
            })
        elif method == "notifications/initialized":
            pass
        elif req.get("id") is not None:
            reply(req, error={"code": -32601, "message": f"Method {method} not found"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
