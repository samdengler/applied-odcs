# applied-odcs

One governed MCP tool behind an Amazon Bedrock AgentCore Gateway, decided
by one interceptor Lambda that holds no use case.  `hr/` is an HR API
whose `update_employee` tool changes an employee's record.  The
interceptor reads the `hr` target's policy file from S3 and decides
every call with cedar-odcs v0.2.6: Alice may change her own address,
and a call naming Bob is refused before the tool runs.  This is use
case 1 of "Writes the Gateway decides from the request".

The stack is `AppliedOdcsShared`, with its own user pool, Gateway, and
env file.  The earlier orders demo, stack `AppliedOdcs`, is at tag
`demo-lambda-target`; nothing here deploys it.  The design and what was
observed are in `docs/shared-interceptor.md`.

## Commands

```sh
make check                      # the tool schema gate, validate, the corpus, every test; no AWS
make deploy && make users       # the stack in us-east-1, the policy file, then Alice, Bob, Maya, and Hana
make demo                       # use case 1 against the deployed Gateway
make call USER=alice TOOL=update_employee ARGS='{"employeeId":"alice","changes":{"homeAddress":{"line1":"48 Pine St"}}}'
make publish                    # a changed policy file to S3; the interceptors use it within 60 seconds
```

`make prove` proves the twelve guardrails against the policies; it needs
cargo, cvc5, and a cedar-odcs checkout at `../cedar-odcs`.  `make record
USER=... TOOL=...` saves a live call as `hr/tests/live/live-*.json`,
which `make check` replays through the interceptor.

`make deploy` writes the stack outputs and the demo password to
`.env.applied-odcs-shared`, which git ignores; `.env.applied-odcs.example`
lists the names.

## Layout

- `hr/` is the governed tool, copied from cedar-odcs `usecases/hr`: the
  descriptor (`usecase.py`), the contract (`contract/employee.odcs.yaml`),
  the policies, the guardrails, the Gateway tool schema (`tools.json`),
  the tool Lambda (`tool/`), and the tests.
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
