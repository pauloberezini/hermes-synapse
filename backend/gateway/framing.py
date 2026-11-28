"""MCP stdio framing.

Verified 2026-11-28 against:

- MCP spec 2025-11-25: newline-delimited JSON-RPC, no embedded newlines
  (https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)
- Official Python SDK 2.3.0 ``mcp.client.stdio``: writes ``json + "\\n"``,
  reads by splitting on ``\\n``. No Content-Length.
- ``@modelcontextprotocol/server-everything`` and
  ``@modelcontextprotocol/server-filesystem``: first response line is JSON,
  no ``Content-Length`` header.

Hermes ``mcp_client.py`` already speaks this dialect. There is no second
framing to keep.
"""

from __future__ import annotations

import json
from typing import Any, Optional, TextIO


def encode_message(msg: dict[str, Any]) -> str:
    """One JSON-RPC object, one newline. Spec + Python/TS SDK."""
    return json.dumps(msg, ensure_ascii=False) + "\n"


def read_message(stream: TextIO) -> Optional[dict[str, Any]]:
    """Read one NDJSON MCP message. None on EOF.

    Blank lines are skipped. A ``Content-Length:`` line (pre-spec LSP style)
    is ignored: we drain headers and parse the body if present, but nothing
    we probed on this date still sends that.
    """
    while True:
        line = stream.readline()
        if line == "":
            return None
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower().startswith("content-length:"):
            body = _read_lsp_body(stream, stripped)
            if body is None:
                return None
            return json.loads(body)
        return json.loads(stripped)


def _read_lsp_body(stream: TextIO, first: str) -> Optional[str]:
    """Best-effort skip of obsolete LSP headers. Returns the JSON body."""
    length = int(first.split(":", 1)[1].strip() or "0")
    while True:
        header = stream.readline()
        if header == "":
            return None
        if header in ("\n", "\r\n"):
            break
    if length <= 0:
        return None
    body = stream.read(length)
    return body if body else None
