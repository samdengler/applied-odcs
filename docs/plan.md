# applied-odcs implementation plan

October 17, 2026.  Source of truth: https://claude.ai/code/artifact/0a360a61-e0cd-4ce7-bf9c-6303958f8483 (this file is an export; edits there win).  Decisions: https://claude.ai/code/artifact/82fc53e1-0333-432b-a579-547faa9089c9

## Summary

By morning, `applied-odcs` is a private repo that deploys one governed MCP tool to Sam's AWS account: an orders tool behind an AgentCore Gateway, with cedar-odcs's request and response interceptors deciding every call from an ODCS contract and Cedar policies.  Alice, Carol, and Dave are Cognito users; a short client script gets a token, calls `list_orders`, and shows each caller getting the rows and fields the contract allows.  The same folder passes `cedar-odcs check` locally, and the recorded Gateway events from the live calls are saved as test fixtures so the demo also runs with no network.

This plan is written for a Claude Code session running in `~/src/github.com/samdengler/applied-odcs` on the Mac, where the AWS CLI, the CDK CLI, uv, and the account credentials are.  cedar-odcs is checked out beside it at `~/src/github.com/samdengler/cedar-odcs` and gets a small loader change and a tag before the sample pins it.  Decisions come from the questions doc; where this plan names a default, that doc's Answer line was blank.

The constraint that runs through everything: the POC uses plain `aws-cdk-lib`, and every stand-in maps onto a prop of the Delta construct it replaces, so the port to `@com-delta-cdk/aws-enterprise-cdk` is a class swap and no change to the Python.

## Decisions carried in

