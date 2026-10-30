"""Offline checks of the client helpers: SSE parsing, redaction, log parsing."""

import importlib.util
import json
from pathlib import Path

CLIENT = Path(__file__).resolve().parent


def _load(name: str):
    spec = importlib.util.spec_from_file_location(f"client_{name}", CLIENT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


call, record = _load("call"), _load("record")


def test_parse_body_reads_plain_json_and_sse():
    assert call.parse_body('{"id": 1}') == {"id": 1}
    assert call.parse_body('event: message\ndata: {"id": 2}\n\n') == {"id": 2}
    assert call.parse_body("") is None


def test_redact_replaces_the_signature_anywhere():
    out = record.redact({"h": {"Authorization": "Bearer aaa.bbb.ccc"}, "l": ["x Bearer d.e.f y"]})
    assert out["h"]["Authorization"] == "Bearer aaa.bbb.signature-redacted"
    assert out["l"][0] == "x Bearer d.e.signature-redacted y"


def test_log_message_parsing_finds_the_marker_and_the_id():
    event = {"mcp": {"gatewayRequest": {"body": json.dumps({"id": 42})}}}
    message = "[DEBUG]\t2026-10-17T00:00:00Z\tabc-123\trecord request " + json.dumps(event) + "\n"
    assert record.parse_log_message(message, "record request ") == event
    assert record.find_event([message], "record request ", 42) == event
    assert record.find_event([message], "record request ", 7) is None
    assert record.parse_log_message("nothing here", "record request ") is None


def test_output_name_carries_the_employee_and_the_fields_an_update_sets():
    assert record.output_name("maya", "list_employees", {}) == "live-maya-list_employees.json"
    assert record.output_name("bob", "get_employee", {"employeeId": "alice"}) == "live-bob-get_employee-alice.json"
    assert (record.output_name("alice", "update_employee", {"employeeId": "alice", "changes": {"homeAddress": {}}})
            == "live-alice-update_employee-alice-homeAddress.json")
