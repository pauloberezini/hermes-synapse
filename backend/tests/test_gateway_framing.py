import io
import json
from pathlib import Path

import pytest

from backend.gateway.framing import encode_message, read_message


def test_encode_is_newline_delimited_json_not_content_length():
    raw = encode_message({"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert raw.endswith("\n")
    assert "Content-Length" not in raw
    assert json.loads(raw.strip())["method"] == "ping"


def test_read_ndjson_roundtrip():
    buf = io.StringIO()
    buf.write(encode_message({"jsonrpc": "2.0", "id": 7, "method": "tools/list"}))
    buf.seek(0)
    msg = read_message(buf)
    assert msg["id"] == 7
    assert read_message(buf) is None


def test_read_skips_blank_lines():
    buf = io.StringIO("\n\n" + encode_message({"jsonrpc": "2.0", "id": 2, "result": {}}))
    assert read_message(buf)["id"] == 2


def test_content_length_body_still_parses():
    body = json.dumps({"jsonrpc": "2.0", "id": 3, "result": {"ok": True}})
    raw = f"Content-Length: {len(body)}\r\n\r\n{body}"
    assert read_message(io.StringIO(raw))["id"] == 3


def test_python_sdk_stdio_is_ndjson():
    mcp_stdio = pytest.importorskip("mcp.client.stdio")
    src = Path(mcp_stdio.__file__).read_text(encoding="utf-8")
    assert 'json + "\\n"' in src
    assert "Content-Length" not in src
