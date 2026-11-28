"""Stdio MCP proxy: client NDJSON <-> Hermes gate <-> upstream stdio MCP server.

Framing matches ``backend/mcp_client.py`` and ``backend/mcp_openapi_proxy.py``
(newline-delimited JSON-RPC), not LSP Content-Length. High-risk ``tools/call``
goes through ``decide``; everything else is forwarded.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any, Callable, Optional, TextIO

from backend.gateway.decide import decide, settings_from_env


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


def read_ndjson(stream: TextIO) -> Optional[dict]:
    line = stream.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return read_ndjson(stream)
    return json.loads(line)


def write_ndjson(stream: TextIO, msg: dict) -> None:
    stream.write(json.dumps(msg, ensure_ascii=False) + "\n")
    stream.flush()


def serve(upstream_cmd: list[str]) -> int:
    cfg = settings_from_env()
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

    def upstream(req: dict) -> dict:
        write_ndjson(proc.stdin, req)
        if req.get("id") is None:
            return {}
        while True:
            msg = read_ndjson(proc.stdout)
            if msg is None:
                raise RuntimeError("upstream MCP server closed")
            if msg.get("id") == req.get("id"):
                return msg
            write_ndjson(sys.stdout, msg)

    try:
        while True:
            req = read_ndjson(sys.stdin)
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
                )
            except Exception as exc:
                log(f"error: {exc}")
                if req.get("id") is not None:
                    write_ndjson(sys.stdout, {
                        "jsonrpc": "2.0",
                        "id": req.get("id"),
                        "error": {"code": -32603, "message": str(exc)},
                    })
                continue
            if res is not None:
                write_ndjson(sys.stdout, res)
    finally:
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
