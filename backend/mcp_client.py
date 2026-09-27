import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
from typing import Dict, Any, List, Optional, Iterable
import time

logger = logging.getLogger("hermes.mcp_client")

def _find_executable(cmd: str) -> str:
    """Find executable path in system PATH or common installation locations."""
    if not cmd:
        return cmd
    found = shutil.which(cmd)
    if found:
        return found
    
    common_paths = [
        "/usr/local/bin",
        "/opt/homebrew/bin",
        "/usr/bin",
        "/bin",
        os.path.expanduser("~/.nvm/versions/node"),
        os.path.expanduser("~/.nvm/current/bin"),
        os.path.expanduser("~/.local/bin"),
        os.path.expanduser("~/.cargo/bin"),
    ]
    for path in common_paths:
        if os.path.isdir(path):
            candidate = os.path.join(path, cmd)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
            for root, dirs, files in os.walk(path):
                if cmd in files:
                    full_p = os.path.join(root, cmd)
                    if os.access(full_p, os.X_OK):
                        return full_p
                if root.count(os.sep) - path.count(os.sep) >= 2:
                    dirs.clear()
    return cmd

_server_offline_cooldowns: Dict[str, float] = {}

def mark_server_offline(name: str, cooldown_seconds: float = 300.0) -> None:
    """Mark an MCP server as offline until the cooldown period expires."""
    _server_offline_cooldowns[name] = time.time() + cooldown_seconds

def is_server_in_cooldown(name: str) -> bool:
    """Check whether an MCP server is currently in offline cooldown."""
    return time.time() < _server_offline_cooldowns.get(name, 0.0)

def reset_server_cooldown(name: str = None) -> None:
    """Reset offline cooldown for a specific server or all servers."""
    if name:
        _server_offline_cooldowns.pop(name, None)
    else:
        _server_offline_cooldowns.clear()

