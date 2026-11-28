#!/usr/bin/env python3
"""Claude Code PreToolUse / Cursor hook entrypoint.

Stdlib only. Posts the host event to a loopback Hermes endpoint authenticated
by HERMES_GATEWAY_TOKEN. Does not import the backend or open a database.
Fail-closed (deny JSON, exit 0) on bad JSON, missing token, unreachable
backend, HTTP errors, or a non-JSON response. Never prints the token.
"""

from __future__ import annotations

import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

DEFAULT_URL = "http://127.0.0.1:8000/api/gateway/pre-tool"
MIN_TOKEN_LEN = 32
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def _format() -> str:
    return (os.environ.get("HERMES_HOOK_FORMAT") or "claude").strip() or "claude"


def _deny(reason: str) -> int:
    if _format() == "cursor":
        body = {
            "permission": "deny",
            "user_message": reason,
            "agent_message": reason,
        }
    else:
        body = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    sys.stdout.write(json.dumps(body) + "\n")
    return 0


def _loopback_url(url: str) -> bool:
    host = (urlparse(url).hostname or "").strip().lower()
    return host in LOOPBACK


def main() -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw or "{}")
        if not isinstance(event, dict):
            raise ValueError("hook input must be a JSON object")
    except Exception:
        return _deny("hook: invalid JSON (fail-closed)")

    token = os.environ.get("HERMES_GATEWAY_TOKEN") or ""
    if len(token) < MIN_TOKEN_LEN:
        return _deny("hook: HERMES_GATEWAY_TOKEN missing or shorter than 32 (fail-closed)")

    url = (os.environ.get("HERMES_GATEWAY_URL") or DEFAULT_URL).strip() or DEFAULT_URL
    if not _loopback_url(url):
        return _deny("hook: HERMES_GATEWAY_URL is not loopback (fail-closed)")

    try:
        timeout_s = float(os.environ.get("HERMES_HOOK_HTTP_TIMEOUT_S", "45"))
    except ValueError:
        timeout_s = 45.0
    timeout_s = max(0.1, min(timeout_s, 45.0))

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if _format() == "cursor":
        headers["X-Hermes-Hook-Format"] = "cursor"

    req = Request(url, data=json.dumps(event).encode("utf-8"), headers=headers, method="POST")
    try:
        with urlopen(req, timeout=timeout_s) as resp:
            body = resp.read().decode("utf-8")
    except HTTPError:
        return _deny("hook: backend rejected the request (fail-closed)")
    except (URLError, TimeoutError, OSError):
        return _deny("hook: backend unreachable (fail-closed)")
    except Exception:
        return _deny("hook: backend unreachable (fail-closed)")

    try:
        parsed = json.loads(body)
        if not isinstance(parsed, dict):
            raise ValueError("not an object")
    except Exception:
        return _deny("hook: backend returned invalid JSON (fail-closed)")

    sys.stdout.write(json.dumps(parsed, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
