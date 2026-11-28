"""Localhost POST /api/gateway/pre-tool + HTTP-only hook script."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.auth import create_session
from backend.gateway.http_api import router as gateway_router
from backend.gateway.token import MIN_TOKEN_LEN, PATH
from backend.governance import ApprovalQueue
from backend.main import app
from backend.mcp_client import forget_mcp_server_tools

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "gateway" / "claude_pre_tool_use.py"
CANARY = "GATEWAY_TOKEN_CANARY_VALUE_32CHRS_XX"
assert len(CANARY) >= MIN_TOKEN_LEN


def teardown_function():
    forget_mcp_server_tools("gateway")


def _client(token: str | None = CANARY, peer: str = "127.0.0.1", extra_headers: dict | None = None) -> TestClient:
    headers = dict(extra_headers or {})
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    return TestClient(app, headers=headers, client=(peer, 50000))


def test_claude_example_settings_match_cli_2_1_332():
    data = json.loads((ROOT / "scripts" / "gateway" / "example.claude.settings.json").read_text())
    hook = data["hooks"]["PreToolUse"][0]["hooks"][0]
    assert hook["type"] == "command"
    assert hook["onFailure"] == "block"
    assert hook["timeout"] == 50
    assert "statusMessage" in hook
    assert "Bash" in data["hooks"]["PreToolUse"][0]["matcher"]


def test_cursor_example_is_marked_unverified_live():
    data = json.loads((ROOT / "scripts" / "gateway" / "example.cursor.hooks.json").read_text())
    assert "UNVERIFIED-LIVE" in data["_unverified_live"]
    assert data["hooks"]["preToolUse"][0]["failClosed"] is True
    assert data["hooks"]["beforeShellExecution"][0]["failClosed"] is True


def test_script_does_not_import_backend():
    text = HOOK.read_text(encoding="utf-8")
    assert "import backend" not in text
    assert "from backend" not in text
    assert "sqlite" not in text.lower()
    assert "DATABASE_URL" not in text


def test_loopback_with_token_pending_retry(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", CANARY)
    monkeypatch.setenv("HERMES_GATEWAY_WAIT", "0")
    client = _client()
    resp = client.post(PATH, json={
        "session_id": "http_bash",
        "tool_name": "Bash",
        "tool_input": {"command": "echo http"},
    })
    assert resp.status_code == 200
    body = resp.json()
    reason = body["hookSpecificOutput"]["permissionDecisionReason"]
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "Pending approval" in reason
    assert "Retry this tool" in reason
    assert CANARY not in json.dumps(body)
    assert ApprovalQueue.count_pending() == 1


def test_read_allows(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", CANARY)
    resp = _client().post(PATH, json={
        "session_id": "http_read",
        "tool_name": "Read",
        "tool_input": {"path": "a.py"},
    })
    assert resp.status_code == 200
    assert resp.json()["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_missing_token_401(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", CANARY)
    resp = _client(token=None).post(PATH, json={"tool_name": "Bash", "tool_input": {"command": "x"}})
    assert resp.status_code == 401


def test_wrong_token_401(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", CANARY)
    resp = _client(token="b" * 32).post(PATH, json={"tool_name": "Bash", "tool_input": {"command": "x"}})
    assert resp.status_code == 401
    assert CANARY not in resp.text


def test_short_token_unconfigured_503(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", "short")
    resp = _client(token="short").post(PATH, json={"tool_name": "Bash", "tool_input": {"command": "x"}})
    assert resp.status_code == 503


def test_non_loopback_403(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", CANARY)
    resp = _client(peer="8.8.8.8").post(PATH, json={"tool_name": "Bash", "tool_input": {"command": "x"}})
    assert resp.status_code == 403


def test_forwarded_header_403(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", CANARY)
    resp = _client(extra_headers={"X-Forwarded-For": "1.2.3.4"}).post(
        PATH, json={"tool_name": "Bash", "tool_input": {"command": "x"}}
    )
    assert resp.status_code == 403


def test_session_token_cannot_call_gateway(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", CANARY)
    session = create_session()
    resp = _client(token=session).post(PATH, json={"tool_name": "Bash", "tool_input": {"command": "x"}})
    assert resp.status_code == 401


def test_gateway_token_cannot_call_other_api(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", CANARY)
    resp = _client().get("/api/config")
    assert resp.status_code == 401


def test_invalid_json_body_400(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", CANARY)
    resp = _client().post(PATH, content=b"not-json", headers={"Content-Type": "application/json"})
    assert resp.status_code == 400


def test_token_never_in_decision_log_or_caplog(monkeypatch, caplog, tmp_path):
    from backend import decision_log as dl

    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", CANARY)
    monkeypatch.setenv("HERMES_GATEWAY_WAIT", "0")
    caplog.set_level("DEBUG")
    resp = _client().post(PATH, json={
        "session_id": "http_noleak",
        "tool_name": "Bash",
        "tool_input": {"command": "echo noleak"},
    })
    assert resp.status_code == 200
    blob, _name = dl.export_zip()
    zip_path = tmp_path / "noleak.zip"
    zip_path.write_bytes(blob)
    dumped = zip_path.read_bytes()
    assert CANARY.encode() not in dumped
    assert CANARY not in caplog.text
    result = dl.verify()
    assert result.ok, result.error
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_decision_log.py"), str(zip_path), "--pin", result.head_hash],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert CANARY not in proc.stdout
    assert CANARY not in proc.stderr


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _run_hook(env: dict, payload: dict | str, timeout: float = 10) -> subprocess.CompletedProcess[str]:
    raw = payload if isinstance(payload, str) else json.dumps(payload)
    merged = {**os.environ, **env}
    return subprocess.run(
        [sys.executable, str(HOOK)],
        input=raw,
        text=True,
        capture_output=True,
        env=merged,
        cwd=str(ROOT),
        timeout=timeout,
    )


def test_script_fail_closed_invalid_json():
    proc = _run_hook(
        {"HERMES_GATEWAY_TOKEN": CANARY, "HERMES_GATEWAY_URL": "http://127.0.0.1:9/x"},
        "not-json",
    )
    assert proc.returncode == 0
    body = json.loads(proc.stdout)
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "invalid JSON" in body["hookSpecificOutput"]["permissionDecisionReason"]
    assert CANARY not in proc.stdout


def test_script_fail_closed_missing_token():
    proc = _run_hook({"HERMES_GATEWAY_TOKEN": "", "HERMES_GATEWAY_URL": "http://127.0.0.1:9/x"}, {
        "tool_name": "Bash", "tool_input": {"command": "ls"},
    })
    assert proc.returncode == 0
    body = json.loads(proc.stdout)
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "HERMES_GATEWAY_TOKEN" in body["hookSpecificOutput"]["permissionDecisionReason"]


def test_script_fail_closed_non_loopback_url():
    proc = _run_hook(
        {"HERMES_GATEWAY_TOKEN": CANARY, "HERMES_GATEWAY_URL": "http://example.com/api/gateway/pre-tool"},
        {"tool_name": "Bash", "tool_input": {"command": "ls"}},
    )
    assert proc.returncode == 0
    body = json.loads(proc.stdout)
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "loopback" in body["hookSpecificOutput"]["permissionDecisionReason"]


def test_script_fail_closed_backend_bad_json():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"not-json")

        def log_message(self, *_a):
            return

    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        proc = _run_hook(
            {
                "HERMES_GATEWAY_TOKEN": CANARY,
                "HERMES_GATEWAY_URL": f"http://127.0.0.1:{port}/api/gateway/pre-tool",
            },
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        )
    finally:
        server.shutdown()
    assert proc.returncode == 0
    body = json.loads(proc.stdout)
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "invalid JSON" in body["hookSpecificOutput"]["permissionDecisionReason"]


def test_script_fail_closed_http_timeout():
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            time.sleep(2)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_a):
            return

    port = _free_port()
    server = HTTPServer(("127.0.0.1", port), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        proc = _run_hook(
            {
                "HERMES_GATEWAY_TOKEN": CANARY,
                "HERMES_GATEWAY_URL": f"http://127.0.0.1:{port}/api/gateway/pre-tool",
                "HERMES_HOOK_HTTP_TIMEOUT_S": "0.3",
            },
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
        )
    finally:
        server.shutdown()
    assert proc.returncode == 0
    body = json.loads(proc.stdout)
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "fail-closed" in body["hookSpecificOutput"]["permissionDecisionReason"]
    assert CANARY not in proc.stdout
    assert CANARY not in proc.stderr


def test_script_posts_to_live_queue_and_chain_verifies(monkeypatch, tmp_path):
    import uvicorn
    from backend import decision_log as dl

    monkeypatch.setenv("HERMES_GATEWAY_TOKEN", CANARY)
    monkeypatch.setenv("HERMES_GATEWAY_WAIT", "0")

    mini = FastAPI()
    mini.include_router(gateway_router)
    port = _free_port()
    config = uvicorn.Config(mini, host="127.0.0.1", port=port, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 8
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    assert server.started, "uvicorn did not start"

    try:
        proc = _run_hook(
            {
                "HERMES_GATEWAY_TOKEN": CANARY,
                "HERMES_GATEWAY_URL": f"http://127.0.0.1:{port}{PATH}",
                "HERMES_GATEWAY_WAIT": "0",
            },
            {
                "session_id": "live_http",
                "tool_name": "Bash",
                "tool_input": {"command": "echo live-http"},
            },
        )
        assert proc.returncode == 0, proc.stderr
        body = json.loads(proc.stdout)
        reason = body["hookSpecificOutput"]["permissionDecisionReason"]
        assert body["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Pending approval" in reason
        assert CANARY not in proc.stdout
        pending = [r for r in ApprovalQueue.get_pending() if r["agent_id"] == "live_http"]
        assert len(pending) == 1
        rid = pending[0]["id"]
        events = [row["event"] for row in dl.history(int(rid))]
        assert "REQUESTED" in events
        assert "HOOK" in events
        result = dl.verify()
        assert result.ok, result.error
        blob, _name = dl.export_zip()
        zip_path = tmp_path / "live.zip"
        zip_path.write_bytes(blob)
        assert CANARY.encode() not in zip_path.read_bytes()
        verified = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "verify_decision_log.py"), str(zip_path), "--pin", result.head_hash],
            capture_output=True,
            text=True,
        )
        assert verified.returncode == 0, verified.stderr + verified.stdout
    finally:
        server.should_exit = True
        thread.join(timeout=3)