class MCPServerClient:

    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        raw_url = config.get("url")
        if raw_url and os.path.exists("/.dockerenv") and ("localhost" in raw_url or "127.0.0.1" in raw_url):
            raw_url = raw_url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
        self.url = raw_url
        self.http_headers = config.get("headers", {})
        self.command = config.get("command")
        self.args = config.get("args", [])
        self.env = {**os.environ, **config.get("env", {})}
        self.process = None
        self.reader = None
        self.writer = None
        self.req_id = 0
        self.pending_requests = {}
        self.tools = []
        self.session_id = None
        self.session_ttl = float(config.get("session_ttl", 180.0))
        self._last_used_at = 0.0
        self._reinit_cooldown_until = 0.0
        self._http_locks = {}
        self.is_connected = False
        self.optional = bool(config.get("optional", True if self.url else False))

    async def start(self):
        self._started = True
        now = time.time()
        if (self.optional or self.url) and now < _server_offline_cooldowns.get(self.name, 0.0):
            logger.debug(f"MCP server '{self.name}' is in offline cooldown, skipping start.")
            return
        try:
            if self.url:
                logger.info(f"Connecting HTTP/SSE MCP server '{self.name}': {self.url}")
                try:
                    await self._initialize_http()
                    await self._list_tools_http()
                except Exception as http_err:
                    if "localhost" in self.url or "127.0.0.1" in self.url:
                        alt_url = self.url.replace("localhost", "host.docker.internal").replace("127.0.0.1", "host.docker.internal")
                        logger.info(f"Retrying HTTP/SSE MCP server '{self.name}' via host gateway: {alt_url}")
                        self.url = alt_url
                        await self._initialize_http()
                        await self._list_tools_http()
                    else:
                        raise http_err
            else:
                exec_cmd = _find_executable(self.command)
                if not shutil.which(exec_cmd) and not (os.path.isabs(exec_cmd) and os.path.exists(exec_cmd)):
                    self.is_connected = False
                    logger.error(f"Executable '{self.command}' for MCP server '{self.name}' not found in PATH or system locations.")
                    return
                logger.info(f"Starting MCP server '{self.name}': {exec_cmd} {' '.join(self.args)}")
                self.process = await asyncio.create_subprocess_exec(
                    exec_cmd,
                    *self.args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=self.env
                )
                self.reader = self.process.stdout
                self.writer = self.process.stdin
                
                # Start background reader task for messages
                asyncio.create_task(self._read_loop())
                
                # Initialize connection
                await self._initialize()
                
                # List tools
                await self._list_tools()
            self.is_connected = True
            logger.info(f"MCP server '{self.name}' successfully initialized with {len(self.tools)} tools.")
        except FileNotFoundError as fnf_err:
            self.is_connected = False
            logger.error(f"Executable '{self.command}' for MCP server '{self.name}' not found: {fnf_err}")
        except Exception as e:
            self.is_connected = False
            err_str = str(e)
            is_connection_error = (
                self.url is not None
                or any(k in type(e).__name__ for k in ("ConnectError", "ConnectTimeout", "ConnectionRefused", "NetworkError", "RemoteProtocolError"))
                or any(k in err_str.lower() for k in ("connection refused", "not known", "all connection attempts failed", "connect timeout", "gaierror"))
            )
            if getattr(self, "optional", False) or is_connection_error:
                _server_offline_cooldowns[self.name] = time.time() + 300.0
                logger.warning(f"MCP server '{self.name}' is unavailable or failed to connect ({self.url or self.command}): {e}")
            else:
                logger.error(f"Failed to start MCP server '{self.name}': {e}")

    def _get_http_lock(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if not hasattr(self, "_http_locks"):
            self._http_locks = {}
        if loop not in self._http_locks:
            self._http_locks[loop] = asyncio.Lock()
        return self._http_locks[loop]

    async def send_request_http(self, method: str, params: Dict[str, Any], _is_retry: bool = False) -> Dict[str, Any]:
        import httpx
        lock = self._get_http_lock()

        # If re-initialization is currently in progress and this is not part of initialization, wait for it
        if method not in ("initialize", "notifications/initialized") and lock.locked():
            async with lock:
                pass  # Wait until ongoing re-initialization completes

        # Ensure session exists or proactively re-initialize if session has been idle longer than its TTL
        now = time.time()
        if (
            not self.session_id
            and method not in ("initialize", "notifications/initialized")
            and not _is_retry
            and now > getattr(self, "_reinit_cooldown_until", 0.0)
        ):
            async with lock:
                if not self.session_id:
                    try:
                        await self._initialize_http()
                    except Exception as init_err:
                        self._reinit_cooldown_until = time.time() + 300.0
                        logger.warning(f"MCP server '{self.name}' initial HTTP session establishment failed: {init_err}. Entering 5m cooldown.")
                        raise
        elif (
            bool(self.session_id)
            and method not in ("initialize", "notifications/initialized")
            and not _is_retry
            and getattr(self, "_last_used_at", 0.0) > 0.0
            and (now - getattr(self, "_last_used_at", 0.0)) > getattr(self, "session_ttl", 180.0)
            and now > getattr(self, "_reinit_cooldown_until", 0.0)
        ):
            async with lock:
                if getattr(self, "_last_used_at", 0.0) > 0.0 and (time.time() - getattr(self, "_last_used_at", 0.0)) > getattr(self, "session_ttl", 180.0):
                    self.session_id = None
                    try:
                        await self._initialize_http()
                    except Exception as init_err:
                        self._reinit_cooldown_until = time.time() + 300.0
                        logger.warning(f"MCP server '{self.name}' proactive re-initialization failed: {init_err}. Entering 5m cooldown.")
                        raise

        self.req_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self.req_id,
            "method": method,
            "params": params
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.http_headers
        }
        if self.session_id:
            headers["mcp-session-id"] = self.session_id

        if getattr(self, "client", None) is not None:
            resp = await self.client.post(self.url, json=payload, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self.url, json=payload, headers=headers)
            
        # Check for session expiration / session not found (HTTP 404/401/400 with active session or explicit session error)
        now = time.time()
        resp_lower = resp.text.lower()
        has_session_err_keyword = any(k in resp_lower for k in (
            "session not found", "no valid session", "invalid session",
            "re-initialize", "session expired", "session is closed",
            "session closed", "unknown session", "missing session", "session id"
        ))
        is_session_expired = (
            (
                (bool(self.session_id) and resp.status_code in (401, 404))
                or (bool(self.session_id) and resp.status_code == 400 and ("session" in resp_lower or "bad request" in resp_lower))
                or (resp.status_code in (400, 401, 404) and has_session_err_keyword)
                or (resp.status_code >= 400 and has_session_err_keyword)
            )
            and method not in ("initialize", "notifications/initialized")
            and not _is_retry
            and now > getattr(self, "_reinit_cooldown_until", 0.0)
        )
        if is_session_expired:
            logger.info(f"MCP server '{self.name}' session expired or not found (HTTP {resp.status_code}). Re-initializing session...")
            current_sess = self.session_id
            lock = self._get_http_lock()
            async with lock:
                if self.session_id == current_sess:
                    self.session_id = None
                    try:
                        await self._initialize_http()
                    except Exception as init_err:
                        self._reinit_cooldown_until = time.time() + 300.0
                        logger.warning(f"MCP server '{self.name}' re-initialization failed: {init_err}. Entering 5m cooldown.")
                        raise
            try:
                res = await self.send_request_http(method, params, _is_retry=True)
                self._reinit_cooldown_until = 0.0
                return res
            except Exception as retry_err:
                self._reinit_cooldown_until = time.time() + 300.0
                logger.warning(f"MCP server '{self.name}' request failed after re-initialization: {retry_err}. Entering 5m cooldown.")
                raise

        resp.raise_for_status()
        if "mcp-session-id" in resp.headers:
            self.session_id = resp.headers["mcp-session-id"]
        self._last_used_at = time.time()
        
        text = resp.text
        for line in text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        if not text.strip():
            return {}
        try:
            return resp.json()
        except Exception:
            return {}

    async def _initialize_http(self):
        init_res = await self.send_request_http("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "hermes-mcp-client",
                "version": "1.0.0"
            }
        })
        try:
            await self.send_request_http("notifications/initialized", {})
        except Exception as notify_err:
            logger.debug(f"MCP server '{self.name}' notifications/initialized error: {notify_err}")
        return init_res

    async def _list_tools_http(self):
        res = await self.send_request_http("tools/list", {})
        self.tools = res.get("result", {}).get("tools", [])

    async def _read_loop(self):
        # Background task reading stderr to log it
        async def read_stderr():
            while True:
                if not self.process or self.process.returncode is not None:
                    break
                line = await self.process.stderr.readline()
                if not line:
                    break
                logger.warning(f"[{self.name} stderr] {line.decode('utf-8').strip()}")
        asyncio.create_task(read_stderr())

        while True:
            if not self.process or self.process.returncode is not None:
                break
            line_bytes = await self.reader.readline()
            if not line_bytes:
                break
            line = line_bytes.decode("utf-8").strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
                msg_id = msg.get("id")
                if msg_id in self.pending_requests:
                    fut = self.pending_requests[msg_id]
                    if not fut.done():
                        fut.set_result(msg)
            except Exception as e:
                logger.error(f"Error parsing line from '{self.name}': {e}")

    async def send_request(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.url:
            return await self.send_request_http(method, params)
        self.req_id += 1
        curr_id = self.req_id
        fut = asyncio.get_event_loop().create_future()
        self.pending_requests[curr_id] = fut
        
        req = {
            "jsonrpc": "2.0",
            "id": curr_id,
            "method": method,
            "params": params
        }
        
        self.writer.write(json.dumps(req).encode("utf-8") + b"\n")
        await self.writer.drain()
        
        try:
            res = await asyncio.wait_for(fut, timeout=60.0)
            return res
        except asyncio.TimeoutError:
            logger.error(f"Request {method} to '{self.name}' timed out")
            raise
        finally:
            self.pending_requests.pop(curr_id, None)

    async def _initialize(self):
        res = await self.send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {
                "name": "hermes-mcp-client",
                "version": "1.0.0"
            }
        })
        return res

    async def _list_tools(self):
        res = await self.send_request("tools/list", {})
        self.tools = res.get("result", {}).get("tools", [])

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        if getattr(self, "_started", False) and not getattr(self, "is_connected", False):
            return json.dumps({"error": f"MCP server '{self.name}' is not connected (failed to start)"}, ensure_ascii=False)
        if not self.url and (not self.process or self.process.returncode is not None):
            return json.dumps({"error": f"MCP server '{self.name}' is not running (failed to start)"}, ensure_ascii=False)
        try:
            if self.url:
                res = await self.send_request_http("tools/call", {
                    "name": tool_name,
                    "arguments": arguments
                })
            else:
                res = await self.send_request("tools/call", {
                    "name": tool_name,
                    "arguments": arguments
                })
        except Exception as e:
            logger.warning(f"MCP server '{self.name}' call_tool '{tool_name}' failed: {e}")
            return json.dumps({"error": f"MCP server '{self.name}' tool '{tool_name}' failed: {e}"}, ensure_ascii=False)
        if "error" in res:
            return json.dumps({"error": res["error"]}, ensure_ascii=False)
        content_list = res.get("result", {}).get("content", [])
        if content_list and content_list[0].get("type") == "text":
            return content_list[0].get("text")
        return json.dumps(res.get("result", {}), ensure_ascii=False)

    async def shutdown(self):
        if self.process:
            logger.info(f"Stopping MCP server '{self.name}'")
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception as e:
                logger.error(f"Error terminating MCP server '{self.name}': {e}")


