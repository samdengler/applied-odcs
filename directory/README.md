# Directory

Anyone looks up anyone, and a field labelled `restricted` never leaves.  That is
the whole use case.  It is the smallest thing that shows the path from the
registry to the response interceptor, and it needs no metadata about the caller
or the record.  `docs/response-filter.md` has the diagrams, the live results, and
what the filter does not cover.

## The tool and its fields

`look_up_employee` returns the whole stored record: the tool filters nothing, on
purpose.  It logs the names of the fields it returned, never their values.  The
SSNs in `tool/data/` are fake, from the `000` area that is never assigned.

| Field | Level | Leaves the Gateway |
| --- | --- | --- |
| `employeeId`, `name`, `workEmail` | `public` | yes |
| `personalPhone` | `internal` | yes |
| `ssn` | `restricted` | no |
| `passportNumber` | not in the contract | no |

## The two policies

`policies.cedar` has one `permit` that passes everything and one `forbid` that
stops a field unless the contract labelled it below `restricted`.  A forbid
overrides every permit, so later permits cannot open a restricted field.

`guardrails/` states the same boundary as two sentences for the prover to check
against the policies: a restricted field is never allowed, and neither is a field
the contract does not declare.  `make check` runs the proofs, and `make publish`
stops if they fail.

## Running it

```sh
make check              # with the proofs, which need cargo and cvc5
make prove              # the proofs alone
make demo-directory     # against the deployed Gateway
make call USER=bob TOOL=directory___look_up_employee ARGS='{"employeeId":"alice"}'
uv run cedar-odcs dry-run directory --caller directory/tests/identities/bob.json --tool directory___look_up_employee --arg employeeId=alice --response directory/tests/responses/alice.json
```

The tests read the expected fields from the labels in the policy file, so a
relabel needs no test change.
