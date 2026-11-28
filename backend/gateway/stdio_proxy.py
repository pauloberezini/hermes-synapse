"""Stdio MCP proxy: client <-> Hermes gate <-> one upstream stdio MCP server.

Framing is newline-delimited JSON-RPC (MCP spec 2025-11-25 and the official
Python/TS SDKs). High-risk ``tools/call`` goes through ``decide``; everything
else is forwarded. Default is pending-retry, not a blocking wait.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from typing import Any, Callable, Optional, TextIO

from backend.gateway.decide import decide, settings_from_env
from backend.gateway.framing import encode_message, read_message


def log(msg: str) -> None:
    sys.stderr.write(f"[hermes-gateway] {msg}\n")
    sys.stderr.flush()


def tool_result(msg_id: Any, text: str, *, is_error: bool = False) -> dict:
    body: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        body["isError"] = True
    return {"jsonrpc": "2.0", "id": msg_id, "result": body}


def handle_rpc(
    req: dict,
    *,
    upstream: Callable[[dict], dict],
    tools_cache: dict[str, dict],
    session_id: str,
    display_name: str,
    wait: bool,
    timeout_s: float,
    on_timeout: str,
    cancel=None,
) -> Optional[dict]:
    """Dispatch one JSON-RPC frame. None means no response (notification)."""
    method = req.get("method")
    msg_id = req.get("id")

    if method and str(method).startswith("notifications/") and msg_id is None:
        upstream(req)
        return None

    if method == "tools/list":
        res = upstream(req)
        tools = ((res.get("result") or {}).get("tools")) or []
        tools_cache.clear()
        for tool in tools:
            if isinstance(tool, dict) and tool.get("name"):
                ann = tool.get("annotations")
                tools_cache[str(tool["name"])] = ann if isinstance(ann, dict) else {}
        return res

    if method == "tools/call":
        params = req.get("params") or {}
        name = str(params.get("name") or "")
        arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
        decision = decide(
            session_id,
            name,
            arguments,
            annotations=tools_cache.get(name),
            known_mcp=True,
            wait=wait,
            timeout_s=timeout_s,
            on_timeout=on_timeout,
            display_name=display_name,
            cancel=cancel,
        )
        if decision.effect == "allow":
            return upstream(req)
        payload = {
            "status": "PENDING_APPROVAL" if decision.effect == "pending" else "DENIED",
            "effect": decision.effect,
            "request_id": decision.request_id,
            "error": decision.error,
        }
        if decision.body:
            payload["gate"] = decision.body
        return tool_result(msg_id, json.dumps(payload, ensure_ascii=False), is_error=True)

    if msg_id is None:
        upstream(req)
        return None
    return upstream(req)


def write_message(stream: TextIO, msg: dict) -> None:
    stream.write(encode_message(msg))
    stream.flush()


def serve(
    upstream_cmd: list[str],
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    from backend.database import init_db

    init_db()
    cfg = settings_from_env()
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    log(
        f"starting upstream={upstream_cmd!r} wait={cfg['wait']} "
        f"timeout={cfg['timeout_s']} on_timeout={cfg['on_timeout']}"
    )
    proc = subprocess.Popen(
        upstream_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
        text=True,
        bufsize=1,
    )
    if proc.stdin is None or proc.stdout is None:
        log("upstream pipes missing")
        return 1
    tools_cache: dict[str, dict] = {}
    cancel = threading.Event()
    incoming: queue.Queue[dict | None] = queue.Queue()

    def upstream(req: dict) -> dict:
        write_message(proc.stdin, req)
        if req.get("id") is None:
            return {}
        while True:
            msg = read_message(proc.stdout)
            if msg is None:
                raise RuntimeError("upstream MCP server closed")
            if msg.get("id") == req.get("id"):
                return msg
            write_message(stdout, msg)

    def reader() -> None:
        try:
            while True:
                msg = read_message(stdin)
                if msg is None:
                    cancel.set()
                    incoming.put(None)
                    return
                incoming.put(msg)
        except Exception as exc:
            log(f"stdin reader: {exc}")
            cancel.set()
            incoming.put(None)

    threading.Thread(target=reader, daemon=True).start()
    try:
        while True:
            req = incoming.get()
            if req is None:
                break
            try:
                res = handle_rpc(
                    req,
                    upstream=upstream,
                    tools_cache=tools_cache,
                    session_id=cfg["session_id"],
                    display_name=cfg["display_name"],
                    wait=cfg["wait"],
                    timeout_s=cfg["timeout_s"],
                    on_timeout=cfg["on_timeout"],
                    cancel=cancel,
                )
            except Exception as exc:
                log(f"error: {exc}")
                if req.get("id") is not None:
                    write_message(stdout, {
                        "jsonrpc": "2.0",
                        "id": req.get("id"),
                        "error": {"code": -32603, "message": str(exc)},
                    })
                continue
            if res is not None:
                try:
                    write_message(stdout, res)
                except BrokenPipeError:
                    cancel.set()
                    break
    finally:
        cancel.set()
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--" in argv:
        upstream_cmd = argv[argv.index("--") + 1 :]
    else:
        upstream_cmd = argv
    if not upstream_cmd:
        log("usage: python -m backend.gateway.stdio_proxy -- <upstream command> [args...]")
        return 2
    return serve(upstream_cmd)


if __name__ == "__main__":
    raise SystemExit(main())
