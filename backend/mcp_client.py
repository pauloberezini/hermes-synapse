import asyncio
import json
import logging
import os
import subprocess
import sys
from typing import Dict, Any, List

logger = logging.getLogger("hermes.mcp_client")


def _base_process_environment() -> Dict[str, str]:
    """Do not leak the backend's API keys and tokens into third-party MCP processes."""
    allowed = {
        "HOME",
        "LANG",
        "LC_ALL",
        "PATH",
        "SSL_CERT_DIR",
        "SSL_CERT_FILE",
        "TMPDIR",
    }
    return {key: value for key, value in os.environ.items() if key in allowed}


class MCPServerClient:
    def __init__(self, name: str, config: Dict[str, Any]):
        from backend.mcp_governance import expand_environment, validate_server_config

        validated = validate_server_config(name, config)
        self.name = name
        self.command = validated["command"]
        self.args = validated["args"]
        self.env = {**_base_process_environment(), **expand_environment(validated["env"])}
        self.process = None
        self.reader = None
        self.writer = None
        self.req_id = 0
        self.pending_requests = {}
        self.tools = []

    async def start(self):
        try:
            logger.info(f"Starting MCP server '{self.name}': {self.command} {' '.join(self.args)}")
            self.process = await asyncio.create_subprocess_exec(
                self.command,
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
            logger.info(f"MCP server '{self.name}' successfully initialized with {len(self.tools)} tools.")
        except Exception as e:
            logger.error(f"Failed to start MCP server '{self.name}': {e}")
            if self.process and self.process.returncode is None:
                self.process.terminate()
                await self.process.wait()
            raise

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
        res = await self.send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })
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


def register_client_tools(name: str, client: MCPServerClient) -> None:
    from backend.tools import TOOLS_SCHEMA

    for tool in client.tools:
        tool_name = tool["name"]
        mcp_tool_to_server[tool_name] = name
        if not any(item.get("function", {}).get("name") == tool_name for item in TOOLS_SCHEMA):
            TOOLS_SCHEMA.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}}),
                },
            })


async def init_mcp_servers():
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
        for name, srv_config in servers.items():
            try:
                client = MCPServerClient(name, srv_config)
                await client.start()
                mcp_clients[name] = client
                register_client_tools(name, client)
            except Exception as exc:
                logger.error("Skipping unsafe or unavailable MCP server '%s': %s", name, exc)
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
