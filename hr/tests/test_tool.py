"""The tool Lambda against its data and the Gateway schema."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

HR = Path(__file__).resolve().parents[1]
FIELDS = {"employeeId", "name", "workEmail", "homeAddress", "personalPhone", "salary", "bankAccount"}
ADDRESS = {"line1", "city", "postalCode", "country"}


def _load():
    spec = importlib.util.spec_from_file_location("hr_tool_handler", HR / "tool" / "handler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ctx(name):
    return SimpleNamespace(client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": name}))


@pytest.fixture
def call():
    mod = _load()
    return lambda tool, event=None: mod.handler(event or {}, _ctx(f"hr___{tool}"))


def test_get_employee_returns_alice_with_all_fields(call):
    e = call("get_employee", {"employeeId": "alice"})
    assert e["name"] == "Alice Moreau" and set(e) == FIELDS


def test_update_employee_changes_the_phone(call):
    e = call("update_employee", {"employeeId": "bob", "changes": {"personalPhone": "+1 207 555 0100"}})
    assert e["personalPhone"] == "+1 207 555 0100"
    assert call("get_employee", {"employeeId": "bob"})["personalPhone"] == "+1 207 555 0100"


def test_nested_change_leaves_other_address_lines(call):
    e = call("update_employee", {"employeeId": "alice",
                                 "changes": {"homeAddress": {"line1": "48 Pine St"}}})
    assert e["homeAddress"] == {"line1": "48 Pine St", "city": "Portland", "postalCode": "04101", "country": "US"}


def test_writes_do_not_leak_between_tests(call):
    assert call("get_employee", {"employeeId": "alice"})["homeAddress"]["line1"] == "12 Harbor St"
    assert call("get_employee", {"employeeId": "bob"})["personalPhone"] == "+1 207 555 0187"


def test_unknown_tool_raises(call):
    with pytest.raises(ValueError, match="unknown tool"):
        call("drop_table")


def test_missing_tool_name_raises():
    ctx = SimpleNamespace(client_context=SimpleNamespace(custom={}))
    with pytest.raises(ValueError, match="unknown tool"):
        _load().handler({}, ctx)


def test_unknown_employee_raises(call):
    with pytest.raises(ValueError, match="unknown employeeId"):
        call("get_employee", {"employeeId": "nobody"})
    with pytest.raises(ValueError, match="unknown employeeId"):
        call("update_employee", {"employeeId": "nobody", "changes": {}})


def test_schema_matches_handler_and_usecase():
    from hr.usecase import TOOLS
    schema = json.loads((HR / "tools.json").read_text())
    names = {t["name"] for t in schema}
    assert names == set(_load().TOOLS)
    assert {n.removeprefix("hr___") for n in TOOLS} <= names


def test_output_schemas_have_the_contract_leaves():
    for t in json.loads((HR / "tools.json").read_text()):
        employee = t["outputSchema"]
        assert set(employee["properties"]) == FIELDS
        assert set(employee["properties"]["homeAddress"]["properties"]) == ADDRESS
