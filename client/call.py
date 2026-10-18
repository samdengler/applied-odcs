"""A minimal MCP client over streamable HTTP, standard library only.

`call(user, tool, arguments)` runs initialize, notifications/initialized,
and tools/call against GATEWAY_URL with the user's access token, and returns
the id, the HTTP status, and the JSON-RPC message of the tools/call response.
"""

import importlib.util
import json
import os
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path

PREFIX = "orders___"


def _load_token_module():
    # A plain `import token` would find the standard library module.
    spec = importlib.util.spec_from_file_location("applied_odcs_token", Path(__file__).with_name("token.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parse_body(raw: str) -> dict | None:
    """Parse a response body that is plain JSON or an SSE stream of `data:` lines."""
    text = raw.strip()
    if not text:
        return None
    if text.startswith("{") or text.startswith("["):
        return json.loads(text)
    messages = []
    for line in text.splitlines():
        if line.startswith("data:"):
            data = line[5:].strip()
            if data:
                messages.append(json.loads(data))
    if not messages:
        return None
    return messages[-1]


def _post(url: str, headers: dict, message: dict) -> tuple[int, dict, dict | None]:
    req = urllib.request.Request(url, data=json.dumps(message).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, dict(resp.headers), parse_body(resp.read().decode())
    except urllib.error.HTTPError as err:
        return err.code, dict(err.headers), parse_body(err.read().decode())


def session(user: str) -> dict:
    """initialize and notifications/initialized as user; the headers for the next request."""
    token = _load_token_module().access_token(user)
    url = os.environ["GATEWAY_URL"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    init = {
        "jsonrpc": "2.0",
        "id": random.randint(10**8, 10**9 - 1),
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "applied-odcs", "version": "0.1"},
        },
    }
    _, resp_headers, _ = _post(url, headers, init)
    for key, value in resp_headers.items():
        if key.lower() == "mcp-session-id":
            headers["Mcp-Session-Id"] = value
    _post(url, headers, {"jsonrpc": "2.0", "method": "notifications/initialized"})
    return headers


def call(user: str, tool: str, arguments: dict) -> dict:
    url = os.environ["GATEWAY_URL"]
    headers = session(user)
    rpc_id = random.randint(10**8, 10**9 - 1)
    status, _, body = _post(
        url,
        headers,
        {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "method": "tools/call",
            "params": {"name": PREFIX + tool, "arguments": arguments},
        },
    )
    return {"id": rpc_id, "status": status, "body": body}


def payload_of(body: dict | None):
    """The tool's payload: structuredContent if present, else the first text item parsed as JSON.
    An MCP server sends a list as {"result": [...]} in structuredContent; that is the list."""
    result = (body or {}).get("result") or {}
    if "structuredContent" in result:
        content = result["structuredContent"]
        if isinstance(content, dict) and set(content) == {"result"} and isinstance(content["result"], list):
            return content["result"]
        return content
    for item in result.get("content") or []:
        if item.get("type") == "text":
            try:
                return json.loads(item["text"])
            except ValueError:
                return item["text"]
    return None


def render(user: str, tool: str, outcome: dict) -> str:
    status, body = outcome["status"], outcome["body"] or {}
    if "error" in body:
        err = body["error"]
        message = err.get("message", err) if isinstance(err, dict) else err
        return f"{user}  {tool}  {status}  error\n{message}"
    result = body.get("result") or {}
    payload = payload_of(body)
    if result.get("isError"):
        return f"{user}  {tool}  {status}  isError\n{payload if isinstance(payload, str) else json.dumps(payload, indent=2)}"
    size = f"{len(payload)} rows" if isinstance(payload, list) else "1 object"
    return f"{user}  {tool}  {status}  {size}\n{json.dumps(payload, indent=2)}"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: call.py <user> <tool> ['<json args>']", file=sys.stderr)
        return 2
    user, tool = argv[0], argv[1]
    arguments = json.loads(argv[2]) if len(argv) > 2 and argv[2].strip() else {}
    print(render(user, tool, call(user, tool, arguments)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
