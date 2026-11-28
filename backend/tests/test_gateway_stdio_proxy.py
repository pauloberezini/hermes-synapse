import inspect
import json
import threading
import time

from backend.gateway.stdio_proxy import handle_rpc, tool_result
from backend.governance import ApprovalQueue
from backend.mcp_client import MCPServerClient, forget_mcp_server_tools


def teardown_function():
    forget_mcp_server_tools("gateway")


class FakeUpstream:
    def __init__(self):
        self.calls: list[dict] = []
        self.tools = [
            {"name": "ping", "annotations": {"readOnlyHint": True, "destructiveHint": False}},
            {"name": "execute_command"},
            {"name": "drop_table"},
        ]

    def __call__(self, req: dict) -> dict:
        self.calls.append(req)
        method = req.get("method")
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": req["id"], "result": {"tools": self.tools}}
        if method == "tools/call":
            name = req["params"]["name"]
            return {
                "jsonrpc": "2.0",
                "id": req["id"],
                "result": {"content": [{"type": "text", "text": f"ran {name}"}]},
            }
        return {"jsonrpc": "2.0", "id": req.get("id"), "result": {"ok": True}}


def _rpc(upstream, tools, req, **kwargs):
    return handle_rpc(
        req,
        upstream=upstream,
        tools_cache=tools,
        session_id=kwargs.get("session_id", "p1"),
        display_name="gateway-test",
        wait=kwargs.get("wait", False),
        timeout_s=kwargs.get("timeout_s", 1.0),
        on_timeout=kwargs.get("on_timeout", "fail_closed"),
    )


def test_tools_list_is_forwarded_and_cached():
    up = FakeUpstream()
    cache: dict = {}
    res = _rpc(up, cache, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert "ping" in cache
    assert cache["ping"]["readOnlyHint"] is True
    assert res["result"]["tools"][0]["name"] == "ping"
    assert up.calls[0]["method"] == "tools/list"


def test_readonly_mcp_tool_forwards_to_upstream():
    up = FakeUpstream()
    cache: dict = {}
    _rpc(up, cache, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    res = _rpc(up, cache, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "ping", "arguments": {"msg": "hi"}},
    })
    assert res["result"]["content"][0]["text"] == "ran ping"
    assert [c["method"] for c in up.calls] == ["tools/list", "tools/call"]


def test_high_risk_call_does_not_reach_upstream_until_approved():
    up = FakeUpstream()
    cache: dict = {}
    _rpc(up, cache, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    res = _rpc(up, cache, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "execute_command", "arguments": {"command": "echo x"}},
    }, session_id="p_block")
    body = json.loads(res["result"]["content"][0]["text"])
    assert res["result"]["isError"] is True
    assert body["status"] == "PENDING_APPROVAL"
    assert [c["method"] for c in up.calls] == ["tools/list"]


def test_mcp_unannotated_write_is_gated():
    up = FakeUpstream()
    cache: dict = {}
    _rpc(up, cache, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    res = _rpc(up, cache, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "drop_table", "arguments": {"name": "t"}},
    }, session_id="p_drop")
    body = json.loads(res["result"]["content"][0]["text"])
    assert body["status"] == "PENDING_APPROVAL"
    assert not any(c.get("method") == "tools/call" for c in up.calls)


def test_wait_approve_then_forwards(monkeypatch):
    up = FakeUpstream()
    cache: dict = {}
    _rpc(up, cache, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

    def _approve():
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            pending = [r for r in ApprovalQueue.get_pending() if r["agent_id"] == "p_ok"]
            if pending:
                ApprovalQueue.resolve(pending[0]["id"], "APPROVED")
                return
            time.sleep(0.05)

    t = threading.Thread(target=_approve)
    t.start()
    res = _rpc(up, cache, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "execute_command", "arguments": {"command": "echo ok"}},
    }, session_id="p_ok", wait=True, timeout_s=2.0)
    t.join(timeout=3)
    assert res["result"]["content"][0]["text"] == "ran execute_command"
    assert any(c.get("method") == "tools/call" for c in up.calls)


def test_reject_never_calls_upstream():
    up = FakeUpstream()
    cache: dict = {}
    _rpc(up, cache, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

    def _reject():
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            pending = [r for r in ApprovalQueue.get_pending() if r["agent_id"] == "p_no"]
            if pending:
                ApprovalQueue.resolve(pending[0]["id"], "REJECTED")
                return
            time.sleep(0.05)

    t = threading.Thread(target=_reject)
    t.start()
    res = _rpc(up, cache, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "execute_command", "arguments": {"command": "halt"}},
    }, session_id="p_no", wait=True, timeout_s=2.0)
    t.join(timeout=3)
    body = json.loads(res["result"]["content"][0]["text"])
    assert body["status"] == "DENIED"
    assert not any(c.get("method") == "tools/call" for c in up.calls)


def test_initialize_is_forwarded():
    up = FakeUpstream()
    res = _rpc(up, {}, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert res["result"]["ok"] is True


def test_tool_result_pending_is_mcp_tool_error_not_jsonrpc_error():
    msg = tool_result(9, '{"status":"PENDING_APPROVAL"}', is_error=True)
    assert "error" not in msg
    assert msg["result"]["isError"] is True


def test_hermes_mcp_client_timeouts_are_60s_stdio_and_30s_http():
    assert "timeout=60.0" in inspect.getsource(MCPServerClient.send_request)
    assert "timeout=30.0" in inspect.getsource(MCPServerClient.send_request_http)


def test_client_deadline_leaves_pending_while_proxy_still_waiting():
    """A 0.3s client timeout vs a 2s wait: the call never reaches upstream."""
    up = FakeUpstream()
    cache: dict = {}
    _rpc(up, cache, {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    holder: dict = {}

    def _wait():
        holder["res"] = _rpc(up, cache, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "execute_command", "arguments": {"command": "echo slow"}},
        }, session_id="p_to", wait=True, timeout_s=2.0)

    t = threading.Thread(target=_wait)
    start = time.monotonic()
    t.start()
    t.join(timeout=0.3)
    elapsed = time.monotonic() - start
    assert t.is_alive()
    assert elapsed < 0.8
    assert not any(c.get("method") == "tools/call" for c in up.calls)
    pending = [r for r in ApprovalQueue.get_pending() if r["agent_id"] == "p_to"]
    assert pending
    t.join(timeout=3)
