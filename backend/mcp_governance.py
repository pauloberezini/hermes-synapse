"""Validation, approval and activation for MCP server connections."""

from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import os
import re
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend.database import DB_PATH


_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,47}$")
_ENV_KEY = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_ENV_REF = re.compile(r"^\$\{([A-Z][A-Z0-9_]{0,63})\}$")
_ALLOWED_PROXY_ENV = {
    "OPENAPI_URL",
    "AUTH_TOKEN_URL",
    "AUTH_USERNAME",
    "AUTH_PASSWORD",
    "STATIC_BEARER_TOKEN",
}
_SECRET_ENV = {"AUTH_USERNAME", "AUTH_PASSWORD", "STATIC_BEARER_TOKEN"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def _init_schema() -> None:
    with _connect() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mcp_connection_proposals (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                status TEXT NOT NULL,
                config TEXT NOT NULL,
                config_digest TEXT NOT NULL,
                control_task_id TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def _validate_url(value: str, field: str) -> str:
    if len(value) > 2048:
        raise ValueError(f"{field} is too long")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError(f"{field} must be an HTTP(S) URL without embedded credentials")
    host = parsed.hostname.lower()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address and (address.is_link_local or address.is_multicast or address.is_unspecified):
        raise ValueError(f"{field} points to a blocked network range")
    if parsed.scheme == "http":
        private_http = host in {"localhost", "host.docker.internal"} or bool(
            address and (address.is_private or address.is_loopback)
        )
        if not private_http:
            raise ValueError(f"{field} must use HTTPS outside the private network")
    return value


def _proxy_commands() -> set[str]:
    return {"python3", sys.executable}


def validate_server_config(name: str, config: dict[str, Any]) -> dict[str, Any]:
    """Accept only the built-in OpenAPI bridge or an executable owned by the capability broker."""
    clean_name = str(name).strip().lower()
    if not _NAME.fullmatch(clean_name):
        raise ValueError("MCP name must contain only lowercase letters, digits, underscores or hyphens")
    command = str(config.get("command", "")).strip()
    args = config.get("args") or []
    env = config.get("env") or {}
    if not isinstance(args, list) or len(args) > 32:
        raise ValueError("MCP arguments must be a list of at most 32 values")
    if not isinstance(env, dict) or len(env) > 24:
        raise ValueError("MCP environment must be an object with at most 24 values")
    normalized_args = []
    for value in args:
        item = str(value)
        if not item or len(item) > 2048 or "\x00" in item or "\n" in item or "\r" in item:
            raise ValueError("MCP arguments contain an invalid value")
        normalized_args.append(item)

    local_proxy = str((Path(__file__).resolve().parent / "mcp_openapi_proxy.py"))
    container_proxy = "/app/backend/mcp_openapi_proxy.py"
    is_proxy = command in _proxy_commands() and normalized_args[:1] in ([local_proxy], [container_proxy])
    if not is_proxy:
        from backend.capability_broker import install_root

        try:
            executable = Path(command).expanduser().resolve()
            executable.relative_to(install_root())
        except (OSError, ValueError):
            raise ValueError("Only the built-in OpenAPI bridge or managed capability executables are allowed")
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError("Managed MCP executable is missing or not executable")

    normalized_env: dict[str, str] = {}
    for key, value in env.items():
        clean_key = str(key).strip().upper()
        clean_value = str(value).strip()
        if not _ENV_KEY.fullmatch(clean_key) or clean_key not in _ALLOWED_PROXY_ENV:
            raise ValueError(f"MCP environment key is not allowed: {clean_key}")
        if len(clean_value) > 2048 or "\x00" in clean_value or "\n" in clean_value:
            raise ValueError(f"MCP environment value is invalid: {clean_key}")
        if clean_key in _SECRET_ENV:
            match = _ENV_REF.fullmatch(clean_value)
            if not match or match.group(1) != clean_key:
                raise ValueError(f"{clean_key} must be stored as the reference ${{{clean_key}}}")
        elif clean_key in {"OPENAPI_URL", "AUTH_TOKEN_URL"}:
            clean_value = _validate_url(clean_value, clean_key)
        normalized_env[clean_key] = clean_value
    if is_proxy and "OPENAPI_URL" not in normalized_env:
        raise ValueError("OPENAPI_URL is required for the OpenAPI bridge")
    return {
        "name": clean_name,
        "command": command,
        "args": normalized_args,
        "env": normalized_env,
    }


def expand_environment(config_env: dict[str, str]) -> dict[str, str]:
    expanded: dict[str, str] = {}
    for key, value in config_env.items():
        match = _ENV_REF.fullmatch(value)
        if match:
            variable = match.group(1)
            resolved = os.getenv(variable, "")
            if not resolved:
                raise ValueError(f"Required MCP environment variable is not configured: {variable}")
            expanded[key] = resolved
        else:
            expanded[key] = value
    return expanded


def build_openapi_config(name: str, url: str, auth_env_var: str = "") -> dict[str, Any]:
    env = {"OPENAPI_URL": url}
    if auth_env_var:
        if auth_env_var != "STATIC_BEARER_TOKEN":
            raise ValueError("Only STATIC_BEARER_TOKEN is supported by the autonomous connection profile")
        env["STATIC_BEARER_TOKEN"] = "${STATIC_BEARER_TOKEN}"
    return validate_server_config(
        name,
        {
            "command": "python3",
            "args": ["/app/backend/mcp_openapi_proxy.py"],
            "env": env,
        },
    )


def _digest(config: dict[str, Any]) -> str:
    canonical = json.dumps(config, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_connection_proposal(name: str, config: dict[str, Any]) -> dict[str, Any]:
    _init_schema()
    validated = validate_server_config(name, config)
    digest = _digest(validated)
    with _connect() as connection:
        existing = connection.execute(
            """
            SELECT * FROM mcp_connection_proposals
            WHERE config_digest = ? AND status IN ('awaiting_approval', 'approved', 'connecting')
            ORDER BY created_at DESC LIMIT 1
            """,
            (digest,),
        ).fetchone()
    if existing:
        return _proposal_from_row(existing)

    from backend.control_plane import create_review_task

    plan = {
        "name": validated["name"],
        "transport": "stdio",
        "command": validated["command"],
        "args": validated["args"],
        "env_keys": sorted(validated["env"]),
        "config_digest": digest,
        "network_policy": "HTTPS externally; private HTTP allowed; metadata/link-local blocked",
        "secret_policy": "Secret values remain in process environment and are never stored in MCP config",
    }
    task = create_review_task(
        goal=f"Connect reviewed MCP server: {validated['name']}",
        arguments=plan,
        risk_class="R4",
        acceptance=[
            "Command matches the built-in bridge or a managed executable",
            "No shell interpreter, lifecycle hook or inherited application secret is exposed",
            "Remote tools are registered only after MCP initialization succeeds",
        ],
        rollback=f"Disconnect and remove only MCP server '{validated['name']}' from managed configuration.",
        requester="autonomy:mcp",
    )
    now = _now()
    proposal_id = f"mcp-{uuid.uuid4().hex[:12]}"
    with _connect() as connection:
        connection.execute(
            """
            INSERT INTO mcp_connection_proposals
                (id, name, status, config, config_digest, control_task_id, created_at, updated_at)
            VALUES (?, ?, 'awaiting_approval', ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                validated["name"],
                json.dumps(validated, ensure_ascii=False),
                digest,
                task["id"],
                now,
                now,
            ),
        )
        row = connection.execute(
            "SELECT * FROM mcp_connection_proposals WHERE id = ?",
            (proposal_id,),
        ).fetchone()
    result = _proposal_from_row(row)
    result["control_task"] = task
    return result


def _proposal_from_row(row: sqlite3.Row) -> dict[str, Any]:
    item = dict(row)
    item["config"] = json.loads(item["config"] or "{}")
    return item


def get_connection_proposal(control_task_id: str) -> dict[str, Any] | None:
    _init_schema()
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT * FROM mcp_connection_proposals
            WHERE control_task_id = ? ORDER BY created_at DESC LIMIT 1
            """,
            (control_task_id,),
        ).fetchone()
    return _proposal_from_row(row) if row else None


def _set_status(proposal_id: str, status: str) -> None:
    with _connect() as connection:
        connection.execute(
            "UPDATE mcp_connection_proposals SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), proposal_id),
        )


def _config_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "mcp_config.json"


def _save_config(name: str, config: dict[str, Any]) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {}
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
    payload.setdefault("mcpServers", {})[name] = {
        "command": config["command"],
        "args": config["args"],
        "env": config["env"],
    }
    temporary = path.with_suffix(f".tmp-{uuid.uuid4().hex[:8]}")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


async def execute_approved_connection(control_task_id: str) -> dict[str, Any]:
    proposal = get_connection_proposal(control_task_id)
    if not proposal:
        raise KeyError(control_task_id)
    from backend.control_plane import finish_task, get_task, start_task

    task = get_task(control_task_id)
    if not task or task["status"] != "approved":
        raise PermissionError("MCP connection is not approved")
    if proposal["status"] not in {"awaiting_approval", "approved", "failed"}:
        raise ValueError(f"MCP proposal cannot execute from status {proposal['status']}")
    config = validate_server_config(proposal["name"], proposal["config"])
    if _digest(config) != proposal["config_digest"]:
        raise RuntimeError("Approved MCP configuration changed")

    _set_status(proposal["id"], "connecting")
    start_task(control_task_id)
    try:
        from backend.mcp_client import MCPServerClient, mcp_clients, register_client_tools

        old_client = mcp_clients.get(proposal["name"])
        client = MCPServerClient(proposal["name"], config)
        await client.start()
        if old_client:
            await old_client.shutdown()
        mcp_clients[proposal["name"]] = client
        register_client_tools(proposal["name"], client)
        await asyncio.to_thread(_save_config, proposal["name"], config)
        result = {"status": "connected", "name": proposal["name"], "tools": len(client.tools)}
    except Exception as exc:
        _set_status(proposal["id"], "failed")
        finish_task(control_task_id, "", error=str(exc))
        raise
    _set_status(proposal["id"], "connected")
    finish_task(control_task_id, json.dumps(result, ensure_ascii=False))
    return result


_init_schema()
