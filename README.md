# applied-odcs

One governed MCP tool, deployed.  `orders/` is an orders API behind an
Amazon Bedrock AgentCore Gateway, and cedar-odcs's request and response
interceptors decide every call from an ODCS contract and Cedar policies.
Alice, Carol, and Dave are Cognito users; the same `list_orders` call
returns each of them only the rows and fields the contract allows.  The
folder passes `cedar-odcs check` locally with no AWS, and the Gateway
events recorded from live calls are saved as test fixtures.

## Commands

```sh
make check                      # build, tool schema gate, validate, the corpus, every handler test; no AWS
make deploy && make users       # the stack in us-east-1, then Alice, Carol, and Dave
make call USER=carol TOOL=list_orders
make call USER=alice TOOL=refund_order ARGS='{"orderId":"order-1001"}'
```

`make demo` runs the Monday sequence in `docs/demo.md` against the
deployed Gateway.  `make prove` proves the twelve guardrails against the
policies; it needs cargo, cvc5, and a cedar-odcs checkout at
`../cedar-odcs`.  `make record USER=... TOOL=...` saves a live call as
`orders/tests/events/live-*.json`, which `make check` replays.

`make deploy` writes the stack outputs and the demo password to
`.env.applied-odcs`, which git ignores; `.env.applied-odcs.example`
lists the names.

## Layout

- `orders/` is the governed tool, the folder a tool team copies: the
  descriptor (`usecase.py`), the contract (`contract/order.odcs.yaml`)
  and the role grants (`contract/grants.yaml`), the verb policies, the
  guardrails, the Gateway tool schema (`tools.json`), the tool Lambda
  (`tool/`), and the tests.
- `lambda/bundle.sh` builds the interceptor code: cedar-odcs from its
  git tag, the Linux cedarpy wheel, and `orders/` with the files the
  build generates.  Nothing generated is committed.
- `infra/` is the CDK app, plain `aws-cdk-lib`.
- `client/` gets a Cognito token, calls the Gateway, and records calls.

The plan is `docs/plan.md`; what was built and what was observed is
`docs/status.md`.
