"""The HR API stand-in Lambda behind target hr.

It does no authorization, on purpose: every tool returns every field of
every record it is asked for.  Access control belongs to the Gateway
interceptors in front of it, and this tool is what they are tested
against.  Each tool is one business intent.  update_address does more
than set a field: it records the change, tells payroll, and screens the
change for payroll diversion, and it returns that change, not the
employee.  Writes change memory only and do not survive a cold start.
"""
import datetime
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "employees.json")
with open(_PATH) as _f:
    EMPLOYEES = {e["employeeId"]: e for e in json.load(_f)}
CHANGES = []

_KEY = "bedrockAgentCoreToolName"
ADDRESS = ("line1", "city", "postalCode", "country")


def _employee(event):
    employee_id = (event or {}).get("employeeId")
    if employee_id not in EMPLOYEES:
        raise ValueError(f"unknown employeeId: {employee_id!r}")
    return EMPLOYEES[employee_id]


def get_profile(event):
    return _employee(event)


def _fraud_score(old, new):
    """The payroll-diversion screen, stood in for: a move to another
    postal code scores higher than a correction within one."""
    return 0.31 if old.get("postalCode") != new["postalCode"] else 0.04


def update_address(event):
    employee = _employee(event)
    address = event.get("address")
    if not isinstance(address, dict) or set(address) != set(ADDRESS):
        raise ValueError(f"address must give exactly {', '.join(ADDRESS)}")
    change = {
        "changeId": f"chg-{len(CHANGES) + 1:04d}",
        "employeeId": employee["employeeId"],
        "homeAddress": {key: address[key] for key in ADDRESS},
        "effectiveDate": datetime.date.today().isoformat(),
        "payrollNotified": True,
        "fraudScore": _fraud_score(employee["homeAddress"], address),
    }
    employee["homeAddress"] = dict(change["homeAddress"])
    CHANGES.append(change)
    return change


TOOLS = {f.__name__: f for f in (get_profile, update_address)}


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
