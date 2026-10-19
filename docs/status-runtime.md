# Runtime port status

The run of `docs/plan-runtime.md` on branch `runtime-mcp`, in the worktree at `~/src/github.com/samdengler/applied-odcs-runtime`, on October 18, 2026, from tag `demo-lambda-target` (`e8126a9`).  Each entry says what the plan asked, what was done, and what was observed.

## Read first

1. Live comparison (below): the eight calls through the MCP server target decide exactly as through the Lambda function target, on cedar-odcs v0.2.5.
2. Step 5: why v0.2.4 withheld every list from FastMCP, and the fix.
3. Step 6: every tool call gets a new Runtime session, so in-memory writes are lost and the median call is about four times slower.
4. Open questions for the bundle loader plan, at the end.

## Steps

| Step | State | Commits |
| --- | --- | --- |
| 1. Variant switch and baseline | done | `62303c5` |
| 2. Orders MCP server | done | `d33d482` |
| 3. Runtime, M2M client, and MCP server target | done, after step 5 | `20cabe2`, `b779549` |
| 4. Live calls and comparison | done on v0.2.5: eight of eight outcomes match | `23d9f3b` |
| 5. cedar-odcs fix | done: v0.2.5, run before step 4 | cedar-odcs `63bdc08`, tag `v0.2.5`; the pin is in `20cabe2` |
| 6. Demo, writes, and latency | done | `903d9dd` |
| 7. Close | done | the closing commit on `runtime-mcp`, pushed |

## What is deployed

