# applied-odcs runtime port: implementation plan

October 18, 2026.  Exported from the Claude Doc at https://claude.ai/code/artifact/a01e8d4e-bfe9-4b56-a9c9-555b1aee1765 (the doc has the architecture diagram).

## Goal and scope

Port the orders tool from a Lambda function target to an MCP server on AgentCore Runtime, because Delta does not allow Lambda-function MCP tools (decision 30 in the decision log).  The port runs on a branch, `runtime-mcp`, in its own git worktree, and deploys as a second stack in the personal account.  The working `AppliedOdcs` stack and the main checkout stay exactly as they are, so the demo keeps working.

This plan is for a Claude Code session.  It is step 1 of three on this branch; the bundle loader and the Runtime API proxy spike get their own plans after this one lands.

### In scope

- A stack variant switch, so the same CDK app deploys `AppliedOdcs` unchanged or `AppliedOdcsRuntime` with every name prefixed.
- The five orders tools as an MCP server (MCP Python SDK, FastMCP) with the same data and the same behavior as `orders/tool/handler.py`.
- An AgentCore Runtime of protocol MCP hosting it, behind the same kind of Gateway, interceptors, and Cognito pool, with OAuth from the Gateway to the Runtime.
- The eight live calls re-recorded against the runtime stack and compared, decision by decision, with the Lambda function target recordings.
- A cedar-odcs fix, released as v0.2.5, only if the response interceptor cannot read an MCP server's results.

### Out of scope

- Production gaps 0.1 and 0.2 (records in the deployed store, writes reading the record first).  The runtime stack keeps today's behavior, including Alice's 403 on order-2002.
- The bundle format, the loader, and anything about Lambda extensions.
- Delta constructs.  This stays plain `aws-cdk-lib` 2.273.0, with each construct commented with the Delta construct it maps to, as today.
- Merging to main.  The branch stays open for review.

## Starting point

What the repo holds today, read from the main checkout on October 18 at commit `e8126a9`.

| Area | Today |
| --- | --- |
| Engine pin | `pyproject.toml` pins `cedar-odcs @ git+https://github.com/samdengler/cedar-odcs.git@v0.2.4`.  `lambda/bundle.sh` reads the same pin; `CEDAR_ODCS_SOURCE` overrides it with a local checkout while iterating. |
| CDK app | `infra/bin/applied-odcs.ts` creates one stack, `AppliedOdcs`.  `infra/lib/governed-tool-stack.ts` holds a Cognito pool named `applied-odcs` with groups support, finance, and employee; the `OrdersTool` Lambda function; two interceptor functions running `cedar_odcs.gateway.handler.request` and `.response`; a Gateway named `applied-odcs` in MCP mode with a Cognito authorizer and `exceptionLevel` DEBUG; and `addLambdaTarget('Orders')` with `gatewayTargetName: 'orders'` and `orders/tools.json` as the tool schema. |
| Tool | `orders/tool/handler.py` reads `bedrockAgentCoreToolName` from the client context, strips the `orders___` prefix, and runs one of five functions over `orders/tool/data/orders.json`.  Writes change memory only. |
| Interceptor parsing | `cedar_odcs/gateway/handlers.py` in v0.2.4 already reads a tool result from `structuredContent` when present, else from the first text content item, and on the way out writes the filtered payload to both `structuredContent` and a single text item. |
| Outputs and secrets | `scripts/env.py` reads the `AppliedOdcs` key from `build/outputs.json` and writes `.env.applied-odcs` (ignored, mode 600), generating the demo password once. |
| Makefile | `check`, `bundle`, `synth`, `deploy`, `users`, `token`, `call`, `record`, `demo`, all reading `.env.applied-odcs`. |
| Live fixtures | Eight `orders/tests/events/live-*.json` recordings from the Lambda function target, replayed by `make check`. |
| Session settings | `.claude/settings.json` denies `cdk destroy`, `git push --force`, and reading `./.env.applied-odcs`.  `CLAUDE.md` holds the conventions and the unattended rules. |

