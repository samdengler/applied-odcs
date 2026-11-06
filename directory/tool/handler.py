"""The directory API stand-in Lambda behind target directory.

It does no authorization and filters nothing, on purpose: every lookup
returns the whole stored record, including ssn, which the contract
labels restricted, and passportNumber, which the contract does not
declare.  The Gateway interceptors in front of it are what this tool is
tested against.  It logs the names of the fields it returned, never
their values, so a demo can compare them with what the caller received.
"""
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "employees.json")
with open(_PATH) as _f:
    EMPLOYEES = {e["employeeId"]: e for e in json.load(_f)}

_KEY = "bedrockAgentCoreToolName"


def look_up_employee(event):
    employee_id = (event or {}).get("employeeId")
    if employee_id not in EMPLOYEES:
        raise ValueError(f"unknown employeeId: {employee_id!r}")
    return EMPLOYEES[employee_id]


TOOLS = {f.__name__: f for f in (look_up_employee,)}


def handler(event, context):
    custom = getattr(getattr(context, "client_context", None), "custom", None)
    raw = (custom or {}).get(_KEY)
    if not raw:
        raise ValueError(f"unknown tool: {_KEY} missing, received {custom!r}")
    name = raw.split("___", 1)[1] if "___" in raw else raw
    if name not in TOOLS:
        raise ValueError(f"unknown tool: {raw!r}")
    record = TOOLS[name](event)
    print("returned " + json.dumps(sorted(record)))
    return record
