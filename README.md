# applied-odcs

One governed MCP tool behind an Amazon Bedrock AgentCore Gateway, decided
by one interceptor Lambda that holds no use case.  `hr/` is an HR API
with two tools, each one business intent: `get_profile` returns the
`Employee` model, and `update_address` records a move (it changes the
address, tells payroll, and screens for payroll diversion) and returns
the `AddressChange` model.  The interceptor reads the `hr` target's
policy file from S3 and decides every call with cedar-odcs v0.2.6.  The
rule is one sentence: an employee sees their own profile and changes
their own address, and no one else's.  A call naming Bob is refused
before the tool runs, and each tool's result is cut as its own model:
the profile without `bankAccount`, the address change without
`fraudScore`.  This is use case 1 of "Writes the Gateway decides from
the request".

The example is kept to that one rule on purpose.  Branch `hr-full` has
the larger HR use case from cedar-odcs: managers, HR partners, acting
for an employee, the HR assistant, and the directory list, with tools
that edit the record (`update_employee`) rather than name an intent.

The stack is `AppliedOdcsShared`, with its own user pool, Gateway, and
env file.  The earlier orders demo, stack `AppliedOdcs`, is at tag
`demo-lambda-target`; nothing here deploys it.  The design and what was
observed are in `docs/shared-interceptor.md`.

## Commands

```sh
make check                      # build, validate, the corpus, the binding check, every test; no AWS
make deploy && make users       # the stack in us-east-1, the policy file, then Alice and Bob
make demo                       # use case 1 against the deployed Gateway
make call USER=alice TOOL=update_address ARGS='{"employeeId":"alice","address":{"line1":"48 Pine St","city":"Portland","postalCode":"04102","country":"US"}}'
make publish                    # a changed policy file to S3; the interceptors use it within 60 seconds
```

`make record USER=... TOOL=...` saves a live call as `hr/tests/live/live-*.json`,
which `make check` replays through the interceptor.

`make deploy` writes the stack outputs and the demo password to
`.env.applied-odcs-shared`, which git ignores; `.env.applied-odcs.example`
lists the names.

## Layout

- `hr/` is the governed tool, cut down from cedar-odcs `usecases/hr`:
  the binding (`usecase.py`: each tool's verb, model, and the field it
  writes), the contract with its two models
  (`contract/employee.odcs.yaml`), the seven policies, the Gateway tool
  schema (`tools.json`), the tool Lambda (`tool/`), and the tests.
- `interceptor/` is the shared interceptor: `handler.py` routes each
  tool call to its target's policy file, and each result to the
  cedar-odcs handlers for its tool's model; `policy_file.py` writes a
  policy file from a use case folder, checks the binding against the
  contract and `tools.json`, and reads one back.
- `scripts/publish.py` stands in for the registry: it writes
  `build/policies/hr.json` and puts it in the policy bucket.
- `lambda/bundle.sh` builds the interceptor code: `interceptor/` and
  cedar-odcs from its git tag with the Linux cedarpy wheel.
- `infra/` is the CDK app, plain `aws-cdk-lib`.
- `client/` gets a Cognito token, calls the Gateway, and records calls.