## Target architecture

The caller (`client/call.py` with a Cognito user token) calls the Gateway in MCP mode.  The Gateway runs the request and response interceptors as today and routes to an MCP server target named `orders`.  The target calls an AgentCore Runtime of protocol MCP, ARM64, running the FastMCP orders server, with an OAuth token issued to a new Cognito M2M client.  The Runtime's inbound JWT authorizer accepts only that client.

The caller, the Cognito user client, the Gateway, and both interceptors are the same as in `AppliedOdcs`.  Three things are new:

- **The MCP server target** replaces `addLambdaTarget`.  The Gateway syncs the tool list from the server's `tools/list` when the target is created, and calls the Runtime's invocation endpoint with an OAuth token from its credential provider.  Tool names reach the interceptors as `orders___<tool>`, as today.
- **The AgentCore Runtime** of protocol MCP hosts the FastMCP server, listening on `0.0.0.0:8000/mcp` with stateless streamable HTTP, as the Runtime's MCP contract requires.  Its inbound authorizer accepts only tokens issued to the M2M client.
- **The M2M client** is a second Cognito app client with the client credentials grant and a resource server scope.  It stands in for the Ping client that `DeltaAgentCoreRuntimeMcp` configures with `credentialSecretName`.

The server does no authorization, as the tool Lambda function did not.  The interceptors decide every call.

## Isolation rules

These keep `AppliedOdcs` and the main checkout untouched, and keep the branch safe to merge later.

| Rule | How |
| --- | --- |
| Separate checkout | The session works only in the worktree at `~/src/github.com/samdengler/applied-odcs-runtime`, on branch `runtime-mcp`.  It never edits, builds, or runs make targets in `~/src/github.com/samdengler/applied-odcs`. |
| A variant switch with an unchanged default | The CDK app reads `-c variant=<name>`.  With no variant, it synthesizes `AppliedOdcs` with today's resources and names, and a Lambda function target.  With `variant=runtime`, it synthesizes `AppliedOdcsRuntime`, prefixes every physical name with `applied-odcs-runtime`, and uses the MCP server target. |
| Proof the default did not move | Step 1 synthesizes the default variant on the branch and compares the template with one synthesized from the `demo-lambda-target` tag.  They must be identical apart from asset hashes. |
| Make targets per variant | `VARIANT ?=` in the Makefile.  Every target passes `-c variant=$(VARIANT)` to CDK, reads and writes `.env.applied-odcs$(if $(VARIANT),-$(VARIANT))`, and `scripts/env.py` reads the outputs key for the stack it deployed. |
| No accidental deploy of the main stack | On the branch, `make deploy` refuses to run unless `VARIANT=runtime` is set.  The session never runs `cdk deploy AppliedOdcs`. |
| Secrets | The runtime stack's password and the M2M client secret live only in `.env.applied-odcs-runtime`.  `.gitignore` covers `.env.applied-odcs*` except `.env.applied-odcs.example`, and `.claude/settings.json` denies reading `./.env.applied-odcs-runtime`. |
| Engine pin | Main stays on cedar-odcs v0.2.4.  If the branch needs a fix, it pins a new tag (v0.2.5) in its own `pyproject.toml`.  `CEDAR_ODCS_SOURCE` is for local iteration only and is never left in a commit. |
| Account and region | The personal account, `us-east-1`, the default profile.  Nothing else. |

## Kickoff

This plan is also saved in the main checkout at `docs/plan-runtime.md`, untracked.  Run these from a terminal before starting the session:

```
cd ~/src/github.com/samdengler/applied-odcs
git tag demo-lambda-target e8126a9
git push origin demo-lambda-target
git worktree add ../applied-odcs-runtime -b runtime-mcp demo-lambda-target
cp docs/plan-runtime.md ../applied-odcs-runtime/docs/
cd ../applied-odcs-runtime
claude --model opus --add-dir ../cedar-odcs
```

