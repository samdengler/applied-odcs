# applied-odcs

One governed MCP tool behind an Amazon Bedrock AgentCore Gateway, decided
by one interceptor Lambda that holds no use case.  `hr/` is an HR API
with two tools, `get_employee` and `update_employee`.  The interceptor
reads the `hr` target's policy file from S3 and decides every call with
cedar-odcs v0.2.6.  The rule is one sentence: an employee reads and
changes their own record, and no one else's.  Alice may change her own
address; a call naming Bob is refused before the tool runs; her own
salary is the contract's to protect.  This is use case 1 of "Writes the
Gateway decides from the request".

The example is kept to that one rule on purpose.  Branch `hr-full` has
the larger HR use case from cedar-odcs: managers, HR partners, acting
for an employee, the HR assistant, and the directory list.

The stack is `AppliedOdcsShared`, with its own user pool, Gateway, and
env file.  The earlier orders demo, stack `AppliedOdcs`, is at tag
`demo-lambda-target`; nothing here deploys it.  The design and what was
observed are in `docs/shared-interceptor.md`.

## Commands

```sh
make check                      # the tool schema gate, validate, the corpus, every test; no AWS
make deploy && make users       # the stack in us-east-1, the policy file, then Alice and Bob
make demo                       # use case 1 against the deployed Gateway
make call USER=alice TOOL=update_employee ARGS='{"employeeId":"alice","changes":{"homeAddress":{"line1":"48 Pine St"}}}'
make publish                    # a changed policy file to S3; the interceptors use it within 60 seconds
```

`make record USER=... TOOL=...` saves a live call as `hr/tests/live/live-*.json`,
which `make check` replays through the interceptor.

`make deploy` writes the stack outputs and the demo password to
`.env.applied-odcs-shared`, which git ignores; `.env.applied-odcs.example`
lists the names.

## Layout

- `hr/` is the governed tool, cut down from cedar-odcs `usecases/hr`:
  the descriptor (`usecase.py`), the contract
  (`contract/employee.odcs.yaml`), the five policies, the Gateway tool
  schema (`tools.json`), the tool Lambda (`tool/`), and the tests.
- `interceptor/` is the shared interceptor: `handler.py` routes each
  tool call to its target's policy file and hands it to cedar-odcs's
  handlers; `policy_file.py` writes a policy file from a use case folder
  and reads one back.
- `scripts/publish.py` stands in for the registry: it writes
  `build/policies/hr.json` and puts it in the policy bucket.
- `lambda/bundle.sh` builds the interceptor code: `interceptor/` and
  cedar-odcs from its git tag with the Linux cedarpy wheel.
- `infra/` is the CDK app, plain `aws-cdk-lib`.
- `client/` gets a Cognito token, calls the Gateway, and records calls.
