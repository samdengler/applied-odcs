"""Times the server's part of each tool call from the Runtime log streams.

`runtime_sessions.py <minutes>`: for each session stream that began in the
last `minutes`, the milliseconds from its first log line to the initialize
response, from the initialize response to the tool's answer, and of the
tools/call handling, as medians.  It also counts the sessions that log a
server start, the warm-up, uvicorn's invalid request warning, and a /ping
probe.  The log group is RUNTIME_LOG_GROUP.
"""

import json
import os
import statistics
import subprocess
import sys
import time

LG = os.environ["RUNTIME_LOG_GROUP"]
since = int((time.time() - 60 * float(sys.argv[1] if len(sys.argv) > 1 else 5)) * 1000)


def aws(*a):
    return json.loads(subprocess.check_output(["aws", "--region", os.environ["AWS_REGION"], "--output", "json", *a]))


streams = aws("logs", "describe-log-streams", "--log-group-name", LG, "--order-by", "LastEventTime",
              "--descending", "--max-items", "200")["logStreams"]
rows, notes = [], {}
for s in streams:
    if s.get("firstEventTimestamp", 0) < since:
        continue
    ev = aws("logs", "get-log-events", "--log-group-name", LG, "--log-stream-name", s["logStreamName"],
             "--start-from-head", "--limit", "40")["events"]
    msgs = [(e["timestamp"], e["message"].strip()) for e in ev]
    for key in ("Started server process", "warm-up:", "Invalid HTTP request", "GET /ping"):
        notes[key] = notes.get(key, 0) + any(key in m for _, m in msgs)
    idx = next((i for i, (_, m) in enumerate(msgs) if "CallToolRequest" in m), None)
    if idx is None:
        continue
    posts = [i for i, (_, m) in enumerate(msgs[:idx]) if '"POST /mcp' in m]
    if len(posts) < 3:
        continue  # the snapshot build's stream, where the warm-up's requests do not pass uvicorn
    init = posts[-3]  # initialize, notifications/initialized, tools/call
    done = next(t for t, m in msgs[idx:] if m.startswith("Terminating"))
    rows.append((msgs[init][0] - msgs[0][0], done - msgs[init][0], done - msgs[idx][0]))
print(f"{len(rows)} sessions; lines seen in N sessions: {notes}")
for i, name in enumerate(["first line to initialize", "initialize to tool answer", "tool handling"]):
    v = [r[i] for r in rows]
    if v:
        print(f"  {name}: median {statistics.median(v):.0f} ms, min {min(v)}, max {max(v)}")