# Global registry
mcp_clients: Dict[str, MCPServerClient] = {}
mcp_tool_to_server: Dict[str, str] = {}

async def init_mcp_servers(target_servers: Optional[Iterable[str]] = None):
    backend_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(backend_dir, "data", "mcp_config.json")
    
    if not os.path.exists(config_path):
        config_path = os.path.join(os.path.dirname(backend_dir), "mcp_config.json")
        if not os.path.exists(config_path):
            logger.info("No mcp_config.json found, skipping MCP client setup.")
            return

    try:
        logger.info(f"Loading MCP config from {config_path}")
        with open(config_path, "r") as f:
            config = json.load(f)
        servers = config.get("mcpServers", {})
        target_set = set(target_servers) if target_servers is not None else None
        for name, srv_config in servers.items():
            if target_set is not None and name not in target_set:
                continue
            if srv_config.get("disabled", False):
                logger.info(f"MCP server '{name}' is disabled in config, skipping.")
                continue

            existing = mcp_clients.get(name)
            if existing and getattr(existing, "is_connected", False):
                logger.debug(f"MCP server '{name}' is already connected, skipping re-init.")
                continue

            now = time.time()
            if srv_config.get("optional", False) and now < _server_offline_cooldowns.get(name, 0.0):
                logger.debug(f"MCP server '{name}' is optional and in offline cooldown ({_server_offline_cooldowns[name] - now:.0f}s remaining), skipping.")
                continue

            client = MCPServerClient(name, srv_config)
            try:
                await client.start()
            except Exception as start_err:
                if srv_config.get("optional", False):
                    _server_offline_cooldowns[name] = time.time() + 300.0
                    logger.info(f"Optional MCP server '{name}' start skipped or offline: {start_err}")
                else:
                    logger.warning(f"MCP server '{name}' start encountered error: {start_err}")

            mcp_clients[name] = client
            if client.is_connected:
                _server_offline_cooldowns.pop(name, None)
                for tool in client.tools:
                    tool_name = tool["name"]
                    mcp_tool_to_server[tool_name] = name
                    
                    # Dynamically register tool schema in tools.py TOOLS_SCHEMA
                    from backend.tools import TOOLS_SCHEMA
                    if not any(t.get("function", {}).get("name") == tool_name for t in TOOLS_SCHEMA):
                        TOOLS_SCHEMA.append({
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "description": tool.get("description", ""),
                                "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})
                            }
                        })
            elif srv_config.get("optional", False):
                _server_offline_cooldowns[name] = time.time() + 300.0
    except Exception as e:
        logger.error(f"Error loading MCP servers: {e}")

async def handle_mcp_tool(name: str, arguments: Dict[str, Any]) -> str:
    server_name = mcp_tool_to_server.get(name)
    if not server_name or server_name not in mcp_clients:
        return json.dumps({"error": f"MCP server not found for tool {name}"})
    return await mcp_clients[server_name].call_tool(name, arguments)

async def shutdown_mcp_servers():
    for client in list(mcp_clients.values()):
        await client.shutdown()
    mcp_clients.clear()
    mcp_tool_to_server.clear()
