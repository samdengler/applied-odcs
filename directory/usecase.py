"""The directory: anyone looks up anyone, and a field labelled restricted
never leaves."""

from pathlib import Path

from cedar_odcs.engine.usecase import UseCase

ROOT = Path(__file__).parent

# The binding the registry publishes: the one tool's verb, the argument
# naming the record, and the model its result is.
TOOLS = {
    "directory___look_up_employee": {"action": 'Action::"LookUpEmployee"', "id": "employeeId",
                                     "returns": "object", "model": "Employee"},
}

# The field that is a record's id.  No field becomes an attribute of the
# entity, because the policies read nothing from the record.
MODELS = {"Employee": {"id": "employeeId", "attributes": {}}}

USE_CASE = UseCase(
    name="directory",
    root=ROOT,
    resource_type="Employee",
    attributes=MODELS["Employee"]["attributes"],
    id_field=MODELS["Employee"]["id"],
    read_action='Action::"ReadEmployee"',
    read_field_action='Action::"ReadEmployeeField"',
    field_actions={},
    tools=TOOLS,
)

# The contract build's input, written by hand at contract/employee.odcs.yaml.
CONTRACT = "Employee"
