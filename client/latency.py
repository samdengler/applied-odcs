"""Times tools/call round trips through the Gateway as one user.

`latency.py <user> <tool> [n] [warmup]`: one token and one initialize, then
`warmup` calls that are not counted and `n` timed calls of the tool with no
arguments.  Prints each time, the median, and the worst, in milliseconds.
Only the tools/call POST is timed, not the sign-in or initialize.
"""

import importlib.util
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path


def _load_call_module():
    spec = importlib.util.spec_from_file_location("applied_odcs_call", Path(__file__).with_name("call.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: latency.py <user> <tool> [n] [warmup]", file=sys.stderr)
        return 2
    user, tool = argv[0], argv[1]
    n = int(argv[2]) if len(argv) > 2 else 10
    warmup = int(argv[3]) if len(argv) > 3 else 1
    call = _load_call_module()
    url = os.environ["GATEWAY_URL"]
    headers = call.session(user)
    times = []
    for i in range(warmup + n):
        message = {"jsonrpc": "2.0", "id": random.randint(10**8, 10**9 - 1), "method": "tools/call",
                   "params": {"name": call.PREFIX + tool, "arguments": {}}}
        start = time.perf_counter()
        status, _, body = call._post(url, headers, message)
        elapsed = (time.perf_counter() - start) * 1000
        rows = call.payload_of(body)
        if status != 200 or not isinstance(rows, list):
            print(f"call {i}: {status} {json.dumps(body)[:200]}", file=sys.stderr)
            return 1
        if i >= warmup:
            times.append(elapsed)
    print(f"{url.split('.')[0].removeprefix('https://')}  {user}  {tool}  {n} calls after {warmup} warmup: "
          + " ".join(f"{t:.0f}" for t in times))
    print(f"median {statistics.median(times):.0f} ms, worst {max(times):.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
