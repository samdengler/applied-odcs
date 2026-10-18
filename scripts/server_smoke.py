"""Runs build/server/server.py on the Mac and checks it over HTTP.

Starts the server, posts initialize and tools/list to
http://127.0.0.1:8000/mcp, asserts the five tools, and stops it.  Stateless
streamable HTTP, so no Mcp-Session-Id comes back.
"""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8000/mcp"
TOOLS = {"get_order", "update_order", "cancel_order", "refund_order", "list_orders"}
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def post(message: dict) -> tuple[dict, dict]:
    req = urllib.request.Request(URL, data=json.dumps(message).encode(), headers=HEADERS, method="POST")
    with urllib.request.urlopen(req, timeout=10) as resp:
        lines = [line[5:].strip() for line in resp.read().decode().splitlines() if line.startswith("data:")]
        return dict(resp.headers), json.loads(lines[-1])


def main() -> int:
    server = subprocess.Popen([sys.executable, str(ROOT / "build/server/server.py")],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        for _ in range(50):
            try:
                headers, init = post({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                    "protocolVersion": "2025-06-18", "capabilities": {},
                    "clientInfo": {"name": "server-smoke", "version": "0"}}})
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(0.2)
        else:
            print("server did not answer on " + URL, file=sys.stderr)
            return 1
        info = init["result"]["serverInfo"]
        _, listed = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in listed["result"]["tools"]}
        assert names == TOOLS, names
        assert not any(k.lower() == "mcp-session-id" for k in headers), headers
        print(f"server ok: {info['name']} {info['version']} answered initialize "
              f"({init['result']['protocolVersion']}) and tools/list with {', '.join(sorted(names))}")
        return 0
    finally:
        server.terminate()
        server.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