First message to the session:

> Execute docs/plan-runtime.md.  Start at step 1 of the Work order and follow the plan's rules and CLAUDE.md.  Record every default, fallback, and finding in docs/status-runtime.md as you go.

Opus for the main session, because steps 3 to 5 are CDK and auth work against APIs the plan marks unverified.  The `log-reader` and `fixture-writer` sub-agents from `CLAUDE.md` still apply.

## Work order

Each step ends with a commit on `runtime-mcp` once its checks pass.  A step that fails its checks is fixed or takes its named fallback; it is never committed over.

### Step 1: Variant switch and baseline

1. `uv sync` and `cd infra && npm ci`.
2. Before changing anything, run `make synth` and save `infra/cdk.out/AppliedOdcs.template.json` as `build/baseline-AppliedOdcs.template.json`.  This is the template the tag produces.
3. Add the variant switch from the isolation rules: `infra/bin/applied-odcs.ts` reads `variant` from context and names the stack `AppliedOdcs` or `AppliedOdcsRuntime`; `GovernedToolStack` takes `variant` as a prop and derives every physical name (user pool, Gateway, log groups if named) from one prefix.  Construct IDs stay as they are.
4. Makefile: `VARIANT ?=`, an `ENV` that follows it, `-c variant=$(VARIANT)` on every CDK call, and a guard so `make deploy` fails with a clear message when `VARIANT` is empty.
5. `scripts/env.py` takes the env file and reads the single stack key in the outputs file instead of the literal `AppliedOdcs`.  `scripts/demo.sh` and the clients read the env file the Makefile passes.
6. `.gitignore` covers `.env.applied-odcs*` except the example.  `.claude/settings.json` denies `Read(./.env.applied-odcs-runtime)`.  `CLAUDE.md` gains a short section: this worktree is the `runtime-mcp` branch, deploys only with `VARIANT=runtime`, and records in `docs/status-runtime.md`.
7. Create `docs/status-runtime.md` with sections for defaults, fallbacks, findings, and the live comparison.

**Done when:** `make check` passes; `make synth` with no variant produces a template identical to the baseline apart from asset hashes (write `scripts/compare_templates.py` for this); `make synth VARIANT=runtime` produces `AppliedOdcsRuntime` with every physical name prefixed; nothing is deployed.

### Step 2: Orders MCP server

1. Create `orders/server/server.py` with the MCP Python SDK's FastMCP: name `orders`, host `0.0.0.0`, port 8000, stateless streamable HTTP at `/mcp`.  Pin the `mcp` version in `orders/server/requirements.txt` and record it.
2. The five tools keep the names, argument names, and behavior of `orders/tool/handler.py`: `get_order(orderId)`, `list_orders()`, `update_order(orderId, changes)`, `cancel_order(orderId)`, `refund_order(orderId)`, over the same `orders.json`, writes in memory, an unknown `orderId` raised as a tool error.  Single-record tools return the order as a dict; `list_orders` returns the list.  The server does no authorization.
3. A `server-build` Makefile target assembles `build/server/` from `orders/server/` and `orders/tool/data/orders.json`, so the data has one source.
4. `orders/tests/test_server.py`, run in process with the SDK's in-memory client session: `tools/list` names and input schemas match `orders/tools.json` (names, properties, required); each tool returns the same result as `handler.py` for the same arguments.
5. Record exactly what FastMCP emits for a single record and for `list_orders`: `structuredContent`, the text content, and `outputSchema` (known unknown K2).

**Done when:** `make check` passes with the new tests, and the server answers `initialize` and `tools/list` over HTTP on a local run.

### Step 3: Runtime, M2M client, and MCP server target

Everything here is in the `variant=runtime` branch of the stack; the default variant keeps the Lambda function target.