From the [questions doc](https://claude.ai/code/artifact/82fc53e1-0333-432b-a579-547faa9089c9).  Numbers are its question numbers.

| # | Decision |
| --- | --- |
| 1, 3, 4 | The sample is the orders use case from cedar-odcs, copied in: one entity type, four levels, roles customer, support, finance |
| 2 | Single principal with roles live on Monday.  Carol acting for Alice is shown from the command line with the recorded identity, since Cognito cannot mint an `act` claim without a pre-token trigger |
| 5, 6, 8 | Full stack is a Python client with a token, the Gateway in MCP mode, a Lambda tool target returning orders from JSON, the two interceptor Lambdas.  No agent runtime, no token exchange |
| 7 | Cognito user pool stands in for Ping.  Roles ride in the `cognito:groups` claim |
| 9, 10 | Personal account, us-east-1, default profile.  One stack for Monday |
| 11 | Contract lives in the sample repo next to the tool, one ODCS document per tool, `outputSchema` checked against it at build |
| 12 | Option (b): the build generates the Cedar schema, tag maps, and entities into the Lambda package; nothing generated is committed |
| 13 | Library ships the field-level read and write policies keyed on classification; the sample writes the verb policies and role grants.  New work in cedar-odcs, see Library changes |
| 14, 15 | Guardrails come along as files.  `check` runs build, validate, run-tests.  `prove` is a separate target that needs cargo and cvc5 |
| 16, 19 | cedar-odcs as a git dependency pinned to a tag; the command line ships with it |
| 17 | Python descriptor module for Monday, loaded from a path the sample sets |
| 18 | cedarpy inside the Lambda; Linux wheel installed at bundling time |
| 20 | Audience is the platform team that owns the constructs, kill switch, and registry |
| 21 | Live on Monday: the command line, the local handler tests, and the deployed Gateway if the overnight deploy succeeds |
| 22 | Repo is `applied-odcs`, private on github.com/samdengler |
| 23 | Work order as in this plan |

## Architecture

*Diagram (in the Claude Doc): client gets a token from Cognito; client calls the Gateway (MCP, JWT authorizer); the Gateway asks the request interceptor (verb round, payload round), which allows or returns 403; the Gateway calls the orders tool Lambda with its service role; the tool answers every field of every row; the response interceptor (row round, field round) keeps rows and strips fields; the caller sees the rest.  The ODCS contract feeds cedar-odcs build, whose schema, tag maps, and entities are bundled into both interceptor Lambdas.*

The client gets an access token from Cognito and calls the Gateway.  The request interceptor decides the verb and the payload from the token's claims; if it allows, the Gateway calls the tool Lambda with its own role, and the tool answers with every field.  The response interceptor keeps the rows the caller may read and strips the fields the caller may not see.  Both interceptors run the same bundle: the engine from cedar-odcs plus the Cedar files the build generated from the contract.  At port time the Gateway box becomes `DeltaAgentCoreGateway`, Cognito becomes Ping, and nothing else moves.

## Repository layout

The repo has one governed tool folder, `orders/`, and everything else exists to deploy, call, or check it.  `orders/` is the folder a tool team would copy; it has the same shape as a cedar-odcs use case plus the tool's own code and schema.

```text
applied-odcs/
  README.md                 what it is, the three commands, the demo
  CLAUDE.md                 instructions for the Claude Code session (see Work order)
  Makefile                  check, bundle, synth, deploy, users, token, demo
  pyproject.toml            depends on cedar-odcs by git tag; dev: pytest, boto3
  uv.lock
  .gitignore                orders/contract/generated/, orders/entities.json, build/, infra/cdk.out/
  orders/                   the governed tool: the folder a tool team copies
    usecase.py              descriptor: entity, attributes, verbs, tool table, claims mapping
    tools.json              Gateway tool schema: five tools, inputSchema and outputSchema
    contract/
      order.odcs.yaml       the ODCS v3.2.0 contract, committed, hand-written form
      generated/            build output, not committed
    policies.cedar          verb policies and role grants, hand-written
    guardrails/             the twelve orders guardrails, unchanged
    principals.cedarschema  who can be a principal
    actions.cedarschema     the verbs and their context
    facts.json              Alice, Bob, Carol, Dave, the roles, the role hierarchy
    entities.json           build output, not committed
    tool/
      handler.py            the tool Lambda: five tools over data/orders.json
      data/orders.json      the three orders the README case uses, plus a few more
    tests/
      test-cases/           request in, decision expected; copied from cedar-odcs
      identities/           claims per caller, in the Cognito claim shape
      lists/                the list response fixture
      responses/            per-record responses
      events/               Gateway events: the cedar-odcs set, plus the ones recorded live
      test_corpus.py        runs test-cases through the engine
      test_interceptor.py   runs events through the two handlers
      test_tool.py          the tool Lambda against its data
  lambda/
    bundle.sh               builds build/lambda: cedar_odcs, cedarpy Linux wheel, orders/ with generated outputs
  infra/                    CDK app, TypeScript, plain aws-cdk-lib
    bin/applied-odcs.ts
    lib/governed-tool-stack.ts
    package.json  cdk.json  tsconfig.json
  client/
    token.py                Cognito USER_PASSWORD_AUTH to an access token
    call.py                 MCP initialize, tools/list, tools/call against the Gateway URL
    record.py               saves a live request and response pair as a tests/events fixture
  docs/
    demo.md                 the Monday script with expected output
```

Two things are not here on purpose.  There is no `usecases/` directory: the sample is one tool, and the engine loads any directory that has a `usecase.py`.  There is no copy of the engine: `cedar_odcs` comes from the git dependency and is installed into the Lambda bundle by `lambda/bundle.sh`.

## Library changes in cedar-odcs

cedar-odcs needs one small change to work behind Cognito, one medium change for the standard-policy split, and a tag.  The engine already loads a use case from any directory: `gateway/handler.py` reads `CEDAR_ODCS_USE_CASE` as a path and the command line takes `DIR` arguments, so no loader work is needed.

### Claims mapping (required)

`engine/identities.py` hard-codes the subject in `sub`, roles in `roles`, and the actor in `act`.  A Cognito access token carries the username in `username`, groups in `cognito:groups`, and a UUID in `sub`, and the store in `facts.json` keys users by name.  The change:

1. Add `ClaimsMapping(subject="sub", roles="roles", actor="act")` as a frozen dataclass in `identities.py`, and give `project(claims, entities, mapping=ClaimsMapping())` the mapping.  `_roles` reads `mapping.roles`, the subject reads `mapping.subject`, the actor `mapping.actor`.  Inside an `act` object the same names apply.
2. Add `claims: ClaimsMapping = ClaimsMapping()` to `UseCase` in `engine/usecase.py`.  `Handlers` and `Engine` pass `use_case.claims` through.  The command line's identity files are claims dicts already, so they pick up the mapping with no change.
3. One test per mapping in `cedar_odcs/`: the default mapping on an existing identity, and the Cognito mapping on a claims dict shaped like a real access token (`username`, `cognito:groups`, `client_id`, `sub` as a UUID).  The `_actor_type` check compares `client_id` to `sub`; a Cognito user token has both and they differ, so the actor is a `User`.

The orders sample sets `claims=ClaimsMapping(subject="username", roles="cognito:groups")`.  At port time the Ping mapping is another two strings.

### Role grants rendered to policies (decision 13, do after the deploy works)

Today every use case writes its own field-level policies: P4, P5, P6, and P11 in the orders `policies.cedar` are the same four shapes with different role names and level lists.  The split:

1. New module `engine/grants.py`.  Input `grants.yaml` next to the contract:

   ```yaml
   reads:
     owner:   [public, confidential]     # the acted-for party or the principal
     support: [public, internal]
   writes:
     owner:   owner                       # writer tag a role may set
     support: support
   ```
2. `render_grants(grants, entity_name)` returns Cedar text: one `ReadField` permit per `reads` entry and one `UpdateField` permit per `writes` entry, each with the same `@id` scheme as the orders policies (`customer-fields-on-own-order`, `support-fields-on-any-order`, `customer-updates-own-order-fields`, `support-updates-support-fields`) so the test cases keep naming them.  The `owner` key renders the ownership form with `actingFor`; a role key renders the `principal in Role::"<role>"` direct-mode form.
3. `build` writes `contract/generated/grants.cedar` when `grants.yaml` exists.  `UseCase.policies` returns `policies.cedar` plus the generated file when present.  `validate` and `share` read the combined text.
4. The orders use case inside cedar-odcs keeps its hand-written policies so its corpus and proofs are untouched.  The sample removes the four field policies from its `policies.cedar` and carries `grants.yaml` instead.  Its corpus must still pass unchanged, which is the test that the generator is faithful.

If this slips past 03:00, the sample commits the full hand-written `policies.cedar` and the generator moves to the next-steps list.  The demo does not depend on it.

### Tool schema against the contract (decision 11, do after the deploy works)

`cedar-odcs check DIR` gains a gate when `DIR/tools.json` exists: for every tool whose `returns` is `object` or `list`, each property path in its `outputSchema` must be a leaf in the contract, and each contract leaf must appear in the `outputSchema`.  A difference fails `check` with the two lists.  Thirty lines in `cli/main.py` plus a helper in `engine/contract.py` that already knows the leaves (`_leaves`).

### Packaging and tag

`pyproject.toml` already declares the `cedar_odcs` package and the `cedar-odcs` script.  After the claims mapping lands: tag `v0.2.0`, push, and the sample depends on `cedar-odcs @ git+https://github.com/samdengler/cedar-odcs.git@v0.2.0`.  Later tags (`v0.2.1` for grants and the tool-schema gate) bump the pin.  Run `./check.sh` in cedar-odcs before each tag; it must stay green.

## The sample

`orders/` is `usecases/orders/` from cedar-odcs, copied at the `v0.2.0` commit, with four additions: the tool Lambda, the Gateway tool schema, identities in the Cognito claim shape, and a claims mapping on the descriptor.  Nothing about the contract, the policies, the guardrails, or the test cases changes, and the copied corpus must pass before anything else is built.

### What is copied unchanged

`usecase.py` (`TOOLS`, `USE_CASE`, `CONTRACT`), `contract/order.odcs.yaml`, `contract/unity/` (kept so `pull` still shows the catalog path), `policies.cedar`, `guardrails/`, `principals.cedarschema`, `actions.cedarschema`, `facts.json`, `tests/test-cases/`, `tests/lists/orders.json`, `tests/responses/`, `tests/events/`, `tests/test_corpus.py`, `tests/test_interceptor.py`, `tests/test_build.py`.  `build.py` goes; the Makefile calls `cedar-odcs pull` and `build` instead.

The contract has nine leaves on `Order`: `id`, `owner`, `status`, `total`, `estimatedDelivery` (public), `shippingAddress`, `cardLast4` (confidential), `internalNotes` (internal), `fraudScore` (restricted).  Writers: `shippingAddress` by owner, `internalNotes` by support, the rest system.  That is the whole demo: Alice sees public and confidential, Carol sees public and internal, nobody sees `fraudScore`.

### The descriptor

One line added to `USE_CASE`: `claims=ClaimsMapping(subject="username", roles="cognito:groups")`.  Tool names stay `orders___get_order`, `orders___update_order`, `orders___cancel_order`, `orders___refund_order`, `orders___list_orders`.  The Gateway names a tool `<targetName>___<toolName>`, so the Lambda target is named `orders` and the five tools in `tools.json` are `get_order`, `update_order`, `cancel_order`, `refund_order`, `list_orders`.

### The tool Lambda

`orders/tool/handler.py`, Python 3.12, no dependencies.  The Gateway invokes a Lambda target with the tool's arguments as the event and the tool name in `context.client_context.custom["bedrockAgentCoreToolName"]` (verify the exact key against the Gateway developer guide on the first live call; the recorded event will show it).  The handler strips the `orders___` prefix, dispatches on the name, and returns a JSON object or list, which the Gateway wraps as a `content` text item the response interceptor already parses.

Data is `orders/tool/data/orders.json`: the three orders from `tests/lists/orders.json` (order-1001 and order-3003 for Alice, order-2002 for Bob) plus two more so a list has something to drop for each caller.  Writes (`update_order`, `cancel_order`, `refund_order`) change the record in memory and return it; nothing persists across cold starts, which is fine for a demo and keeps the tool honest about returning every field.  The tool itself does no authorization, which is the point: the API answers whatever is asked.

### The tool schema

`orders/tools.json` is the `ToolSchema.fromLocalAsset` file: an array of five tool definitions, each with `name`, `description`, `inputSchema`, and `outputSchema`.  `get_order`, `cancel_order`, and `refund_order` take `orderId`; `update_order` takes `orderId` and `changes` (an object with the writable fields); `list_orders` takes nothing.  `outputSchema` for the four object tools is the `Order` object with the nine leaves; for `list_orders` an array of it.  This file is what the tool-schema gate compares to the contract once that gate exists.

### Identities and events

The claims mapping is a property of the descriptor, so every identity file in the sample is written in the mapped shape.  `alice.json` carries `username: alice`, no `cognito:groups`, a `client_id`, and a UUID `sub`; `carol.json` adds `cognito:groups: [support]`; `dave.json` `[finance]`.  `carol-for-alice.json` is hand-written in the same shape, `username: alice` with `act: {username: carol, cognito:groups: [support]}`; Cognito cannot mint it, but `dry-run` reads the file directly, so the on-behalf-of case still runs from the command line.  The `tests/events/` fixtures copied from cedar-odcs carry Ping-shaped tokens and are regenerated with Cognito-shaped ones by a small script so `test_interceptor.py` passes under the new mapping.  Live calls are recorded with `client/record.py` into `tests/events/live-*.json`, which `test_interceptor.py` picks up by glob.

## Identities

A Cognito user pool stands in for Ping.  The Gateway validates the access token; the interceptors read its claims through the mapping; the store in `facts.json` supplies the role hierarchy (support and finance are children of employee).

| Person | Cognito username | Groups | In the store | What they see on `list_orders` |
| --- | --- | --- | --- | --- |
| Alice | `alice` | none | User, no roles | Her own orders, public and confidential fields |
| Bob | no user | none | User, no roles | Only appears as an owner; his order is the one Alice's list drops |
| Carol | `carol` | `support` | User in Role support | Every order, public and internal fields |
| Dave | `dave` | `finance` | User in Role finance | Every row, public fields only; refund is his verb |

User pool: self sign-up off, no MFA, email as a required attribute so the console looks normal.  One app client with no secret and `USER_PASSWORD_AUTH` enabled; access token validity one hour.  Three groups: `support`, `finance`, `employee`.  Carol is in `support` and `employee`, Dave in `finance` and `employee`, so the token's `cognito:groups` carries the same roles the store derives.  The union in `identities.project` means either source alone would do; both are set so the token is the Ping shape and the store is the fallback.

Users and group membership are created by `make users` after the first deploy (`scripts/users.py` with boto3: `admin_create_user`, `admin_set_user_password --permanent`, `admin_add_user_to_group`).  Passwords come from `APPLIED_ODCS_PASSWORD` in the environment, one value for all three, never written to the repo.  This is a script and not a custom resource because it has to run once, and because a password in a CloudFormation template is the wrong demo.

`client/token.py` runs `initiate_auth` with `USER_PASSWORD_AUTH` for a named user and prints the access token.  The access token, not the ID token, is what the Gateway expects: it carries `client_id`, which the Cognito authorizer matches against `allowedClients`, plus `username` and `cognito:groups`.  Decoded, it is the identity file shape the sample's `tests/identities/` already uses.

What Cognito cannot do here is mint an `act` claim, so Carol acting for Alice is shown from the command line with `dry-run` and the hand-written identity file.  At port time a PingFederate token exchange produces the real thing and the mapping names its claim.

## CDK app

One TypeScript app, one stack, plain `aws-cdk-lib` with its stable `aws-bedrockagentcore` module, where Gateway, targets, and interceptors now live (the alpha package keeps only the Policy engine).  Pin the newest 2.x at install time and confirm `agentcore.LambdaInterceptor` and `agentcore.GatewayAuthorizer.usingCognito` exist under `node_modules/aws-cdk-lib/aws-bedrockagentcore/lib/`.  Region us-east-1, default profile, default bootstrap.

### Resources

| Construct id | Class | Key props | Delta construct it maps to |
| --- | --- | --- | --- |
| `Users` | `cognito.UserPool` | `selfSignUpEnabled: false`, `signInAliases: { username: true }`, `removalPolicy: DESTROY` | none; Ping replaces it |
| `Client` | `cognito.UserPoolClient` | `generateSecret: false`, `authFlows: { userPassword: true }`, `accessTokenValidity: 1 hour` | none; `PingConfiguration.allowedClients` |
| `SupportGroup`, `FinanceGroup`, `EmployeeGroup` | `cognito.CfnUserPoolGroup` | `groupName` | roles in the Ping token |
| `OrdersTool` | `lambda.Function` | Python 3.12, `code: fromAsset('../orders/tool')`, handler `handler.handler`, 256 MB, 10 s | the Lambda behind `DeltaLambdaGatewayTarget` |
| `Interceptors` (asset) | `lambda.Code.fromAsset('../build/lambda')` | built by `lambda/bundle.sh`; shared by both functions | the interceptor code either way |
| `RequestInterceptor` | `lambda.Function` | Python 3.12, handler `cedar_odcs.gateway.handler.request`, env `CEDAR_ODCS_USE_CASE=/var/task/orders`, 512 MB, 10 s | `requestInterceptor.interceptorFunction` (the construct adds the kill switch layer) |
| `ResponseInterceptor` | `lambda.Function` | same code, handler `cedar_odcs.gateway.handler.response`, same env | `responseInterceptor.interceptorFunction` |
| `Gateway` | `agentcore.Gateway` | `gatewayName: 'applied-odcs'`, `protocolConfiguration: new McpProtocolConfiguration({ instructions, supportedVersions })`, `authorizerConfiguration: GatewayAuthorizer.usingCognito({ userPool, allowedClients: [client] })`, `exceptionLevel: DEBUG`, `interceptorConfigurations: [LambdaInterceptor.forRequest(req, { passRequestHeaders: true }), LambdaInterceptor.forResponse(resp, { passRequestHeaders: true })]` | `DeltaAgentCoreGateway` |
| `OrdersTarget` | `gateway.addLambdaTarget('Orders', …)` | `gatewayTargetName: 'orders'`, `lambdaFunction: ordersTool`, `toolSchema: ToolSchema.fromLocalAsset('../orders/tools.json')` | `DeltaLambdaGatewayTarget` |
| Outputs | `CfnOutput` | `GatewayUrl`, `UserPoolId`, `ClientId`, `Region` | SSM parameters in the Delta construct |

Both interceptors need `passRequestHeaders: true`: the request handler reads the bearer token to decide the verb, and the response handler reads it again to decide rows and fields.  If `forResponse` turns out not to accept the option in the installed version, pass the same `InterceptorOptions` through the L1 (`gateway.node.defaultChild as CfnGateway`) and note it under Risks.

The Gateway L2 grants `lambda:InvokeFunction` to its role for the target and both interceptors.  No other IAM is needed.  No VPC, no KMS, no custom domain.

### Bundling the interceptors

`lambda/bundle.sh` builds `build/lambda` without Docker:

```sh
rm -rf build/lambda && mkdir -p build/lambda
uv pip install --target build/lambda \
  --python-platform aarch64-manylinux2014 --python-version 3.12 --only-binary=:all: \
  "cedar-odcs @ git+https://github.com/samdengler/cedar-odcs.git@v0.2.0"
uv run cedar-odcs build orders                      # contract to generated/ and entities.json
rsync -a --exclude tests --exclude tool --exclude contract/unity orders/ build/lambda/orders/
```

cedarpy 4.12.2 publishes manylinux wheels for aarch64 and x86\_64 on CPython 3.10 to 3.14, so `--only-binary` holds and the functions run on `Architecture.ARM_64`.  The bundle carries the generated Cedar files and `entities.json` and the repo never commits them, which is decision 12 (b).  `cedar_odcs` resolves the use case at import time from `CEDAR_ODCS_USE_CASE`, so the first invocation after a cold start pays the Cedar schema parse once.

### Deploy

`make deploy` runs `make check`, `lambda/bundle.sh`, `npm ci` and `cdk deploy --require-approval never` in `infra/`, then writes the three outputs to `.env.applied-odcs` for the client scripts.  First deploy needs `cdk bootstrap` once if the account has none; the plan's work order checks with `aws cloudformation describe-stacks --stack-name CDKToolkit` first.

## Build and check

The Makefile is the interface; every target is one line a tool team could read.  `check` is the gate a pipeline would run on every change to the contract or the policies.

| Target | Runs | Verifies |
| --- | --- | --- |
| `make sync` | `uv sync`, `npm ci` in `infra/` | dependencies resolve, including cedar-odcs at its tag |
| `make build` | `uv run cedar-odcs build orders` | the contract has four known levels, every leaf a level, every writer a role; writes `contract/generated/` and `entities.json` |
| `make check` | `uv run cedar-odcs check orders`, then `uv run pytest -q` | build, validate (cedarpy), run-tests (the corpus), the handler tests on every event fixture, the tool Lambda tests |
| `make prove` | `uv run cedar-odcs prove orders` from the cedar-odcs checkout, with `CEDAR_ODCS_ANALYSIS` pointing at it | the twelve guardrails are no-ops against the policies; needs cargo and cvc5, not part of `check` |
| `make bundle` | `lambda/bundle.sh` | `build/lambda/` imports `cedar_odcs` and `cedarpy` under a Linux Python; a smoke test runs the response handler on one fixture inside the bundle with `PYTHONPATH=build/lambda` (on the Mac this only checks the pure-Python import path; the wheel is exercised on first invoke) |
| `make synth` | `cdk synth` in `infra/` | the template has one Gateway, one target, two interceptors with `passRequestHeaders: true` |
| `make deploy` | `check`, `bundle`, `cdk deploy --require-approval never`, writes `.env.applied-odcs` | the stack is up and outputs are captured |
| `make users` | `scripts/users.py` | Alice, Carol, Dave exist with permanent passwords and group membership |
| `make token USER=carol` | `client/token.py` | prints an access token whose decoded claims have `username`, `cognito:groups`, `client_id` |
| `make call USER=carol TOOL=list_orders` | `client/call.py` | one MCP `initialize`, `tools/call`, prints the result |
| `make record USER=carol TOOL=list_orders` | `client/record.py` | saves the Gateway request and response as `tests/events/live-<user>-<tool>.json` by fetching the two interceptors' last invocation from CloudWatch Logs, where the handlers log the event at DEBUG when `CEDAR_ODCS_RECORD=1` |
| `make demo` | `docs/demo.md` as a script: the Monday sequence | the whole story runs end to end |

`make check` passes with no AWS credentials and no network beyond the git dependency.  That is the property the platform team cares about: the governance of a tool is checked where its code is, before anything deploys.

The `CEDAR_ODCS_RECORD` switch is a small addition to `gateway/handlers.py` in cedar-odcs: when set, each handler logs the full inbound event as one JSON line before deciding.  It is off by default, since the event carries a bearer token, and the recording script redacts the token signature before writing the fixture.

## Work order

For the Claude Code session, started in `~/src/github.com/samdengler/applied-odcs` with `~/src/github.com/samdengler/cedar-odcs` beside it.  Authority for the night: commit and push on `main` in both repos, create the private GitHub repo `samdengler/applied-odcs` with `gh repo create --private`, tag cedar-odcs, deploy to and tear down in the personal account.  Do not touch the Delta constructs or any Delta account.  Each step ends with its verification and a commit; a step that fails its verification is not committed over, it is fixed or its fallback taken and the fallback written into `docs/status.md`.  Ask nothing; take the plan's default and record it.

The demo path (steps 1 to 9) comes first.  Steps 10 and 11 are the decision-13 and decision-11 work and run only once step 9 is green.  Step 12 closes.

1. **cedar-odcs: claims mapping.**  Implement `ClaimsMapping` as in Library changes, with tests.  `./check.sh` green.  Commit `Claims mapping on the descriptor: subject, roles, actor by name`.  Tag `v0.2.0`, push tags.
   - Verify: `uv run pytest -q` in cedar-odcs passes; `uv run cedar-odcs check usecases/orders` passes.
2. **applied-odcs: skeleton.**  `pyproject.toml` (depends on `cedar-odcs @ git+...@v0.2.0`, dev `pytest`, `boto3`), `.gitignore`, `Makefile` with the targets above as stubs, `README.md` with the one-paragraph description, `CLAUDE.md` pointing at this plan and the Makefile.  `uv sync` resolves.  Create the private repo, first commit, push.
   - Verify: `uv run cedar-odcs --help` works from the sample repo.
3. **applied-odcs: copy orders.**  Copy `usecases/orders/` as listed in The sample, drop `build.py`, add the claims mapping line, rewrite `tests/identities/` to the Cognito shape, regenerate the token in `tests/events/*.json` from the new identity files (a 30-line script under `scripts/`).  `make check` green.  Commit.
   - Verify: the corpus passes unchanged; `test_interceptor.py` passes on every event; `cedar-odcs dry-run orders --caller orders/tests/identities/carol-for-alice.json --tool orders___list_orders --response orders/tests/lists/orders.json` prints two rows with seven fields each.
4. **The tool Lambda and schema.**  `orders/tool/handler.py`, `orders/tool/data/orders.json`, `orders/tools.json`, `tests/test_tool.py`.  Commit.
   - Verify: `test_tool.py` calls each tool through the handler with a fake context carrying the tool name; `list_orders` returns five rows with all nine fields.
5. **Bundle.**  `lambda/bundle.sh` and `make bundle`.  Commit.
   - Verify: `PYTHONPATH=build/lambda CEDAR_ODCS_USE_CASE=build/lambda/orders python -c 'import cedar_odcs.gateway.handler'` succeeds on the Mac for the pure-Python path (cedarpy import will fail on the Mac against a Linux wheel; that is expected, and the check is that the wheel file is present under `build/lambda/cedarpy*`).
6. **CDK app.**  `infra/` as in CDK app.  `make synth` green.  Commit.
   - Verify: `cdk synth` output contains `AWS::BedrockAgentCore::Gateway` with two `InterceptorConfigurations` entries, `PassRequestHeaders: true` on both, `AWS::BedrockAgentCore::GatewayTarget` named `orders`, `AWS::Cognito::UserPool`.
7. **Deploy and users.**  Check for the CDKToolkit stack, bootstrap if absent.  `make deploy`, `make users` with `APPLIED_ODCS_PASSWORD` set in the session's environment (generate one, keep it in `.env.applied-odcs`, which is ignored, and let `docs/status.md` say where it is).  Commit `.env.applied-odcs.example` (names only).
   - Verify: `aws bedrock-agentcore-control get-gateway` shows `READY`; `make token USER=alice` prints a token whose payload decodes with `username: alice`.
8. **Live calls and recordings.**  `make call USER=alice TOOL=list_orders`, then `carol`, then `dave`.  `make call USER=alice TOOL=get_order ARGS='{"orderId":"order-2002"}'` (Bob's order; expect an empty object).  `make call USER=dave TOOL=refund_order ARGS='{"orderId":"order-1001"}'` and the same as `alice` (expect 403 with the explanation).  Record each with `make record`.  Commit the fixtures.
   - Verify: Alice's list has her two rows with seven fields and no `internalNotes` or `fraudScore`; Carol's has every row with seven fields and no `shippingAddress` or `cardLast4`; Dave's has every row with five public fields; `make check` passes with the live fixtures included.  If a live result differs from the local `dry-run` on the same identity and response, stop and write the difference to `docs/status.md`; that is a finding, not something to patch around.
9. **Demo script.**  `docs/demo.md` with the sequence in Demo script below, each command followed by its real output pasted from step 8.  `make demo` runs it.  Commit.  Write `docs/status.md`: what is deployed, the outputs, where the password is, what passed.
10. **cedar-odcs: role grants rendered to policies.**  As in Library changes.  Tag `v0.2.1`.  In the sample: add `grants.yaml`, remove P4, P5, P6, P11 from `policies.cedar`, bump the pin, `make check` green with the corpus unchanged, redeploy, rerun step 8's three list calls.  Commit both repos.
    - Fallback at 03:00 local: leave the hand-written policies, note it in `docs/status.md`.
11. **cedar-odcs: tool schema gate.**  As in Library changes.  Tag `v0.2.2`, bump the pin.  Break `tools.json` on purpose once (drop `cardLast4` from the output schema) to show the failure message, restore it.  Commit.
12. **Close.**  `make check` and `make synth` green at the final commit in both repos.  `git status` clean in both.  `docs/status.md` carries: commits and tags made, what is deployed and its outputs, where the demo password is, every fallback taken, every unverified item from this plan with what was observed (the tool-name key in the Lambda context, `passRequestHeaders` on the response interceptor, the exact Gateway event shape), and the teardown command (`cdk destroy`) not run.

## Demo script for Monday

Ten minutes, terminal only, in this order.  Each line is a Makefile target so the typing is short.  Expected output is what the overnight run pastes into `docs/demo.md`; the shapes below are what to look for.

1. `cat orders/contract/order.odcs.yaml`.  Point at `internalNotes: internal`, `fraudScore: restricted`, and the `writer` properties.  The sentence: a policy never names a field; this file does.
2. `make check`.  Build, validate, run-tests, the handler tests, all green, no AWS.  The sentence: this is the pipeline gate.
3. `make call USER=alice TOOL=list_orders`.  Two rows, seven fields, no `internalNotes`, no `fraudScore`, and Bob's order is gone.
4. `make call USER=carol TOOL=list_orders`.  Every row, seven fields, no `shippingAddress`, no `cardLast4`.  Same tool, same API response, different caller.
5. `make call USER=alice TOOL=refund_order ARGS='{"orderId":"order-1001"}'`.  A 403 from the request interceptor with the explanation naming the verb.  The sentence: the request leg never let it reach the API.
6. `make call USER=dave TOOL=refund_order ARGS='{"orderId":"order-1001"}'`.  Allowed; the response comes back with public fields only.
7. `uv run cedar-odcs dry-run orders --caller orders/tests/identities/carol-for-alice.json --tool orders___list_orders --response orders/tests/lists/orders.json`.  Carol acting for Alice holds Alice's access and not her own: Alice's two rows, Alice's fields.  The sentence: this is the case Cognito cannot mint and Ping can.
8. Edit `orders/contract/order.odcs.yaml`: change `cardLast4` from `confidential` to `internal`.  `make check`, then `make deploy`, then step 3 again.  Alice no longer sees `cardLast4`; Carol now does.  No policy changed.  Revert the edit.
9. `uv run cedar-odcs check-access orders --caller orders/tests/identities/carol.json`.  Every verb, every readable field, every writable field for Carol, from real authorization questions.
10. `uv run cedar-odcs share orders --case "support reads any order"`.  Opens the case in Cedar's playground for anyone who wants to pull on it.

Step 8 is the one to rehearse: a deploy takes a minute or two, so either run it live and talk through the mapping table while it goes, or show the before and after recorded fixtures.  If the deployed Gateway is down on Monday, steps 3 to 6 and 8 run as `dry-run` against the recorded responses, which is what `make check` already does.

## Risks and fallbacks

| Risk | How it shows | Fallback |
| --- | --- | --- |
| `LambdaInterceptor.forResponse` does not take `passRequestHeaders` in the installed `aws-cdk-lib` | The response handler rejects every call with `no bearer token` | Set the option on the L1 `CfnGateway.interceptorConfigurations` entry; if the service itself does not pass headers to the RESPONSE point, the request interceptor copies the decoded claims into a header the Gateway forwards, and the response handler reads that; note either in `docs/status.md` |
| The tool-name key in the Lambda target's context differs from `bedrockAgentCoreToolName` | The tool Lambda returns `unknown tool` | Log the full `client_context` on the first invoke, read it from CloudWatch, fix the key |
| Gateway event shape differs from the cedar-odcs fixtures | The handlers return `request could not be evaluated` | `CEDAR_ODCS_RECORD=1` logs the event; compare with `tests/events/`, adjust `handlers.py` in cedar-odcs, tag `v0.2.x`, rebundle.  This is the single most valuable finding of the night if it happens, since the fixtures were written from documentation |
| Cognito access token lacks `username` or `cognito:groups` | Token decodes without them | `username` is standard in Cognito access tokens and `cognito:groups` is present when the user is in a group; if the installed pool differs, switch the mapping to the ID token (`cognito:username`) and send the ID token instead |
| cedarpy Linux wheel not picked by `uv pip install --python-platform` | `ImportError` on first invoke | Wheels exist for aarch64 and x86\_64 on 3.12; switch architecture or pin `cedarpy==4.12.2` explicitly |
| Gateway creation fails on the Cognito authorizer | `cdk deploy` rolls back | Use `GatewayAuthorizer.usingCustomJwt` with the pool's discovery URL `https://cognito-idp.us-east-1.amazonaws.com/<poolId>/.well-known/openid-configuration` and `allowedClients: [clientId]`; same shape as the Ping port |
| AgentCore Gateway interceptors unavailable in the account or region | `CREATE_FAILED` naming the interceptor property | Deploy without interceptors to prove the target, run the handlers locally on recorded events for the demo, say so on the asks slide |
| Interceptor cold start exceeds the Gateway's timeout | Intermittent 5xx on first calls | Raise memory to 1024 MB; warm the two functions from `make demo` before the meeting |
| The grants generator changes a decision | The copied corpus fails after step 10 | That is the test working; keep the hand-written policies and file the difference |
| Overnight cost | None of these resources are expensive; the Gateway bills per request | `cdk destroy` after Monday |

Two items in this plan are marked unverified and must be confirmed from the first live call rather than assumed: the tool-name key in the Lambda context and whether the RESPONSE interception point receives request headers.  Both go in `docs/status.md` with what was observed.

## Out of scope and next steps

Not built overnight, and named in the doc and the deck as the steps after Monday.

- **Option (c), contract and policies loaded at runtime.**  The interceptor reads the contract, the generated maps, and the policies from S3 or a parameter at cold start with a short cache, so a classification change in the catalog reaches enforcement with no redeploy.  Maps onto the kill-switch pattern the platform team already runs (a table read on every call with a cache TTL).
- **On-behalf-of through PingFederate.**  RFC 8693 token exchange gives the Gateway a token with an `act` claim; the engine already handles it, and the mapping names the claim.  Carol acting for Alice becomes a live call.
- **The port to the Delta constructs.**  `DeltaAgentCoreGateway` with `requestInterceptor` and `responseInterceptor`, `DeltaLambdaGatewayTarget`, `DeltaStack`, Ping as the authorizer.  The mapping table in the questions doc is the diff.  The ask to the platform team is whether this becomes a construct of theirs: a governed target that takes a folder with a contract, policies, and tests and produces the two interceptors.
- **AgentCore Policy.**  AWS now ships a Cedar policy engine on the Gateway (`policyEngineConfiguration`, alpha in CDK) that decides tool calls on the request path with `context.input.*` conditions.  It covers part of cedar-odcs's request leg and none of the response leg.  The doc should say where the two meet: AgentCore Policy for verb-level allow and deny on arguments, cedar-odcs for the contract-keyed field decisions and for the response.  Worth a slide, since the platform team will have seen it.
- **The proofs in the sample's pipeline.**  Package cvc5 and the analysis crate in a container image so `prove` runs in GitLab, not only on a machine with cargo.
- **Contract from the catalog.**  The sample's `contract/unity/` fixtures are the stand-in for Unity Catalog; the real pull is a `pull` importer against the catalog API once Delta's catalog is ready.
- **Tool binding at deploy time.**  Today the Gateway target name and the descriptor's tool names agree by convention (`orders___`).  The CDK app could read `tools.json` and the descriptor and fail synth when they disagree.
- **A declarative descriptor.**  `usecase.py` as YAML next to the contract, so a tool team writes no Python.
