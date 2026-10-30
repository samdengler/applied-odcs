"""Record a live Gateway call as a test fixture.

Makes the call through call.call, then reads the two interceptors' logged
events (the handlers log them when CEDAR_ODCS_RECORD=1) from CloudWatch Logs,
picks the ones whose JSON-RPC id matches, redacts bearer token signatures, and
writes hr/tests/live/live-<user>-<tool>[-<employeeId>][-<extra field>...].json.
"""

import importlib.util
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVENTS = ROOT / "hr" / "tests" / "live"
BEARER = re.compile(r"(Bearer\s+[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+)\.[A-Za-z0-9_\-=]*")
POLL_SECONDS = 60
POLL_EVERY = 5


def _load_call_module():
    spec = importlib.util.spec_from_file_location("applied_odcs_call", Path(__file__).with_name("call.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# Headers that name the caller's network rather than the call: the
# caller's public address is replaced with a documentation address.
ADDRESS_HEADERS = {"x-forwarded-for": "203.0.113.10"}


def redact(value):
    """Replace the signature of every bearer token found anywhere in value,
    and the caller's address in X-Forwarded-For."""
    if isinstance(value, str):
        return BEARER.sub(r"\1.signature-redacted", value)
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, dict):
        return {k: ADDRESS_HEADERS.get(k.lower(), redact(v)) if isinstance(v, str) else redact(v)
                for k, v in value.items()}
    return value


def parse_log_message(message: str, marker: str) -> dict | None:
    """The JSON after `marker` to the end of the message, or None."""
    at = message.find(marker)
    if at < 0:
        return None
    try:
        parsed = json.loads(message[at + len(marker):].strip())
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def request_id(event: dict):
    body = (((event.get("mcp") or {}).get("gatewayRequest")) or {}).get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return None
    return body.get("id") if isinstance(body, dict) else None


def find_event(messages: list[str], marker: str, rpc_id) -> dict | None:
    found = None
    for message in messages:
        event = parse_log_message(message, marker)
        if event is not None and request_id(event) == rpc_id:
            found = event
    return found


def fetch_messages(logs, group: str, marker: str, start_ms: int) -> list[str]:
    messages, token = [], None
    while True:
        kwargs = {"logGroupName": group, "startTime": start_ms, "filterPattern": f'"{marker.strip()}"'}
        if token:
            kwargs["nextToken"] = token
        page = logs.filter_log_events(**kwargs)
        messages += [e["message"] for e in page.get("events", [])]
        token = page.get("nextToken")
        if not token:
            return messages


ADDRESS_LINES = {"line1", "city", "postalCode", "country"}


def output_name(user: str, tool: str, arguments: dict) -> str:
    name = f"live-{user}-{tool}"
    if arguments.get("employeeId"):
        name += f"-{arguments['employeeId']}"
    # Two address changes of one employee differ only in a field sent
    # beside the four lines.
    if isinstance(arguments.get("address"), dict):
        name += "".join(f"-{field}" for field in sorted(set(arguments["address"]) - ADDRESS_LINES))
    return name + ".json"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: record.py <user> <tool> ['<json args>']", file=sys.stderr)
        return 2
    import boto3

    user, tool = argv[0], argv[1]
    arguments = json.loads(argv[2]) if len(argv) > 2 and argv[2].strip() else {}
    call_module = _load_call_module()
    start_ms = int((time.time() - 60) * 1000)
    outcome = call_module.call(user, tool, arguments)
    rpc_id = outcome["id"]
    denied = outcome["status"] == 403

    logs = boto3.client("logs", region_name=os.environ.get("AWS_REGION", "us-east-1"))
    request_event = response_event = None
    deadline = time.time() + POLL_SECONDS
    while True:
        if request_event is None:
            request_event = find_event(
                fetch_messages(logs, os.environ["REQUEST_LOG_GROUP"], "record request ", start_ms),
                "record request ",
                rpc_id,
            )
        if request_event is not None and response_event is None and not denied:
            response_event = find_event(
                fetch_messages(logs, os.environ["RESPONSE_LOG_GROUP"], "record response ", start_ms),
                "record response ",
                rpc_id,
            )
        if request_event is not None and (denied or response_event is not None):
            break
        if time.time() >= deadline:
            break
        time.sleep(POLL_EVERY)

    if request_event is None:
        print(f"no request event with id {rpc_id} found in {POLL_SECONDS}s; nothing written", file=sys.stderr)
        return 1
    if response_event is None and not denied:
        print("warning: no response event found; saving response: null", file=sys.stderr)

    fixture = {
        "user": user,
        "tool": tool,
        "arguments": arguments,
        "request": redact(request_event),
        "response": redact(response_event) if response_event is not None else None,
        "observed": {"status": outcome["status"], "body": outcome["body"]},
    }
    EVENTS.mkdir(parents=True, exist_ok=True)
    path = EVENTS / output_name(user, tool, arguments)
    path.write_text(json.dumps(fixture, indent=2) + "\n")
    print(path)
    print(f"{user}  {tool}  {outcome['status']}  request={'yes'} response={'yes' if response_event else 'null'}")

    tool_group = os.environ.get("TOOL_LOG_GROUP")
    if tool_group:
        try:
            lines = [m for m in fetch_messages(logs, tool_group, "client_context ", start_ms) if "client_context " in m]
        except Exception as err:  # the tool log is a convenience
            lines = []
            print(f"could not read tool log: {err}", file=sys.stderr)
        if lines:
            print(lines[-1].strip())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