1. Read the `aws-bedrockagentcore` type definitions in `infra/node_modules/aws-cdk-lib` and record the classes and props for the Runtime, its MCP protocol and JWT authorizer, the Gateway's MCP server target, and outbound OAuth credentials (K1).
2. Cognito: a resource server `orders` with one scope, a user pool domain, and an M2M app client with a secret and the client credentials grant for that scope.
3. AgentCore Runtime, protocol MCP, ARM64, from `build/server/` (container if Docker or Finch is installed, else direct code deployment: K3).  Inbound JWT authorizer with the pool's discovery URL and only the M2M client allowed.
4. An OAuth2 credential provider for the Gateway using the M2M client.  If CDK has no resource for it, use the K1 fallback: a script creates it with boto3 after a first deploy, and a second deploy adds the target with its ARN from context.
5. The Gateway's MCP server target, named `orders`, pointing at the Runtime invocation endpoint (`https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/<URL-encoded runtime ARN>/invocations?qualifier=DEFAULT`, the form the Delta constructs use) with the OAuth credential and scope.  Interceptors as today, `passRequestHeaders: true` on both.
6. Outputs: today's keys plus `RuntimeArn` and `RuntimeLogGroup`.  Update `scripts/check_synth.py` for the variant.
7. `make deploy VARIANT=runtime`, then `make users VARIANT=runtime`.

**Done when:** the target is READY with five tools synced; a `tools/list` through the Gateway as Carol shows the five `orders___` tools; `make call VARIANT=runtime USER=carol TOOL=list_orders` returns five orders with six fields; the Runtime log shows the call.  If the response interceptor withholds the result, go to step 5 before step 4.

### Step 4: Live calls and comparison

1. Record the same eight calls as the Lambda function target fixtures, against the runtime stack, into `orders/tests/events/runtime/`: Alice `get_order` order-2002, Alice `list_orders`, Alice `refund_order` order-1001, Alice `update_order` order-1001 with internalNotes and with shippingAddress, Carol `list_orders`, Dave `list_orders`, Dave `refund_order` order-1001.  Redact the caller's address as the existing recordings do.
2. `scripts/compare_live.py` pairs each runtime recording with its Lambda function target recording and compares the outcome: HTTP status, error or result, the row ids, and the field names of each row.  Any difference fails.  Differences in the event envelope (keys, `structuredContent`, streaming flags) are printed separately as findings.
3. `make check` replays both sets of recordings through the local handlers.

**Done when:** all eight outcomes match, including Alice's two orders with seven fields, Carol's five orders with six fields, Dave's empty refund, and Alice's 403 on order-2002; the envelope findings are in `docs/status-runtime.md`.

### Step 5: cedar-odcs fix, only if needed

1. Only when step 3 or 4 shows the interceptors misreading or mis-writing an MCP server result.  Write the cause in `docs/status-runtime.md` first.
2. In `../cedar-odcs`, follow its `CLAUDE.md` (a Beads issue for the change).  Add the redacted runtime events as test fixtures, fix the parsing, and keep every existing test passing so Lambda function target events behave as in v0.2.4.  Version 0.2.5, tag `v0.2.5`, push.
3. Pin the branch's `pyproject.toml` to v0.2.5, `uv lock`, redeploy the runtime variant, and rerun step 4.

**Done when:** step 4 passes on v0.2.5, and main still pins v0.2.4.

### Step 6: Demo, writes, and latency

1. Run `make demo VARIANT=runtime` and record any step whose output differs from `docs/demo.md`.
2. Check whether an in-memory write survives to the next call (update, then get).  Record the result; do not fix it (K7).
3. Time ten warm `list_orders` calls as Carol against each stack and record the median and the worst.  Calling the main stack's Gateway is allowed; deploying to it is not.

**Done when:** the three results are in `docs/status-runtime.md`.

### Step 7: Close

