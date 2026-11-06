"""The tool Lambda against its data and the Gateway schema: it filters
nothing, so what the Gateway returns is the interceptor's doing."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

DIRECTORY = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("directory_tool_handler", DIRECTORY / "tool" / "handler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ctx(name):
    return SimpleNamespace(client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": name}))


def test_a_lookup_returns_the_whole_record_and_logs_only_field_names(capsys):
    record = _load().handler({"employeeId": "alice"}, _ctx("directory___look_up_employee"))
    assert record["ssn"] == "000-12-3456" and record["passportNumber"] == "X0000001"
    logged = capsys.readouterr().out
    assert logged == "returned " + json.dumps(sorted(record)) + "\n"
    assert "000-12-3456" not in logged


def test_an_unknown_employee_raises_with_what_the_call_named():
    with pytest.raises(ValueError, match="000-12-3456"):
        _load().handler({"employeeId": "000-12-3456"}, _ctx("directory___look_up_employee"))


def test_an_unknown_tool_raises():
    with pytest.raises(ValueError, match="unknown tool"):
        _load().handler({}, _ctx("directory___delete_employee"))


def test_a_missing_tool_name_raises():
    with pytest.raises(ValueError, match="unknown tool"):
        _load().handler({}, SimpleNamespace(client_context=SimpleNamespace(custom={})))


def test_schema_matches_handler_and_usecase():
    from directory.usecase import TOOLS
    names = {t["name"] for t in json.loads((DIRECTORY / "tools.json").read_text())}
    assert names == set(_load().TOOLS) == {n.removeprefix("directory___") for n in TOOLS}
