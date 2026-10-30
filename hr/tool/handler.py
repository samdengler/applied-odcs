"""The HR API stand-in Lambda behind target hr.

It does no authorization, on purpose: every tool returns every field of every
record it is asked for.  Access control belongs to the Gateway interceptors in
front of it, and this tool is what they are tested against.  Writes change
memory only and do not survive a cold start.
"""
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "employees.json")
with open(_PATH) as _f:
    EMPLOYEES = {e["employeeId"]: e for e in json.load(_f)}

_KEY = "bedrockAgentCoreToolName"


def _employee(event):
    employee_id = (event or {}).get("employeeId")
    if employee_id not in EMPLOYEES:
        raise ValueError(f"unknown employeeId: {employee_id!r}")
    return EMPLOYEES[employee_id]


def _merge(record, changes):
    for key, value in changes.items():
        if isinstance(value, dict) and isinstance(record.get(key), dict):
            _merge(record[key], value)
        else:
            record[key] = value


def get_employee(event):
    return _employee(event)


def update_employee(event):
    employee = _employee(event)
    _merge(employee, event.get("changes") or {})
    return employee


def list_employees(event):
    return list(EMPLOYEES.values())


TOOLS = {f.__name__: f for f in (get_employee, update_employee, list_employees)}


def handler(event, context):
    custom = getattr(getattr(context, "client_context", None), "custom", None)
    print("client_context " + json.dumps(custom, default=str))
    raw = (custom or {}).get(_KEY)
    if not raw:
        raise ValueError(f"unknown tool: {_KEY} missing, received {custom!r}")
    name = raw.split("___", 1)[1] if "___" in raw else raw
    if name not in TOOLS:
        raise ValueError(f"unknown tool: {raw!r}")
    return TOOLS[name](event)
