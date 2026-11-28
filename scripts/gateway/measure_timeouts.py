#!/usr/bin/env python3
"""Measure gateway wait vs pending_retry vs a short client timeout.

Uses the in-process decide() path plus a live NDJSON client timeout against
the stdio proxy. Prints JSON to stdout. Not part of the default pytest run.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["DATABASE_URL"] = ""


def _isolate_db() -> None:
    import tempfile
    import backend.database as db_mod
    tmp = tempfile.mkdtemp(prefix="hermes_gateway_measure_")
    db_mod.DB_DIR = tmp
    db_mod.DB_PATH = os.path.join(tmp, "measure.db")
    db_mod._set_backend_for_tests(db_mod.SQLiteBackend())
    db_mod.init_db()


def _client_timeout_against_wait(timeout_s: float, wait_s: float) -> dict:
    """Spawn proxy in wait mode with no approver; client deadline is timeout_s."""
    env = {**os.environ, "PYTHONPATH": str(ROOT), "HERMES_GATEWAY_WAIT": "1",
           "HERMES_GATEWAY_WAIT_TIMEOUT_S": str(wait_s), "HERMES_GATEWAY_SESSION_ID": "measure"}
    fake = ROOT / "backend" / "tests" / "gateway_fake_mcp.py"
    proc = subprocess.Popen(
        [sys.executable, "-m", "backend.gateway.stdio_proxy", "--", sys.executable, str(fake)],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        cwd=str(ROOT), env=env,
    )
    assert proc.stdin and proc.stdout
    start = time.monotonic()
    outcome = "unknown"
    try:
        proc.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "m"}},
        }) + "\n")
        proc.stdin.flush()
        proc.stdout.readline()
        proc.stdin.write(json.dumps({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "execute_command", "arguments": {"command": "echo measure"}},
        }) + "\n")
        proc.stdin.flush()

        def _read():
            return proc.stdout.readline()

        reader = threading.Thread(target=_read)
        reader.start()
        reader.join(timeout=timeout_s)
        elapsed = time.monotonic() - start
        if reader.is_alive():
            outcome = "client_timeout"
        else:
            outcome = "got_response"
        return {"elapsed_s": round(elapsed, 3), "outcome": outcome, "client_timeout_s": timeout_s, "proxy_wait_s": wait_s}
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    _isolate_db()
    from backend.gateway.decide import ON_TIMEOUT_PENDING_RETRY, decide

    results = {}
    t0 = time.monotonic()
    d = decide("m_fail", "execute_command", {"command": "x"}, wait=True, timeout_s=0.3, on_timeout="fail_closed")
    results["wait_fail_closed"] = {
        "elapsed_s": round(time.monotonic() - t0, 3),
        "effect": d.effect,
        "status": d.status,
    }
    t1 = time.monotonic()
    d2 = decide(
        "m_retry", "execute_command", {"command": "y"},
        wait=False, on_timeout=ON_TIMEOUT_PENDING_RETRY,
    )
    results["pending_retry_no_wait"] = {
        "elapsed_s": round(time.monotonic() - t1, 3),
        "effect": d2.effect,
        "status": d2.status,
    }
    results["hermes_stdio_client_timeout_s"] = 60.0
    results["hermes_http_client_timeout_s"] = 30.0
    results["mcp_typescript_sdk_default_s"] = 60.0
    results["client_vs_long_wait"] = _client_timeout_against_wait(timeout_s=0.4, wait_s=5.0)
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
