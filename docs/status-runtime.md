# Runtime port status

The run of `docs/plan-runtime.md` on branch `runtime-mcp`, in the worktree at `~/src/github.com/samdengler/applied-odcs-runtime`, started October 18, 2026 from tag `demo-lambda-target` (`e8126a9`).  Each entry says what the plan asked, what was done, and what was observed.

## Steps

| Step | State | Commit |
| --- | --- | --- |
| 1. Variant switch and baseline | done | see `git log` |
| 2. Orders MCP server | done | see `git log` |
| 3. Runtime, M2M client, and MCP server target | done, after step 5 | see `git log` |
| 4. Live calls and comparison | done on v0.2.5: eight of eight outcomes match | see `git log` |
| 5. cedar-odcs fix | done: v0.2.5, run before step 4 | cedar-odcs `63bdc08`, tag `v0.2.5` |
| 6. Demo, writes, and latency | | |
| 7. Close | | |

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
| K6 | |
| K7 | |

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
- The three request-denied calls (Alice `get_order`, `refund_order`, the `internalNotes` update) have a response event in the runtime recordings and none in the Lambda function target recordings.  The difference is the recorder: before step 5, `client/record.py` did not look for a response event after a 403.  The runtime events show the Gateway runs the response interceptor on the request interceptor's short-circuit, with the JSON-RPC error as the body, and v0.2.5 passes it through.  Whether the Lambda function target stack does the same is checked in step 6.

## Secrets

The runtime stack's demo password and the M2M client secret are in `.env.applied-odcs-runtime` at the worktree root, ignored by git, mode 600.  `.claude/settings.json` denies reading it.
