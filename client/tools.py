"""tools/list through the Gateway as one user: `tools.py <user>` prints each
tool's name and its input and output schema property names."""

import importlib.util
import random
import sys
from pathlib import Path


def _load_call_module():
    spec = importlib.util.spec_from_file_location("applied_odcs_call", Path(__file__).with_name("call.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def list_tools(user: str) -> tuple[int, dict | None]:
    call = _load_call_module()
    headers = call.session(user)
    status, _, body = call._post(call.os.environ["GATEWAY_URL"], headers,
                                 {"jsonrpc": "2.0", "id": random.randint(10**8, 10**9 - 1), "method": "tools/list"})
    return status, body


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: tools.py <user>", file=sys.stderr)
        return 2
    status, body = list_tools(argv[0])
    tools = ((body or {}).get("result") or {}).get("tools")
    if tools is None:
        print(f"{argv[0]}  tools/list  {status}\n{body}")
        return 1
    print(f"{argv[0]}  tools/list  {status}  {len(tools)} tools")
    for tool in tools:
        out = tool.get("outputSchema") or {}
        print(f"{tool['name']}  in: {', '.join(tool['inputSchema'].get('properties', {})) or '(none)'}  "
              f"out: {', '.join(out.get('properties', {})) or out.get('type', '(none)')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
