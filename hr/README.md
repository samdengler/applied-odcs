# HR

An employee reads and changes their own record, and no one else's.
That is the whole use case.  It is cut down from cedar-odcs
`usecases/hr`, which adds managers, HR partners, acting for an
employee, an HR assistant, and a directory list; that version is on
branch `hr-full`.  The contract is written by hand, at
`contract/employee.odcs.yaml`, so `check` has no pull step.

## The record is the employee

The record's id, `employeeId`, is the employee's own user id, the
username in their token.  Both tools name the record by that argument,
and the tool table in `usecase.py` copies it into `context.input` as a
`User`.  So every call names one employee, and the request leg compares
that employee with the caller before the HR API is called.  The
response leg checks the record the API returned the same way, then cuts
it to the fields the employee may read.

## The five policies

`policies.cedar` has one permit for each question the interceptor asks.
Anything no permit allows is refused.

| Leg | Verb | Asked | Permit |
| --- | --- | --- | --- |
| Request | `LookupEmployee` | once per `get_employee` call | `employee-looks-up-own-record`: the call names the caller |
| Request | `UpdateEmployee` | once per `update_employee` call | `employee-updates-own-record`: the call names the caller |
| Request | `UpdateEmployeeField` | once per field the call sends | `employee-sets-own-fields`: on their own record, a field whose writer is `owner` |
| Response | `ReadEmployee` | once per record returned | `employee-reads-own-record`: the record is the caller's |
| Response | `ReadEmployeeField` | once per field returned | `employee-reads-own-fields`: on their own record, a field whose level is `public` or `confidential` |

## Who reads and writes each field

No policy names a field.  The contract gives every field a level and a
writer, and the policies grant levels and writers.

| Field | Level | Writer | Alice, her own record | Alice, Bob's record |
| --- | --- | --- | --- | --- |
| `employeeId`, `name`, `workEmail` | public | system | reads | none |
| `homeAddress.*`, `personalPhone` | confidential | owner | reads, writes | none |
| `salary` | confidential | system | reads | none |
| `bankAccount` | restricted | system | none | none |

A call that changes the address and the salary together is refused
whole and names the salary.  An address sent as one string names no
leaf of the contract and is refused.  A field the contract does not
declare is never set and never shown.

## Running it

```sh
uv run cedar-odcs check hr --skip pull --skip prove
uv run cedar-odcs dry-run hr --caller hr/tests/identities/alice.json --tool hr___update_employee --arg employeeId=alice --arg 'changes={"homeAddress": {"line1": "48 Pine St"}, "salary": 250000}'
uv run cedar-odcs dry-run hr --caller hr/tests/identities/bob.json --tool hr___get_employee --arg employeeId=alice
```

The first builds, validates, and runs the test cases.  The second is
Alice changing her address and her salary in one call, refused for the
salary.  The third is Bob looking up Alice's record, refused before the
tool would run.
