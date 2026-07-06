#!/usr/bin/env python3
import sys
import os
import json
import time
import urllib.request
import urllib.parse
import urllib.error

# Setup simple logger to stderr (stdin/stdout are for JSON-RPC)
def log(msg):
    sys.stderr.write(f"[OpenAPI-Proxy] {msg}\n")
    sys.stderr.flush()

# Load settings from environment
OPENAPI_URL = os.getenv("OPENAPI_URL", "https://mcp-antonbustrov.waw0.amvera.tech/openapi.json")
AUTH_TOKEN_URL = os.getenv("AUTH_TOKEN_URL", "https://mcp-antonbustrov.waw0.amvera.tech/token")
AUTH_USERNAME = os.getenv("AUTH_USERNAME", "")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "")
STATIC_BEARER_TOKEN = os.getenv("STATIC_BEARER_TOKEN", "")

# Global state
token = ""
token_expiry = 0
openapi_spec = {}
tools_map = {} # tool_name -> spec info

def get_token():
    global token, token_expiry
    if STATIC_BEARER_TOKEN:
        return STATIC_BEARER_TOKEN
        
    if token and time.time() < token_expiry - 60:
        return token

    if not AUTH_USERNAME or not AUTH_PASSWORD:
        return ""

    log(f"Fetching token from {AUTH_TOKEN_URL}...")
    try:
        data = urllib.parse.urlencode({
            "grant_type": "password",
            "username": AUTH_USERNAME,
            "password": AUTH_PASSWORD,
            "scope": "",
            "client_id": "string",
            "client_secret": "string"
        }).encode("utf-8")
        
        req = urllib.request.Request(AUTH_TOKEN_URL, data=data, method="POST")
        req.add_header("accept", "application/json")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        
        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            token = res_data.get("access_token")
            # Default to 15 min expiry if not specified
            expires_in = res_data.get("expires_in", 900)
            token_expiry = time.time() + expires_in
            log("Token successfully acquired.")
            return token
    except Exception as e:
        log(f"Token acquisition failed: {e}")
        return ""

def load_openapi_spec():
    global openapi_spec
    log(f"Loading OpenAPI specification from {OPENAPI_URL}...")
    try:
        with urllib.request.urlopen(OPENAPI_URL, timeout=15) as response:
            openapi_spec = json.loads(response.read().decode("utf-8"))
        log("OpenAPI specification loaded successfully.")
        parse_tools()
    except Exception as e:
        log(f"Failed to load OpenAPI spec: {e}")

def parse_tools():
    global tools_map
    paths = openapi_spec.get("paths", {})
    for path, methods in paths.items():
        for method, details in methods.items():
            if method.lower() not in ("get", "post", "put", "delete"):
                continue
                
            op_id = details.get("operationId")
            if not op_id:
                # Generate unique operationId from path and method
                clean_path = path.replace("/", "_").replace("{", "").replace("}", "")
                op_id = f"{method.lower()}{clean_path}"
                
            summary = details.get("summary", "")
            description = details.get("description", "")
            doc_string = f"{summary}\n\n{description}" if summary else description
            
            # Map parameters into schema
            parameters = details.get("parameters", [])
            properties = {}
            required = []
            
            for param in parameters:
                p_name = param.get("name")
                p_required = param.get("required", False)
                p_schema = param.get("schema", {"type": "string"})
                p_desc = param.get("description", "")
                
                properties[p_name] = {
                    "type": p_schema.get("type", "string"),
                    "description": p_desc or p_name
                }
                if p_required:
                    required.append(p_name)
            
            # Save mapping info
            tools_map[op_id] = {
                "path": path,
                "method": method.upper(),
                "parameters": parameters,
                "tool_def": {
                    "name": op_id,
                    "description": doc_string[:1000], # Keep description clean
                    "inputSchema": {
                        "type": "object",
                        "properties": properties,
                        "required": required
                    }
                }
            }
    log(f"Mapped {len(tools_map)} tools from OpenAPI spec.")

def call_api(tool_name, arguments):
    info = tools_map.get(tool_name)
    if not info:
        return f"Error: Tool {tool_name} not found."
        
    path = info["path"]
    method = info["method"]
    
    # Separate arguments based on where they belong (path or query)
    path_args = {}
    query_args = {}
    
    for param in info["parameters"]:
        p_name = param.get("name")
        p_in = param.get("in", "query")
        if p_name in arguments:
            if p_in == "path":
                path_args[p_name] = str(arguments[p_name])
            else:
                query_args[p_name] = arguments[p_name]
                
    # Replace path parameters
    url_path = path
    for k, v in path_args.items():
        url_path = url_path.replace(f"{{{k}}}", urllib.parse.quote(v))
        
    # Build complete URL
    server_url = openapi_spec.get("servers", [{}])[0].get("url")
    if not server_url:
        # Fallback to base domain of openapi URL
        parsed = urllib.parse.urlparse(OPENAPI_URL)
        server_url = f"{parsed.scheme}://{parsed.netloc}"
        
    full_url = f"{server_url.rstrip('/')}{url_path}"
    if query_args:
        full_url += f"?{urllib.parse.urlencode(query_args)}"
        
    log(f"Making API request: {method} {full_url}")
    
    # Try the request (with authorization if token is available)
    for retry in range(2):
        try:
            req = urllib.request.Request(full_url, method=method)
            req.add_header("accept", "application/json")
            
            t = get_token()
            if t:
                req.add_header("Authorization", f"Bearer {t}")
                
            with urllib.request.urlopen(req, timeout=30) as response:
                content = response.read().decode("utf-8")
                return content
        except urllib.error.HTTPError as e:
            if e.code == 401 and retry == 0 and AUTH_USERNAME:
                log("Received 401. Refreshing token and retrying...")
                global token
                token = "" # Force refresh
                continue
            error_msg = e.read().decode("utf-8")
            log(f"API Error {e.code}: {error_msg}")
            return json.dumps({"error": f"API returned HTTP {e.code}", "detail": error_msg})
        except Exception as e:
            log(f"Request failed: {e}")
            return json.dumps({"error": str(e)})
            
    return "Error calling API: Unauthorized."

# ─── Stdio JSON-RPC Loop ──────────────────────────────────────────────────────

def main():
    load_openapi_spec()
    
    while True:
        line = sys.stdin.readline()
        if not line:
            break
            
        try:
            req = json.loads(line.strip())
            method = req.get("method")
            msg_id = req.get("id")
            
            if method == "initialize":
                res = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "serverInfo": {
                            "name": "openapi-bridge-server",
                            "version": "1.0.0"
                        }
                    }
                }
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
                
            elif method == "notifications/initialized":
                # Notifications don't get a response
                pass
                
            elif method == "tools/list":
                tools_list = [info["tool_def"] for info in tools_map.values()]
                res = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "tools": tools_list
                    }
                }
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
                
            elif method == "tools/call":
                params = req.get("params", {})
                tool_name = params.get("name")
                arguments = params.get("arguments", {})
                
                result_text = call_api(tool_name, arguments)
                
                res = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": result_text
                            }
                        ]
                    }
                }
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
                
            elif msg_id is not None:
                # Unsupported method
                res = {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method {method} not found"
                    }
                }
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
                
        except Exception as e:
            log(f"Error handling RPC frame: {e}")

if __name__ == "__main__":
    main()
