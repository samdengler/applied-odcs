"""Compares each runtime recording with its Lambda function target recording.

`compare_live.py [lambda dir] [runtime dir]`, by default
orders/tests/events and orders/tests/events/runtime.  Each live-*.json in
the runtime directory is paired by name.  The outcome must match: the HTTP
status, error or result, the error message, the row ids, and each row's
field names.  Any difference fails.  Differences in the event envelope
(the key paths of the interceptor events and of the tool result,
structuredContent, the number of content items, isStreamingResponse) are
printed as findings and do not fail.
"""

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_call_module():
    spec = importlib.util.spec_from_file_location("applied_odcs_call", ROOT / "client" / "call.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


payload_of = _load_call_module().payload_of


def outcome(fixture: dict) -> dict:
    status, body = fixture["observed"]["status"], fixture["observed"]["body"] or {}
    if "error" in body:
        return {"status": status, "kind": "error", "message": body["error"].get("message")}
    result = body.get("result") or {}
    payload = payload_of(body)
    if result.get("isError"):
        return {"status": status, "kind": "isError", "message": payload}
    rows = payload if isinstance(payload, list) else [payload]
    return {"status": status, "kind": "list" if isinstance(payload, list) else "object",
            "ids": [row.get("id") for row in rows], "fields": [sorted(row) for row in rows]}


def key_paths(value, prefix="") -> set:
    """Every key path in value; list items share one path, and the values
    of headers are left out, since they name the call."""
    paths = set()
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}"
            paths.add(path)
            if key.lower() != "headers":
                paths |= key_paths(item, path)
    elif isinstance(value, list):
        for item in value:
            paths |= key_paths(item, prefix + "[]")
    return paths


def topmost(paths: set) -> list:
    """The paths whose parent is not among them."""
    return sorted(p for p in paths if not any(p != q and p.startswith(q + ".") or p.startswith(q + "[]") for q in paths))


def envelope(fixture: dict) -> dict:
    response = fixture.get("response") or {}
    gateway_response = (response.get("mcp") or {}).get("gatewayResponse") or {}
    result = ((fixture["observed"]["body"] or {}).get("result")) or {}
    raw = ((gateway_response.get("body") or {}).get("result")) or {}
    return {
        "request event keys": key_paths(fixture["request"]),
        "response event": "present" if fixture.get("response") else "absent",
        "response event keys": key_paths(response),
        "isStreamingResponse": gateway_response.get("isStreamingResponse"),
        "result keys from the target": sorted(raw),
        "content items from the target": len(raw.get("content") or []),
        "result keys at the caller": sorted(result),
    }


def main(argv: list[str]) -> int:
    lambda_dir = Path(argv[0]) if argv else ROOT / "orders/tests/events"
    runtime_dir = Path(argv[1]) if len(argv) > 1 else ROOT / "orders/tests/events/runtime"
    runtime_files = sorted(runtime_dir.glob("live-*.json"))
    if not runtime_files:
        print(f"no recordings in {runtime_dir}", file=sys.stderr)
        return 1
    failures, findings = 0, []
    for runtime_path in runtime_files:
        lambda_path = lambda_dir / runtime_path.name
        if not lambda_path.exists():
            print(f"FAIL  {runtime_path.name}: no Lambda function target recording")
            failures += 1
            continue
        lam, run = json.loads(lambda_path.read_text()), json.loads(runtime_path.read_text())
        a, b = outcome(lam), outcome(run)
        if a == b:
            rows = f"{len(a['ids'])} rows, fields {sorted({len(f) for f in a['fields']})}" if "ids" in a else a["message"]
            print(f"same  {runtime_path.stem}: {a['status']} {a['kind']}: {rows}")
        else:
            failures += 1
            print(f"FAIL  {runtime_path.stem}\n  lambda:  {json.dumps(a)}\n  runtime: {json.dumps(b)}")
        ea, eb = envelope(lam), envelope(run)
        for key in ea:
            if key in ("response event keys", "isStreamingResponse") and ea["response event"] != eb["response event"]:
                continue  # one side has no response event; reported once above
            if ea[key] != eb[key]:
                if isinstance(ea[key], set):
                    detail = (f"only lambda: {topmost(ea[key] - eb[key]) or '(none)'}; "
                              f"only runtime: {topmost(eb[key] - ea[key]) or '(none)'}")
                else:
                    detail = f"lambda {ea[key]!r}, runtime {eb[key]!r}"
                findings.append(f"{runtime_path.stem}: {key}: {detail}")
    print(f"\n{len(runtime_files) - failures} of {len(runtime_files)} outcomes match")
    if findings:
        print("\nenvelope findings:")
        for line in findings:
            print(f"  {line}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