1. Finish `docs/status-runtime.md`: every default, fallback, finding, and the open questions for the bundle loader plan.
2. Add a runtime variant section to the README with the commands.
3. Commit and `git push -u origin runtime-mcp`.  Do not merge, do not tag applied-odcs, and leave both stacks deployed.

**Done when:** the branch is pushed and the status file says what to read first.

## Known unknowns and defaults

None of these were verified while writing the plan.  For each, take the default, record what you observed, and take the fallback if the default fails.

| | Unknown | Default | Fallback |
| --- | --- | --- | --- |
| K1 | Which `aws-bedrockagentcore` classes in aws-cdk-lib 2.273.0 cover the Runtime, its MCP protocol and JWT authorizer, the MCP server target, and an OAuth2 credential provider. | Use the L2 classes the type definitions show. | L1 `Cfn*` resources for anything missing; for the credential provider, a boto3 script (`bedrock-agentcore-control`) and a two-pass deploy passing its ARN through context. |
| K2 | What FastMCP puts in `structuredContent` for a list result.  The MCP spec requires an object, so a list may arrive wrapped as `{"result": [...]}`, which v0.2.4 would hand to the engine as a dict. | Keep `list_orders` returning a list and observe. | If wrapped, fix in cedar-odcs v0.2.5 (step 5): unwrap a single `result` key for a list tool on the way in, and wrap again on the way out. |
| K3 | Whether Docker or Finch is installed for an ARM64 container build. | Container image from `build/server/`, the form the Delta constructs recommend. | Direct code deployment: dependencies installed for Linux arm64 the way `lambda/bundle.sh` does it. |
| K4 | Whether the RESPONSE interceptor event for an MCP server target matches the Lambda function target's (keys, a streamed body, `isStreamingResponse`). | v0.2.4 parsing as is. | Step 5. |
| K5 | Whether the Gateway can reach the Runtime with OAuth client credentials from a Cognito M2M client. | OAuth, as `DeltaAgentCoreRuntimeMcp` does with Ping. | If the Gateway offers IAM outbound to a Runtime in this version, note it but stay on OAuth to match Delta.  If OAuth cannot be made to work, stop (rules below). |
| K6 | How the Gateway resyncs tools after the server changes. | Redeploying the target. | The control-plane synchronize call, if it exists; record which one worked. |
| K7 | Whether in-memory writes survive between calls, since the Runtime may serve calls from different sessions. | Observe and record in step 6. | None needed; the demo's write calls return the changed record in the same call. |

## Rules for the session

- Work only in the `applied-odcs-runtime` worktree and, for step 5 only, in `../cedar-odcs`.  Never edit or build in the main `applied-odcs` checkout.
- Deploy only `AppliedOdcsRuntime`, only with `VARIANT=runtime`, only to the personal account in `us-east-1`.  Never run `cdk destroy`.  Never deploy or change `AppliedOdcs`.
- Secrets go only in `.env.applied-odcs-runtime`.  `docs/status-runtime.md` says where a secret is, never what it is.  The M2M client secret is never printed or logged.
- Generated outputs stay uncommitted: `build/`, `infra/cdk.out/`, `orders/contract/generated/`, `orders/entities.json`.
- Conventions from `CLAUDE.md` hold: two spaces after a period, no em or en dashes, commit messages in the cedar-odcs style.
- Take the plan's default instead of asking, and record every default, fallback, and finding in `docs/status-runtime.md` as it happens.

### Stop conditions

Stop, write the state into `docs/status-runtime.md`, commit what passes, and push the branch when:

- The Gateway cannot reach the Runtime after the K1 and K5 fallbacks.  Do not work around it by removing the Runtime's inbound authorizer or by putting a Lambda function in front of the Runtime.
- A cedar-odcs change would alter a decision for a Lambda function target event, meaning an existing cedar-odcs test would need to change.
- Any step would need a change to the main checkout, to `AppliedOdcs`, or to an account other than the personal one.