Stack `AppliedOdcsRuntime` in account 009080466601 (the default profile's SSO account), us-east-1, plain aws-cdk-lib 2.273.0, interceptors on cedar-odcs v0.2.5, Runtime on platform V2 (version 4, the server with the warm-up).  `AppliedOdcs` is unchanged and still deployed from the main checkout; this session deployed nothing to it.

| Output | Value |
| --- | --- |
| GatewayUrl | `https://applied-odcs-runtime-dqm57bvsfy.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp` |
| GatewayId | `applied-odcs-runtime-dqm57bvsfy` (target `orders`, `DBK9EXVI3G`, `READY`) |
| UserPoolId | `us-east-1_Fs1wXDVBY` (pool `applied-odcs-runtime`) |
| ClientId | `2ls1ouutvh4fig2n7ln2aouoai` (users) |
| M2MClientId | `r1r5s5brui7qjk8ncl2vt535q` (Gateway to Runtime) |
| TokenEndpoint | `https://applied-odcs-runtime-009080466601.auth.us-east-1.amazoncognito.com/oauth2/token` |
| RuntimeArn | `arn:aws:bedrock-agentcore:us-east-1:009080466601:runtime/applied_odcs_runtime_orders-T2FW6DHYSp` |
| RuntimeLogGroup | `/aws/bedrock-agentcore/runtimes/applied_odcs_runtime_orders-T2FW6DHYSp-DEFAULT` |

Users: Alice (no groups), Carol (`support`, `employee`), Dave (`finance`, `employee`), from `make users VARIANT=runtime`.  Teardown, not run: `cd infra && npx cdk -c variant=runtime destroy AppliedOdcsRuntime`.  The OAuth2 credential provider and the container image in the CDK assets repository are worth checking after a teardown.

### Step 1

- `uv sync` and `npm ci` in `infra/`.  `make synth` before any change; its `infra/cdk.out/AppliedOdcs.template.json` is saved as `build/baseline-AppliedOdcs.template.json` (17497 bytes, not committed).
- `make compare-baseline` synthesizes the default variant and runs `scripts/compare_templates.py` against the baseline.  It reports the templates identical.  The asset hashes and the `CDKMetadata` analytics string came out unchanged as well, so the script's hash placeholder had nothing to hide.
- `make synth VARIANT=runtime` produces `AppliedOdcsRuntime` with user pool `applied-odcs-runtime` and Gateway `applied-odcs-runtime`.  `scripts/check_synth.py` passes on it.
- `make deploy` with no variant stops at `deploy-guard` with `make deploy: this branch deploys only AppliedOdcsRuntime; run make deploy VARIANT=runtime`.
- `make check` passes (124 tests).  Nothing deployed.

### Step 2

- `orders/server/server.py`: FastMCP `orders`, host `0.0.0.0`, port 8000, `stateless_http=True`, streamable HTTP at `/mcp`.  The five tools keep the names, argument names, descriptions, and behavior of `orders/tool/handler.py`.  `orders/server/requirements.txt` pins `mcp==1.30.0`; the dev group in `pyproject.toml` pins the same for the tests.
- `make server-build` assembles `build/server/` from `server.py`, `requirements.txt`, and `orders/tool/data/orders.json`.
- `orders/tests/test_server.py` runs the server in process with `create_connected_server_and_client_session`: `tools/list` names, input properties, required lists, and descriptions match `orders/tools.json`; eight calls of the five tools, writes included, return what `handler.py` returns for the same arguments, read from `structuredContent` and from the text content; an unknown `orderId` is a tool error.  `make check` passes (127 tests).
- `make server-smoke` starts `build/server/server.py` on the Mac and gets `server ok: orders 1.30.0 answered initialize (2025-06-18) and tools/list with cancel_order, get_order, list_orders, refund_order, update_order`.  No `Mcp-Session-Id` header comes back, as stateless HTTP should.

What FastMCP 1.30.0 emits (K2):

| | Single record (`get_order`) | `list_orders` |
| --- | --- | --- |
| `structuredContent` | the order object | `{"result": [five orders]}` |
| text content | one text item, the order as indented JSON | five text items, one order each as indented JSON |
| `outputSchema` | `{"type": "object", "additionalProperties": true, "title": "get_orderDictOutput"}` | `{"type": "object", "properties": {"result": {"type": "array", "items": {"type": "object", "additionalProperties": true}}}, "required": ["result"], "title": "list_ordersOutput"}` |
| tool error | `isError: true`, one text item `Error executing tool get_order: unknown orderId: 'order-0'`, no `structuredContent` | |

The Lambda function target's recorded result for `list_orders` (`live-carol-list_orders.json`) has `content` with one text item holding the whole list and no `structuredContent`.

### Step 3

- K1 read from `infra/node_modules/aws-cdk-lib/aws-bedrockagentcore/lib` (table under Known unknowns).  Every piece has an L2 class, so no L1 resource and no boto3 script was needed.  One L1 property override: the target's OAuth `GrantType`.
- The runtime variant adds a resource server `orders` with scope `invoke`, a Cognito domain `applied-odcs-runtime-<account>`, the M2M client (secret, client credentials only, scope `orders/invoke`), the Runtime `applied_odcs_runtime_orders` (protocol MCP, container from `build/server/` for `linux/arm64`, JWT authorizer with the pool's discovery URL and `AllowedClients` the M2M client only), the OAuth2 credential provider `applied-odcs-runtime-orders`, and the MCP server target `orders` at `https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/<ARN with %3A and %2F>/invocations?qualifier=DEFAULT`.  The tool Lambda is not created in this variant, so `ToolLogGroup` is not an output.
- `make synth VARIANT=runtime` passes the extended `scripts/check_synth.py`.  `make compare-baseline` still reports the default variant identical to the tag.
- Synth warning, accepted: `The secret ARN is an unresolved token. Granting access using a wildcard prefix (bedrock-agentcore-identity!*)`.  The Gateway role may read any Token Vault secret with that prefix in the account, because the credential provider's secret ARN is only known after deploy.
- The first attempt at `make deploy VARIANT=runtime` stopped before deploying: `aws sts get-caller-identity` answered `Error when retrieving token from sso: Token has expired and refresh failed`.  After `aws sso login`, account 009080466601.
- `make deploy VARIANT=runtime` created `AppliedOdcsRuntime` in 83 seconds on the first try.  `make users VARIANT=runtime` created Alice, Carol, and Dave.
- `get-gateway-target`: target `orders` (`DBK9EXVI3G`) `READY`, `lastSynchronizedAt` 22:19:44 UTC, OAuth provider `applied-odcs-runtime-orders` with `grantType: CLIENT_CREDENTIALS` and scope `orders/invoke`.  The synchronization itself is the Gateway calling the Runtime's `tools/list` with an M2M token, so outbound OAuth worked at create time.
- `make tools VARIANT=runtime USER=carol` (new: `client/tools.py`, a `tools/list` through the Gateway): `200  5 tools`, `orders___cancel_order`, `orders___get_order`, `orders___list_orders`, `orders___refund_order`, `orders___update_order`.  The Gateway serves FastMCP's output schemas as synced: `object` for the four single-record tools, and an object with one property `result` for `list_orders`.
- `make call VARIANT=runtime USER=carol TOOL=list_orders`: `403  error`, `response withheld; it could not be filtered: list tool returned no list`.  The Runtime log has `Processing request of type CallToolRequest` for it, so the call reached the server and the response interceptor withheld the result.  Per the plan, step 5 runs before step 4.

### Cause of the withheld list (step 5, written before the fix)

The response event the interceptor received for that call (`record response` in the response log group) has the same envelope as the Lambda function target's: top keys `interceptorInputVersion` and `mcp`; `mcp` keys `gatewayRequest`, `gatewayResponse`, `rawGatewayRequest`; `gatewayResponse` keys `path`, `httpMethod`, `headers` (empty), `body` (a parsed object), `statusCode` 200, `isStreamingResponse: false`.  The result differs.  The Lambda function target's result is `content` with one text item holding the whole list, and no `structuredContent`.  The MCP server's result is `content` with five text items, one order each, and `structuredContent: {"result": [five orders]}`, passed through from FastMCP unchanged.

cedar-odcs v0.2.4 `_result_payload` reads `structuredContent` when present, so the engine is handed the dict `{"result": [...]}` for a tool whose result kind is `list`, and `decide_response` raises `list tool returned no list`.  The fix the plan names (K2 fallback): for a list tool, unwrap a `structuredContent` that is an object with the single key `result` holding a list, and wrap the filtered rows the same way on the way out.  Lambda function target events have no `structuredContent`, so their path does not change.

### Step 5

- Cause written first (above).  In `../cedar-odcs`: Beads issue `cedar-osdc-bno`, claimed and closed.
- `cedar_odcs/gateway/handlers.py`: `_wrapped_list(result, returns)` is true only for a list tool whose `structuredContent` is an object with the single key `result` holding a list.  `_result_payload` unwraps it on the way in and `_with_payload` wraps the filtered rows as `{"result": [...]}` on the way out; the text content becomes one text item with the filtered list, as for any result.  `returns` defaults to `None`, which is the v0.2.4 path.
- `cedar_odcs/gateway/test_mcp_server_results.py`, six tests over the two redacted live events (Carol `list_orders` and Alice `update_order` with `shippingAddress`, recorded from this stack on v0.2.4) in `usecases/orders/tests/mcp-server-events/`: the live list is wrapped; it is filtered and leaves wrapped with one text item; its rows equal the rows the same event gets with a Lambda function target's result; the single record does too; a `structuredContent` with a key beside `result` is still withheld; an object tool's `{"result": [...]}` is not unwrapped.  The tests read the Cognito claims (`username`, `cognito:groups`) through `dataclasses.replace` on the orders use case.
- `./check.sh` green: 737 tests (731 at v0.2.4 plus the six), every use case's check, 211 history proofs.  No existing test changed.
- Version 0.2.5, README paragraph on result reading, commit `63bdc08` on `main`, tag `v0.2.5`, both pushed.
- This branch's `pyproject.toml` pins `v0.2.5` and `uv.lock` follows.  The main checkout's `pyproject.toml` still pins `v0.2.4` (read, not changed).
- `make deploy VARIANT=runtime` (21 seconds, interceptors only) with `build/lambda/cedar_odcs-0.2.5.dist-info`.  Then `make call VARIANT=runtime USER=carol TOOL=list_orders`: `200  5 rows`, `order-1001` to `order-5005`, each with the six fields `estimatedDelivery`, `id`, `internalNotes`, `owner`, `status`, `total`.  The Runtime log has its `CallToolRequest`.  Step 3's checks pass.

### Step 4

- `make record VARIANT=runtime` for the eight calls, in the order of the plan, into `orders/tests/events/runtime/`.  Every file has the bearer signature replaced with `signature-redacted` and `X-Forwarded-For` replaced with `203.0.113.10`.
- `make compare-live` (`scripts/compare_live.py`) pairs each with the Lambda function target recording of the same name: 8 of 8 outcomes match.  The table is under Live comparison.
- `make check` replays both sets through the local handlers on v0.2.5 (`test_live_recording_matches_the_local_handlers`, 16 cases) and passes (136 tests).

### Step 6

`make demo VARIANT=runtime` ran end to end (output in `build/demo-runtime.txt`, not committed).  Every line of `docs/demo.md`'s output blocks appears in it except these:

| Demo step | `docs/demo.md` | Runtime stack | Why |
| --- | --- | --- | --- |
| 2 | `124 passed` | `136 passed` | The branch adds the server, client, and runtime replay tests. |
| 3, 4, 8 | order-1001 `"status": "refunded"` | `"status": "shipped"` | Dave's refund in step 6 (and earlier) did not persist to the next call (K7).  On the Lambda function target a warm container kept it. |
| 12 | the playground link | a different link | The link is a gzip of the case, and it changes between runs on either stack. |

The decisions are the same in every step: the same rows, the same fields, the same 403 messages, Dave's empty object.

Writes (K7): three rounds of Alice `update_order` order-1001 with `shippingAddress` `1 Birch Ave`, `2 Birch Ave`, `3 Birch Ave`, each followed by Alice `get_order` order-1001.  Every update returned the new address in its own call; every `get_order` returned the original `1 Oak Ln`.  Each Runtime log stream (`/aws/bedrock-agentcore/runtimes/applied_odcs_runtime_orders-T2FW6DHYSp-DEFAULT`, streams named `<date>/[runtime-logs]<uuid>`) begins with `Started server process [1]` and `Uvicorn running on http://0.0.0.0:8000`, then holds one call's `initialize`, `notifications/initialized` (202), and `CallToolRequest`, plus the Runtime's pings.  So the Gateway opens a new Runtime session, with a fresh server process and fresh memory, for every tool call.  Recorded, not fixed, as the plan says.

Latency: `make latency` (`client/latency.py`), Carol `list_orders`, one sign-in and one `initialize`, two warmup calls, then ten timed `tools/call` round trips, from this Mac.  Two rounds per stack:

| Stack | Round | Times (ms) | Median | Worst |
| --- | --- | --- | --- | --- |
| `AppliedOdcsRuntime` (MCP server target) | 1 | 1553 1609 1645 1572 1535 1639 1536 1536 4519 6496 | 1591 | 6496 |
| `AppliedOdcsRuntime` | 2 | 1536 1638 1642 1566 1503 1537 1624 1630 1455 6383 | 1595 | 6383 |
| `AppliedOdcs` (Lambda function target) | 1 | 389 429 409 409 387 364 376 411 378 439 | 399 | 439 |
| `AppliedOdcs` | 2 | 385 338 433 286 415 303 358 377 409 340 | 368 | 433 |

The runtime stack is about four times slower at the median, and has six-second outliers.  These rounds ran on Runtime platform V1, the service default, since the stack set no `platformVersion` (a default not recorded at the time).  Platform V2 is compared below.  Calling the main stack used `../applied-odcs/.env.applied-odcs` through `uv run --env-file`, unprinted; nothing was deployed to it.

The main stack's Gateway also runs the response interceptor after a request denial: Alice `get_order` order-2002 against `AppliedOdcs` returned 403, and its response log group has one `record response` event for that call's id.  The step 4 envelope difference for the three denied calls is the recorder's alone.

### Runtime platform V2 (after step 7)

Asked after the close: whether the Runtime was on platform V2.  It was not: `get-agent-runtime` reported `platformVersion: V1`.  The stack now sets `platformVersion: agentcore.PlatformVersion.V2`.  `cdk diff` showed an in-place update of the Runtime, and `make deploy VARIANT=runtime` (205 seconds) left the ARN, and so the target's endpoint, unchanged; `get-agent-runtime` reports `V2`, `READY`, version 2, and the target stays `READY` without a resynchronization.

The eight calls, made live on V2 and compared with the recorded outcomes (not re-recorded, so `orders/tests/events/runtime/` stays the V1 recording): all eight the same.  A write still does not survive to the next call (`9 Birch Ave`, then `1 Oak Ln`).

`make latency`, interleaved with the main stack so both see the same network:

| Stack | Round | Median | Worst | Times (ms) |
| --- | --- | --- | --- | --- |
| Runtime V2 | 1 | 3148 | 3372 | 2976 3372 2969 2914 3230 2915 3266 3118 3294 3177 |
| Lambda function target | 1 | 410 | 474 | 474 410 410 353 465 410 411 410 361 457 |
| Runtime V2 | 2 | 2827 | 3883 | 2783 2720 2938 3883 3072 2867 2682 3361 2764 2787 |
| Lambda function target | 2 | 409 | 453 | 453 410 409 409 351 348 428 344 371 411 |

V2 is slower than V1 at the median (about 3.0 s against 1.6 s) and steadier (no six-second outliers; worst 3.9 s against 6.5 s).

Where the time goes, from the Runtime log streams.  On both platforms each tool call is one Runtime session, and inside it the Gateway sends three requests about 300 ms apart (`initialize`, then `notifications/initialized`, then `tools/call`), about 620 ms from the first to the tool's answer.  On V1 the server process in the session had started 24 seconds before the call arrived (a pre-warmed process), so process start is not on the call's path; the step 6 note that each call starts a server process was right about fresh memory and wrong as the cause of the latency.  The rest of the round trip, about 1 s on V1 and 2.4 s on V2, is outside what the server logs: the Gateway's interceptors (about 0.4 s in total on the main stack), the OAuth token, and the Runtime assigning a session before the first request reaches the server.  V2's extra time is in that last part or the token, not in the server.  V2 also names log streams `runtime-logs-<uuid>` where V1 used `<date>/[runtime-logs]<uuid>`.

Both platforms probe `GET /ping` about 2 s after a call and get a 404 from FastMCP, then fall back to MCP `ping` requests every 2 s for the life of the session.

### Warm-up before the V2 snapshot

Asked: whether the server does all it can before the V2 snapshot.  The AWS guide ("Optimize your agent for AgentCore Runtime V2") says the snapshot captures whatever the process does before it listens.  `server.py` already did its imports, read `orders.json`, and registered the tools at module scope.  What it left out was the first request's code paths.  `python server.py` now starts the app's session manager, posts the Gateway's requests to the app in process (`initialize`, `notifications/initialized`, `tools/list`, and one `tools/call` of each tool, the writes with an unknown `orderId` so `ORDERS` does not change), and only then starts uvicorn.  `test_server.py` checks that the warm-up calls every tool and changes no order.  On the Mac the 8 requests take 9 ms.  On V2 the warm-up ran in a `build-logs-<uuid>` stream during the snapshot build, twice 0.9 s apart (22 ms and 27 ms), and in no session stream.

The three configurations measured in one sitting, two rounds of `make latency` each (Carol `list_orders`, 10 timed calls after 2 warmups), in this order: V2 with the old server (Runtime version 2), V1 with the old server (version 3, the platform set to V1 for the run and not committed), V2 with the warm-up (version 4).  Nearest-rank percentiles, in ms:

| Configuration | Calls | Min | p50 | p75 | p90 | p95 | p99 | Max | Mean | Over 5 s |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| V1 | 20 | 1524 | 1703 | 6549 | 6557 | 6656 | 6661 | 6661 | 3834 | 9 |
| V1, two more rounds | 20 | 1490 | 1637 | 1770 | 6445 | 6497 | 6531 | 6531 | 2820 | 5 |
| V2 | 20 | 2697 | 3074 | 3235 | 3521 | 3527 | 3696 | 3696 | 3117 | 0 |
| V2 with the warm-up | 20 | 2574 | 2969 | 3175 | 3233 | 3295 | 3772 | 3772 | 2998 | 0 |

V1 has two modes, about 1.6 s and about 6.5 s, and the slow one was 9 of 20 calls right after the deploy and 5 of 20 in the two rounds after; the earlier V1 runs had 2 of 20.  V2 has one mode around 3.0 s.  The warm-up moved V2's p50 by 105 ms and its mean by 119 ms, about the spread between rounds of the same configuration.

From the session streams (`make sessions VARIANT=runtime MINUTES=<n>`, `scripts/runtime_sessions.py`: per session, the first log line to the `initialize` response, `initialize` to the tool's answer, and the `tools/call` handling):

| Configuration | Sessions | First line to `initialize` | `initialize` to answer | Tool handling |
| --- | --- | --- | --- | --- |
| V1 | 24 and 18 | 14.6 s and 12.1 s (pre-warmed processes) | 532 and 527 ms | 4 ms |
| V2 | 24 | 65 ms | 618 ms | 4 ms |
| V2 with the warm-up | 22 | 38 ms | 585 ms | 2 ms |

The warm-up saves about 2 ms of tool handling and about 30 ms between restore and `initialize`.  The server answers each request in a few milliseconds on every configuration, and the 520 to 620 ms inside the session is the Gateway's pacing of its three requests.  The rest of V2's round trip, about 2.4 s, happens before the first request reaches the server, where code in the image cannot reach it.  Each restored V2 session begins with an MCP `ping` and a uvicorn `WARNING: Invalid HTTP request received` before `initialize`, on both V2 images; V1 shows the warning in about half its sessions.  The stack stays on V2 with the warm-up.

## Defaults taken

| Step | Default | Why |
| --- | --- | --- |
| 1 | The variant is `-c variant=` with `''` or `runtime`; any other value fails synth with a message. | A typo must not synthesize `AppliedOdcs`. |
| 1 | Physical names that derive from the prefix: the user pool and the Gateway.  The target stays `orders` in both variants, because the tool names the interceptors see are `orders___<tool>`.  The Cognito group names stay `support`, `finance`, `employee`: they are scoped to the pool and are the role claims the policies read.  Log groups, functions, and roles have no physical name in the template; CloudFormation names them from the stack name, so they already differ per stack. | The plan says every physical name; these are all of them. |
| 1 | The Makefile derives `STACK`, `OUTPUTS` (`build/outputs-runtime.json` for the runtime variant), and `ENV` from `VARIANT`.  `make deploy` names the stack on the `cdk deploy` line as well. | Two variants must not share an outputs file, and `cdk deploy` with no stack name would pick whatever the app synthesizes. |
| 1 | `make demo` passes the env file to `scripts/demo.sh` as `ENV_FILE`, and the Makefile's `ENV` takes `ENV_FILE` when set, so the `make -s call` lines inside the script use it without printing it.  The demo's printed commands stay as in `docs/demo.md`. | The plan asks that the script read the env file the Makefile passes. |
| 1 | `scripts/env.py` takes the outputs file and the env file as arguments, reads the one stack in the outputs file, and copies only the outputs present, so the runtime variant can add or drop keys. | Step 3 adds outputs. |
| 1 | `make compare-baseline` is the target for the baseline check.  `make baseline` (added in step 5) regenerates `build/baseline-AppliedOdcs.template.json` from the tag's sources by `git archive`. | Every verification is a target (`CLAUDE.md`). |
| 2 | `mcp==1.30.0`, the last 1.x release (September 7, 2026).  The newest release is 2.3.0 (October 2), where `mcp.server.fastmcp` is removed and FastMCP is renamed `mcp.server.mcpserver.MCPServer`. | The plan names FastMCP, and the AgentCore Runtime MCP examples use `mcp.server.fastmcp`.  Moving to 2.x is a question for a later plan. |
| 2 | `update_order`'s `changes` is `dict[str, Any]`, so its input schema is an object with `additionalProperties: true` and no nested properties, where `tools.json` lists `shippingAddress` and `internalNotes`.  The test compares top-level properties and required lists, as the plan asks. | A typed `changes` would drop or reject keys that `handler.py` accepts, which would change behavior.  The interceptors decide which keys may be written. |
| 2 | An unknown `orderId` raises FastMCP's `ToolError` with the handler's message.  FastMCP prefixes it: `Error executing tool get_order: unknown orderId: 'order-0'`. | The plan says a tool error. |
| 2 | The server finds `orders.json` beside itself (in `build/server/`) or, in the repository, at `orders/tool/data/orders.json`. | One data source, and the in-process tests run from the repository. |
| 2 | `make server-smoke` is the target for the local HTTP check. | Every verification is a target. |
| 3 | `orders/server/Dockerfile`, copied into `build/server/` by `make server-build`: `public.ecr.aws/docker/library/python:3.12-slim` for `linux/arm64`, `pip install -r requirements.txt`, `python server.py`.  `AgentRuntimeArtifact.fromAsset` sets no platform by default, so the stack passes `Platform.LINUX_ARM64`. | K3 default; ECR Public avoids Docker Hub pull limits. |
| 3 | The credential provider is `OAuth2CredentialProvider.usingCognito` (vendor `CognitoOauth2`) with the pool's issuer and the domain's `/oauth2/authorize` and `/oauth2/token`.  The AgentCore docs show this vendor for the authorization code grant; whether it serves the client credentials grant is unverified.  If it does not, the fallback is `usingCustom` with the pool's discovery URL. | The aws-bedrockagentcore README says to prefer the vendor factory for a known provider. |
| 3 | `GrantType: CLIENT_CREDENTIALS` on the target's OAuth provider, by property override.  The L2 leaves it unset. | The M2M client has only that grant, and Delta's Ping client is the same. |
| 3 | The Runtime authorizer is `RuntimeAuthorizerConfiguration.usingCognito(users, [m2mClient])`, which renders `AllowedClients` with the M2M client and no audience or scope check. | Cognito client credentials tokens carry `client_id` and no `aud`. |
| 3 | Two outputs beyond the plan's: `M2MClientId` and `TokenEndpoint`.  `scripts/env.py` reads the client secret from Cognito with `DescribeUserPoolClient` and writes it to `.env.applied-odcs-runtime` as `M2M_CLIENT_SECRET`, never printing it. | The plan puts the M2M secret in the env file; these let a script fetch an M2M token to call the Runtime directly while debugging. |
| 3 | `make tools USER=<user>` runs `client/tools.py`, a `tools/list` through the Gateway.  `client/call.py` gains `session(user)`, the initialize half of `call`, which both use. | The step's check is a `tools/list` as Carol, and every verification is a target. |
| 6 | `make latency` times only the `tools/call` POST after one sign-in and one `initialize`, with two warmup calls, and ran two rounds per stack. | The plan asks for warm calls; sign-in and initialize are the same for both stacks. |
| 4 | `compare_live.py` reads each payload with `client/call.py`'s `payload_of`, so a wrapped list compares as its rows.  Field values are not compared, only ids and field names, as the plan says.  An `error` compares by its message as well as by status. | Values differ by the order of writes across the two stacks' histories. |
| 5 | `client/call.py`'s `payload_of` unwraps a `structuredContent` of `{"result": [list]}` too, so `make call` prints `5 rows` and the rows.  A test in `test_client.py` covers it. | The interceptor now leaves the list wrapped, as FastMCP sent it, and the client printed `1 object`. |
| 5 | `client/record.py` writes into `RECORD_DIR`, which `make record` sets to `orders/tests/events/runtime` for the runtime variant.  After a 403 it waits up to 20 seconds for a response event before saving `response: null`. | A 403 from the response interceptor (a withheld result) has a response event worth keeping; one from the request interceptor has none. |
| 3 | The resource server identifier is `orders` and the scope is `orders/invoke`. | The plan names the resource server `orders` with one scope. |

## Fallbacks

| Step | Fallback | What failed |
| --- | --- | --- |
| 3, 5 | K2's: the cedar-odcs fix in v0.2.5, run before step 4. | v0.2.4 withheld every `list_orders` through the MCP server target: `response withheld; it could not be filtered: list tool returned no list`. |

## Known unknowns

| | Observed |
| --- | --- |
| K1 | aws-cdk-lib 2.273.0 has L2 classes for all of it.  Runtime: `Runtime` with `agentRuntimeArtifact: AgentRuntimeArtifact.fromAsset(dir, DockerImageAssetOptions)` (also `fromCodeAsset`, `fromS3`, `fromEcrRepository`, `fromImageUri`), `protocolConfiguration: ProtocolType.MCP`, `authorizerConfiguration: RuntimeAuthorizerConfiguration.usingJWT(discoveryUrl, allowedClients, ...)` or `.usingCognito(userPool, clients, ...)`; `runtime.applicationLogGroup` is `/aws/bedrock-agentcore/runtimes/<id>-DEFAULT`, created on the first invocation.  Target: `Gateway.addMcpServerTarget(id, {gatewayTargetName, endpoint, credentialProviderConfigurations})`.  Outbound OAuth: `GatewayCredentialProvider.fromOauthIdentity(provider, {scopes})` or `.fromOauthIdentityArn({providerArn, secretArn, scopes})`.  Credential provider: `OAuth2CredentialProvider.usingCognito`, `.usingPingOne`, `.usingCustom({discoveryUrl})`, and other vendors, over `CfnOAuth2CredentialProvider`.  The target's L1 has an optional `GrantType` that the L2 does not set. |
| K2 | Wrapped.  FastMCP 1.30.0 puts a list result in `structuredContent` as `{"result": [...]}` (step 2 table).  Run locally through v0.2.4's response handler, a Carol `list_orders` response event with that result is withheld: `response withheld; it could not be filtered: list tool returned no list`.  Whether the Gateway passes `structuredContent` through to the interceptor for an MCP server target is for step 3 to see live. |
| K3 | Docker is installed (`/opt/homebrew/bin/docker`) and the daemon answers `docker info`; Finch is not installed.  Default taken: a container image from `build/server/`. |
| K4 | The envelope matches the Lambda function target's: the same keys at every level, a parsed `body`, `isStreamingResponse: false`, empty response headers.  The result inside differs (`structuredContent` present and wrapped for a list, one text item per row).  Not streamed. |
| K5 | OAuth works.  The Gateway reaches the Runtime with client credentials from the Cognito M2M client, through the `CognitoOauth2` credential provider, both for the target's tool synchronization and for each `tools/call`.  The `usingCustom` fallback was not needed.  The Gateway also offers IAM outbound to an MCP server target in this version, `GatewayCredentialProvider.fromIamRole({service, region})`, which the README says the service accepts only for MCP server and OpenAPI targets.  Noted; the stack stays on OAuth to match Delta. |
| K6 | Not exercised: the server did not change after the target was created.  The target synchronized on creation (`lastSynchronizedAt` 22:19:44 UTC), and the second deploy, which changed only the interceptors, did not touch it.  The control-plane call exists (`SynchronizeGatewayTargets`, which the aws-bedrockagentcore README names and `GatewayTarget.grantSync` grants) but was not run. |
| K7 | Writes do not survive.  Each tool call lands in a new Runtime session with a fresh server process (step 6). |

## Findings

- The first cedar-odcs attempt broke `test_agreement` twice without changing a decision.  It calls the private `handlers._result_payload(result)` with one argument, so the new argument got a default.  It also replays every file in `usecases/orders/tests/events/` with the use case's own claims mapping and no knowledge of wrapped lists, so the runtime fixtures live in `mcp-server-events/` beside it.  Neither needed an existing test to change, so the stop condition did not apply.
- The step 1 baseline was synthesized while the SSO token had expired.  With no account, CDK writes `${AWS::AccountId}` and `Fn::Sub` asset bucket names; with credentials it writes `009080466601`.  After `aws sso login`, `make compare-baseline` reported eight differences, all of that kind, and none from the code.  Commit `20cabe2` was made with that comparison failing, because `| tail -1` hid the target's exit status in the command that ran it.  The baseline was then synthesized again from the tag (`make baseline`, `git archive demo-lambda-target`) with credentials, and `make compare-baseline` reports the templates identical.  No code changed between the failing and the passing comparison.  Step 1's comparison, which passed with no credentials on both sides, still holds.
- The Gateway serves the output schemas it synced from the server, so `tools/list` through the runtime stack shows FastMCP's schemas (an object with `additionalProperties: true`, and `{"result": array}` for `list_orders`), not `orders/tools.json`.  The cedar-odcs tool schema gate in `make check` still reads `tools.json`, which the runtime stack no longer serves.  A question for the bundle loader plan.

## Live comparison

`make compare-live`, each runtime recording (`orders/tests/events/runtime/`, MCP server target, cedar-odcs v0.2.5) against the Lambda function target recording of the same name (`orders/tests/events/`, v0.2.4 era):

| Call | Lambda function target | Runtime | Same |
| --- | --- | --- | --- |
| Alice `get_order` order-2002 | 403 `ReadOrder is not permitted for this caller` | 403, same message | yes |
| Alice `list_orders` | 200, order-1001 and order-3003, seven fields each | 200, same ids and fields | yes |
| Alice `refund_order` order-1001 | 403 `RefundOrder is not permitted for this caller` | 403, same message | yes |
| Alice `update_order` order-1001 `internalNotes` | 403 `UpdateOrder rejected; fields not permitted: internalNotes` | 403, same message | yes |
| Alice `update_order` order-1001 `shippingAddress` | 200, order-1001 with seven fields | 200, same | yes |
| Carol `list_orders` | 200, five orders, six fields each | 200, same ids and fields | yes |
| Dave `list_orders` | 200, no rows | 200, no rows | yes |
| Dave `refund_order` order-1001 | 200, an empty object | 200, an empty object | yes |

Envelope findings, printed by `compare_live.py` and not failing it:

- Every result from the MCP server target carries `structuredContent` (from the target, and still at the caller after the response interceptor); the Lambda function target's results carry none.  For a list it is `{"result": [...]}`.
- From the target, a list arrives as one text item per row (five for the full list); the Lambda function target sends one text item holding the list.  The response interceptor writes one text item either way.
- The request event and the response event have the same key paths in both, apart from `structuredContent` inside the result.  `isStreamingResponse` is `false` in every runtime response event.
- The three request-denied calls (Alice `get_order`, `refund_order`, the `internalNotes` update) have a response event in the runtime recordings and none in the Lambda function target recordings.  The difference is the recorder: before step 5, `client/record.py` did not look for a response event after a 403.  The runtime events show the Gateway runs the response interceptor on the request interceptor's short-circuit, with the JSON-RPC error as the body, and v0.2.5 passes it through.  The Lambda function target stack does the same (step 6), so this difference is the recorder's alone.

## Secrets

The runtime stack's demo password and the M2M client secret are in `.env.applied-odcs-runtime` at the worktree root, ignored by git, mode 600.  `.claude/settings.json` denies reading it.

## Open questions for the bundle loader plan

- **A Runtime session per tool call.**  The Gateway opens a new Runtime session for every `tools/call`, with its own server process and memory, and sends three sequential requests into it.  That costs about 1.2 s per call against the Lambda function target on platform V1 and about 2.5 s on V2, and makes in-memory state useless, so production gap 0.1 (records in a deployed store) is required, not optional.  Open: whether the Gateway can reuse a Runtime session or skip the per-call `initialize`, which platform Delta's Runtimes use, and why V2 is slower here when its description promises fast starts.
- **Output schemas the Gateway serves.**  An MCP server target's tool schemas come from the server's `tools/list`, so callers see FastMCP's schemas (`additionalProperties: true` objects, and `{"result": array}` for the list), not `orders/tools.json`.  The cedar-odcs tool schema gate still checks `tools.json`.  The bundle could have the server declare the contract's output schema (typed return models generated from the contract), or the gate could read the server's `tools/list`.
- **The `{"result": [...]}` wrapping.**  v0.2.5 unwraps it for a list tool.  A server that returns a list some other way (no structured output, text items only) would still be withheld, since only the first text item is read.  The bundle should fix the server's result shape, and cedar-odcs should have a test per supported shape.
- **mcp 2.x.**  The server is on mcp 1.30.0 because 2.x renamed FastMCP to `MCPServer`.  The bundle should pick one, and the Runtime examples it follows.
- **Resynchronizing tools (K6).**  A change to the server's tools needs `SynchronizeGatewayTargets` or a target update.  Redeploying the Runtime image alone leaves the Gateway's catalog stale.  Not exercised here.
- **The Token Vault secret grant.**  The Gateway role may read any `bedrock-agentcore-identity!*` secret in the account, because the credential provider's secret ARN is a deploy-time token.  The Delta construct's grant should be compared.
- **The credential provider vendor.**  `CognitoOauth2` served the client credentials grant, though the AgentCore docs show it only for the authorization code grant.  Delta uses Ping, which maps to `OAuth2CredentialProvider.usingPingOne` or `usingCustom`; that mapping is unverified.
