"""The tool Lambda against its data and the Gateway schema."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

HR = Path(__file__).resolve().parents[1]
EMPLOYEE = {"employeeId", "name", "workEmail", "homeAddress", "personalPhone", "salary", "bankAccount"}
CHANGE = {"changeId", "employeeId", "homeAddress", "effectiveDate", "payrollNotified", "fraudScore"}
MOVED = {"line1": "48 Pine St", "city": "Portland", "postalCode": "04102", "country": "US"}


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


def test_get_profile_returns_every_field(call):
    e = call("get_profile", {"employeeId": "alice"})
    assert e["name"] == "Alice Moreau" and set(e) == EMPLOYEE


def test_update_address_returns_the_change_not_the_employee(call):
    change = call("update_address", {"employeeId": "alice", "address": MOVED})
    assert set(change) == CHANGE
    assert change["changeId"] == "chg-0001" and change["homeAddress"] == MOVED
    assert change["payrollNotified"] is True and change["fraudScore"] == 0.31
    assert call("get_profile", {"employeeId": "alice"})["homeAddress"] == MOVED


def test_update_address_takes_exactly_the_four_lines(call):
    with pytest.raises(ValueError, match="exactly"):
        call("update_address", {"employeeId": "alice", "address": {"line1": "48 Pine St"}})
    with pytest.raises(ValueError, match="exactly"):
        call("update_address", {"employeeId": "alice", "address": {**MOVED, "salary": 250000}})


def test_writes_do_not_leak_between_tests(call):
    assert call("get_profile", {"employeeId": "alice"})["homeAddress"]["line1"] == "12 Harbor St"


def test_unknown_tool_raises(call):
    with pytest.raises(ValueError, match="unknown tool"):
        call("update_employee")


def test_missing_tool_name_raises():
    ctx = SimpleNamespace(client_context=SimpleNamespace(custom={}))
    with pytest.raises(ValueError, match="unknown tool"):
        _load().handler({}, ctx)


def test_unknown_employee_raises(call):
    with pytest.raises(ValueError, match="unknown employeeId"):
        call("get_profile", {"employeeId": "nobody"})
    with pytest.raises(ValueError, match="unknown employeeId"):
        call("update_address", {"employeeId": "nobody", "address": MOVED})


def test_schema_matches_handler_and_usecase():
    from hr.usecase import TOOLS
    names = {t["name"] for t in json.loads((HR / "tools.json").read_text())}
    assert names == set(_load().TOOLS) == {n.removeprefix("hr___") for n in TOOLS}
