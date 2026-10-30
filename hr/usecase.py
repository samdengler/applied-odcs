"""HR: an employee sees their own profile and changes their own address,
and no one else's."""

from pathlib import Path

from cedar_odcs.engine.usecase import UseCase

ROOT = Path(__file__).parent

# Each tool is one business intent, bound to the contract: its verb, the
# argument naming the employee, and the model its result is. employeeId,
# copied into context.input as a User, is the employee the call is for,
# so the request leg decides it before the HR API is called.
# update_address's payload is the new value of the Employee field
# homeAddress (writes), so its lines are decided at their contract paths.
EMPLOYEE = {"employeeId": "User"}

TOOLS = {
    "hr___get_profile":    {"action": 'Action::"ViewProfile"', "id": "employeeId", "input": EMPLOYEE,
                            "returns": "object", "model": "Employee"},
    "hr___update_address": {"action": 'Action::"UpdateAddress"', "id": "employeeId", "input": EMPLOYEE,
                            "payload": "address", "writes": "homeAddress",
                            "returns": "object", "model": "AddressChange"},
}

# The contract's schema objects the tools return: the field that is a
# record's id, and the fields that become attributes of its entity.
MODELS = {
    "Employee":      {"id": "employeeId", "attributes": {"employeeId": "User"}},
    "AddressChange": {"id": "changeId",   "attributes": {"employeeId": "User"}},
}

# What a call names on the request leg: Employee::"alice". The response
# legs use MODELS, one cedar-odcs use case per model (interceptor/).
USE_CASE = UseCase(
    name="hr",
    root=ROOT,
    resource_type="Employee",
    attributes=MODELS["Employee"]["attributes"],
    id_field=MODELS["Employee"]["id"],
    read_action='Action::"ReadEmployee"',
    read_field_action='Action::"ReadEmployeeField"',
    field_actions={'Action::"UpdateAddress"': 'Action::"UpdateAddressField"'},
    tools=TOOLS,
)

# The contract build's input. The HR system has no catalog this project
# reads, so there is no PULL: contract/employee.odcs.yaml is written by hand.
CONTRACT = "Employee"
