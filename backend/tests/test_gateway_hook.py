import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from backend.gateway.hook import claude_output, handle_event, main as hook_main
from backend.governance import ApprovalQueue
from backend.mcp_client import forget_mcp_server_tools

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "scripts" / "gateway" / "claude_pre_tool_use.py"


def teardown_function():
    forget_mcp_server_tools("gateway")


def _decision(result: dict) -> str:
    return result["hookSpecificOutput"]["permissionDecision"]


def test_read_allows_without_approval():
    out = handle_event({"tool_name": "Read", "tool_input": {"path": "a.py"}, "session_id": "h1"})
    assert _decision(out) == "allow"
    assert ApprovalQueue.count_pending() == 0


def test_bash_pending_retry_denies_with_request_id(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_WAIT", "0")
    out = handle_event({
        "session_id": "h_bash",
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
    })
    assert _decision(out) == "deny"
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "Pending approval" in reason
    assert "Retry this tool" in reason
    assert ApprovalQueue.count_pending() == 1


def test_edit_is_high_risk_even_though_not_in_high_risk_tools(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_WAIT", "0")
    out = handle_event({
        "session_id": "h_edit",
        "tool_name": "Edit",
        "tool_input": {"file_path": "a.py", "old_string": "a", "new_string": "b"},
    })
    assert _decision(out) == "deny"
    assert "Pending approval" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_wait_then_approve_allows(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_WAIT", "1")
    monkeypatch.setenv("HERMES_GATEWAY_WAIT_TIMEOUT_S", "2")

    def _approve():
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            pending = [r for r in ApprovalQueue.get_pending() if r["agent_id"] == "h_ok"]
            if pending:
                ApprovalQueue.resolve(pending[0]["id"], "APPROVED")
                return
            time.sleep(0.05)

    t = threading.Thread(target=_approve)
    t.start()
    out = handle_event({
        "session_id": "h_ok",
        "tool_name": "Bash",
        "tool_input": {"command": "uname -a"},
    })
    t.join(timeout=3)
    assert _decision(out) == "allow"


def test_timeout_fail_closed_denies(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_WAIT", "1")
    monkeypatch.setenv("HERMES_GATEWAY_WAIT_TIMEOUT_S", "0.2")
    monkeypatch.setenv("HERMES_GATEWAY_ON_TIMEOUT", "fail_closed")
    out = handle_event({
        "session_id": "h_to",
        "tool_name": "Write",
        "tool_input": {"file_path": "x.py", "content": "x"},
    })
    assert _decision(out) == "deny"
    assert "Fail-closed" in out["hookSpecificOutput"]["permissionDecisionReason"] or "Timed out" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_invalid_json_stdin_fail_closed(capsys, monkeypatch):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("not-json"))
    assert hook_main() == 0
    body = json.loads(capsys.readouterr().out)
    assert _decision(body) == "deny"
    assert "invalid JSON" in body["hookSpecificOutput"]["permissionDecisionReason"]


def test_decide_exception_is_fail_closed(monkeypatch):
    from backend.gateway import hook as hook_mod

    def _boom(*_a, **_k):
        raise ConnectionError("backend down")

    monkeypatch.setattr(hook_mod, "decide", _boom)
    out = handle_event({"tool_name": "Bash", "tool_input": {"command": "ls"}, "session_id": "h_down"})
    assert _decision(out) == "deny"
    assert "fail-closed" in out["hookSpecificOutput"]["permissionDecisionReason"]


def test_missing_tool_name_fail_closed():
    out = handle_event({"session_id": "h_miss"})
    assert _decision(out) == "deny"


def test_cursor_format_and_shell_payload(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_WAIT", "0")
    monkeypatch.setenv("HERMES_HOOK_FORMAT", "cursor")
    out = handle_event({"command": "ls", "cwd": "/tmp"}, fmt="cursor")
    assert out["permission"] == "deny"
    assert "Pending approval" in out["agent_message"]
    assert "Retry this tool" in out["agent_message"]


def test_script_fail_closed_when_backend_unreachable(tmp_path):
    dest = tmp_path / "scripts" / "gateway"
    dest.mkdir(parents=True)
    script = dest / "claude_pre_tool_use.py"
    script.write_text(HOOK.read_text(encoding="utf-8"), encoding="utf-8")
    env = {
        **os.environ,
        "PYTHONPATH": "",
        "HERMES_GATEWAY_TOKEN": "a" * 32,
        "HERMES_GATEWAY_URL": "http://127.0.0.1:1/api/gateway/pre-tool",
        "HERMES_HOOK_HTTP_TIMEOUT_S": "1",
    }
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
        text=True,
        capture_output=True,
        env=env,
        cwd=str(tmp_path),
        timeout=10,
    )
    assert proc.returncode == 0
    body = json.loads(proc.stdout)
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "fail-closed" in body["hookSpecificOutput"]["permissionDecisionReason"]
    assert "a" * 32 not in proc.stdout
    assert "a" * 32 not in proc.stderr


def test_claude_output_shape():
    body = claude_output("deny", "no")
    assert body["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert body["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_hook_wait_timeout_defaults_to_pending_retry(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_WAIT", "1")
    monkeypatch.setenv("HERMES_GATEWAY_WAIT_TIMEOUT_S", "0.2")
    monkeypatch.delenv("HERMES_GATEWAY_ON_TIMEOUT", raising=False)
    out = handle_event({
        "session_id": "h_pr",
        "tool_name": "Bash",
        "tool_input": {"command": "sleep 9"},
    })
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert _decision(out) == "deny"
    assert "Pending approval" in reason
    assert "Retry this tool" in reason
    assert ApprovalQueue.count_pending() == 1


def test_hook_decision_is_logged_and_chain_verifies(tmp_path):
    from backend import decision_log as dl

    out = handle_event({
        "session_id": "h_log",
        "tool_name": "Bash",
        "tool_input": {"command": "echo log-me"},
    })
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    rid = int(reason.split("request_id=")[1].split(")")[0])
    events = [row["event"] for row in dl.history(rid)]
    assert "REQUESTED" in events
    assert "HOOK" in events
    result = dl.verify()
    assert result.ok, result.error
    blob, _name = dl.export_zip()
    zip_path = tmp_path / "hook.zip"
    zip_path.write_bytes(blob)
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "verify_decision_log.py"), str(zip_path), "--pin", result.head_hash],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
