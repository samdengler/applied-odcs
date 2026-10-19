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

## Runtime variant

The `runtime-mcp` branch ports the tool to an MCP server on AgentCore
Runtime: `orders/server/server.py` (FastMCP) in a container, behind the
same Gateway, interceptors, and Cognito users, with an MCP server target
that calls the Runtime with an OAuth token from a Cognito M2M client.  It
deploys as a second stack, `AppliedOdcsRuntime`, with every name prefixed
`applied-odcs-runtime`.  Every AWS target takes `VARIANT=runtime`, and on
this branch `make deploy` refuses to run without it.

```sh
make server-smoke                              # the MCP server on the Mac, initialize and tools/list over HTTP
make synth VARIANT=runtime                     # AppliedOdcsRuntime, checked by scripts/check_synth.py
make compare-baseline                          # the default variant still synthesizes the demo-lambda-target tag's template
make deploy VARIANT=runtime && make users VARIANT=runtime
make tools VARIANT=runtime USER=carol          # tools/list through the Gateway
make call VARIANT=runtime USER=carol TOOL=list_orders
make record VARIANT=runtime USER=... TOOL=...  # into orders/tests/events/runtime/
make compare-live                              # each runtime recording against its Lambda function target recording
make latency VARIANT=runtime USER=carol        # ten timed tools/call round trips
make sessions VARIANT=runtime MINUTES=5        # the server's part of each call, from the Runtime log streams
make demo VARIANT=runtime
```

The runtime stack's outputs, demo password, and M2M client secret go to
`.env.applied-odcs-runtime`, which git ignores.  The plan is
`docs/plan-runtime.md`; what was built and observed is
`docs/status-runtime.md`.

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
