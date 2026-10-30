# HR

An employee sees their own profile and changes their own address, and
no one else's.  That is the whole use case.  It is cut down from
cedar-odcs `usecases/hr`, which adds managers, HR partners, acting for
an employee, an HR assistant, and a directory list; that version is on
branch `hr-full`.  The contract is written by hand, at
`contract/employee.odcs.yaml`, so there is no pull step.

## Two tools, two intents, two models

Each tool is one business intent, and each returns its own model, a
schema object of the contract.  `usecase.py` is the binding the
registry would publish: each tool's verb, the argument naming the
employee, the model its result is, and, for a write, the contract
field its payload is.

| Tool | Intent | Verb | Returns |
| --- | --- | --- | --- |
| `get_profile` | See my profile | `ViewProfile` | `Employee`: name, work email, home address, personal phone, salary, bank account |
| `update_address` | I moved | `UpdateAddress` | `AddressChange`: change id, the new address, effective date, whether payroll was told, fraud score |

`update_address` does more than set a field.  The HR API records the
change, tells payroll so tax withholding follows the move, and screens
it for payroll diversion.  It returns that change, not the employee.

## The record is the employee

Both tools name the employee by `employeeId`, the username in their
token, and the tool table copies it into `context.input` as a `User`.
So every call names one employee, and the request leg compares that
employee with the caller before the HR API is called.  The response leg
checks the record the API returned the same way, then cuts it to the
fields the employee may read, as the tool's model.

`update_address` writes the `Employee` field `homeAddress` (its
`writes`).  Its `address` argument is that field's new value, so the
interceptor asks about each line at its contract path:
`address.line1` is decided as `homeAddress.line1`.  A line the contract
does not declare, such as a salary sent inside the address, is refused
as `homeAddress.salary`.

## The seven policies

`policies.cedar` has one permit for each question the interceptor asks.
Anything no permit allows is refused.

| Leg | Verb | Asked | Permit |
| --- | --- | --- | --- |
| Request | `ViewProfile` | once per `get_profile` call | `employee-views-own-profile`: the call names the caller |
| Request | `UpdateAddress` | once per `update_address` call | `employee-updates-own-address`: the call names the caller |
| Request | `UpdateAddressField` | once per address line sent | `employee-sets-own-fields`: on their own record, a field whose writer is `owner` |
| Response | `ReadEmployee` | once per profile returned | `employee-reads-own-profile`: the profile is the caller's |
| Response | `ReadEmployeeField` | once per profile field | `employee-reads-own-profile-fields`: level `public` or `confidential` |
| Response | `ReadAddressChange` | once per change returned | `employee-reads-own-address-change`: the change is the caller's |
| Response | `ReadAddressChangeField` | once per change field | `employee-reads-own-address-change-fields`: level `public` or `confidential` |

## Who sees and sets each field

No policy names a field.  The contract gives every field a level and a
writer, and the policies grant levels and writers.

| Model | Field | Level | Writer | Alice, her own | Alice, Bob's |
| --- | --- | --- | --- | --- | --- |
| `Employee` | `employeeId`, `name`, `workEmail` | public | system | sees | none |
| `Employee` | `homeAddress.*`, `personalPhone` | confidential | owner | sees; `update_address` sets the address | none |
| `Employee` | `salary` | confidential | system | sees | none |
| `Employee` | `bankAccount` | restricted | system | none | none |
| `AddressChange` | `changeId`, `employeeId`, `effectiveDate`, `payrollNotified` | public | system | sees | none |
| `AddressChange` | `homeAddress.*` | confidential | system | sees | none |
| `AddressChange` | `fraudScore` | restricted | system | none | none |

## The binding check

cedar-odcs's own tools gate requires every tool to return exactly the
contract's `Employee` fields, so `make check` runs build, validate, and
the test cases on their own, then `scripts/publish.py`, whose binding
check (`interceptor/policy_file.py`) takes the gate's place: each
model is a schema object of the contract, each tool's `outputSchema`
names exactly its model's fields, and `update_address`'s `address`
names exactly the lines of `homeAddress`.

## Running it

```sh
make check
uv run cedar-odcs dry-run hr --caller hr/tests/identities/bob.json --tool hr___get_profile --arg employeeId=alice
```

The first is the gate.  The second is Bob viewing Alice's profile,
refused before the tool would run.
