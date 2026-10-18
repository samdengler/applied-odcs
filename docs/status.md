# Overnight status

The run of `docs/plan.md`, Work order steps 1 to 12, on October 17 and 18, 2026.  Each entry says what the plan asked, what was done, and what was observed.

## Commits and tags

cedar-odcs, on `main`, pushed to github.com/samdengler/cedar-odcs, each tag after `./check.sh` was green:

| Commit | Tag | Change |
| --- | --- | --- |
| `01cab76` | | Claims mapping on the descriptor (step 1) |
| `95534dc` | `v0.2.0` | `CEDAR_ODCS_RECORD` switch |
| `c607d9f` | `v0.2.1` | `check --skip pull --skip prove`, `CEDAR_ODCS_ANALYSIS` |
| `d08b0c4` | `v0.2.2` | Interceptor responses carry only `statusCode`, `headers`, `body` (the live Gateway fix) |
| `b132bf8` | `v0.2.3` | Role grants rendered to policies (step 10) |
| `2b5ecad` | `v0.2.4` | Tool schema gate (step 11) |

Each change has a closed Beads issue in cedar-odcs.

applied-odcs, on `main`, pushed to the new private repository github.com/samdengler/applied-odcs: eleven commits, `b84dd30` (skeleton) to `c7e1531` (close), one per Work order step except step 12's status-only fix that follows.  The sample pins cedar-odcs `v0.2.4`, and the deployed stack was built from that tag.

## What is deployed

Stack `AppliedOdcs` in account 009080466601 (the default profile's SSO account), us-east-1, from plain aws-cdk-lib 2.273.0 and aws-cdk 2.1145.0.  Last deployed at step 12 from the final commit: interceptors on cedar-odcs v0.2.4, field policies from `grants.yaml`, `CEDAR_ODCS_RECORD` on.  The account was already bootstrapped (`CDKToolkit`, bootstrap version 32).

| Output | Value |
| --- | --- |
| GatewayUrl | `https://applied-odcs-qfff07owsu.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp` |
| GatewayId | `applied-odcs-qfff07owsu` (status `READY`) |
| UserPoolId | `us-east-1_t89ljprDM` |
| ClientId | `2tbbt4giajvkmb3bg2mhmcom89` |
| Region | `us-east-1` |

Resources: one Cognito user pool with the app client and the groups `support`, `finance`, `employee`; the `OrdersTool` Lambda; the `RequestInterceptor` and `ResponseInterceptor` Lambdas (Python 3.12, arm64, 512 MB, the cedar-odcs bundle); the Gateway in MCP mode with the Cognito JWT authorizer, `exceptionLevel: DEBUG`, both interceptors with `passRequestHeaders: true`; the `orders` Lambda target with `orders/tools.json`; three log groups with one-week retention.

Users: `alice` (no groups), `carol` (`support`, `employee`), `dave` (`finance`, `employee`), created by `make users`, permanent passwords.

The demo password is in `.env.applied-odcs` at the repository root, under `APPLIED_ODCS_PASSWORD`.  The file is ignored by git, mode 600, and also holds the stack outputs.  `scripts/env.py` generated the password on the first deploy and keeps it across deploys.  `.env.applied-odcs.example` lists the names.

Teardown, not run: `cd infra && npx cdk destroy AppliedOdcs`.  The user pool and log groups have `RemovalPolicy.DESTROY`, so nothing is left behind.

## What passed

- Step 1: cedar-odcs `./check.sh` green before every tag, v0.2.0 to v0.2.4 (731 tests at v0.2.4, every use case's check, 211 history proofs).
- Step 2: `uv run cedar-odcs --help` from the sample.
- Step 3: the copied corpus, 75 cases, unchanged; the interceptor tests on every regenerated event; the carol-for-alice `dry-run` prints order-1001 and order-3003 with seven fields each.
- Step 4: `test_tool.py`, `list_orders` returns five rows with all nine fields.
- Step 5: `make bundle`; the Linux arm64 cedarpy wheel is in `build/lambda/cedarpy/`, and `lambda/smoke.py` runs the bundle's own response handler on a fixture with the Mac's cedarpy standing in.
- Step 6: `make synth`; `scripts/check_synth.py` asserts one Gateway, REQUEST and RESPONSE interceptors with `PassRequestHeaders: true`, target `orders`, one user pool.
- Step 7: `make deploy`, `make users`; `get-gateway` shows `READY`; `make token USER=alice` decodes with `username: alice`.
- Step 8: the six live calls below, recorded; `make check` passes with them (121 tests).
- Step 9: `make demo` runs `docs/demo.md` end to end against the Gateway.
- Step 10: cedar-odcs v0.2.3 renders `grants.yaml` to the field policies; its test shows the rendered text equals the four hand-written orders policies.  The sample carries `orders/contract/grants.yaml` and its `policies.cedar` no longer has P4, P5, P6, P11 (nine policies kept).  `make check` passes with the corpus unchanged (75 cases), `make prove` gives the same 25 proved and 12 non-vacuous guardrails as the hand-written orders, and after `make deploy` the three list calls return what step 8 recorded (Alice two rows with seven fields, Carol five rows with six, Dave none).  The 03:00 fallback was not needed.
- Step 11: cedar-odcs v0.2.4 adds `cedar-odcs tools DIR` and runs it in `check` after build when `tools.json` is beside `usecase.py`.  With the sample's `tools.json` it prints `every outputSchema in tools.json names the contract's leaves`.  With `cardLast4` dropped from `list_orders`'s output schema, `make check` stopped at the gate:

  ```
  == tools ==
  orders___list_orders: outputSchema and the contract differ
    in outputSchema, not in the contract: (none)
    in the contract, not in outputSchema: cardLast4

  build: ok
  tools: failed
  ```

  `tools.json` was restored from a copy (`git diff` empty) and `make check` passed again.
- Step 12: at the closing commits, `make check` (121 tests, every step ok, pull and prove skipped by design) and `make synth` pass here, `./check.sh` passes in cedar-odcs (731 tests, 25 orders proofs, 211 history proofs), the stack was redeployed from the final commit and answers (`alice list_orders` 2 rows, `carol list_orders` 5 rows, `alice refund_order` 403), and `git status` is clean in both repositories.  `make prove` passed at step 10.  `cdk destroy` was not run.

## Defaults taken

- **cedar-odcs venv and analysis build.**  The cedar-odcs checkout's `.venv` and `analysis/target` were built when the repository was named `cedar-osdc`; `pytest` had a stale shebang and the prover looked for cvc5 under the old path.  Both were rebuilt locally (ignored paths, nothing committed).  `./check.sh` was green before any change: 712 tests, 211 history proofs.
- **Record switch in v0.2.0.**  The plan puts `CEDAR_ODCS_RECORD` in Build and check but not in a Work order step.  It landed in cedar-odcs before the `v0.2.0` tag, as its own commit, so the first bundle carries it.  The Lambda entry point sets the `cedar-odcs` logger to INFO (DEBUG with the switch), since the Lambda runtime's root logger does not show INFO from a library logger otherwise.
- **`check` from an installed cedar-odcs (v0.2.1).**  `cedar-odcs check orders` from the sample ran `pull`, which rewrites `contract/order.odcs.yaml` from `contract/unity/`, and then `prove`, which failed because an installed package has no `analysis/` crate beside it.  cedar-odcs `v0.2.1` adds `check --skip pull --skip prove` and `CEDAR_ODCS_ANALYSIS`.  The sample's `make check` skips both: its contract is the source (decision 11), and `make prove` points `CEDAR_ODCS_ANALYSIS` at `../cedar-odcs/analysis`.  `PULL` stays in `usecase.py` so `cedar-odcs pull orders` still shows the catalog path.  Because of this tag and the v0.2.2 fix below, the grants work is tagged `v0.2.3` and the tool-schema gate `v0.2.4` (the plan said `v0.2.1` and `v0.2.2`).
- **Copied tests that could not stay unchanged.**  `test_interceptor.py` and `test_corpus.py` import `orders.usecase` (they imported `usecases.orders.usecase`).  `test_policies_and_entities_are_the_proven_ones` was removed from `test_interceptor.py`: it compares against cedar-odcs's `history/`, which is not here.  `test_build.py` was rewritten: the cedar-odcs version compares committed generated files and the history chain, and here nothing generated is committed.  It now checks that build writes the schema, maps, and entities, and that every one of the nine leaves has a known level and a writer.  The corpus (`tests/test-cases/`) is unchanged and passes: 75 cases.
- **Build before tests.**  A root `conftest.py` builds `orders/contract/generated/` and `orders/entities.json` from the contract before any test loads the use case, so `uv run pytest` works on a fresh clone.
- **Identity files.**  Carol's identity carries `cognito:groups: [support]` and Dave's `[finance]`, as the plan's Identities and events section says; the live pool also puts both in `employee`.  UUIDs and the client id in the fixtures are made up.
- **Bundling a local cedar-odcs.**  `lambda/bundle.sh` takes `CEDAR_ODCS_SOURCE` in place of the pinned git URL, so a fix can be tried on the live Gateway before it is tagged.  It must be a wheel (`uv build --wheel` in the checkout), since the install is `--only-binary :all:`.  Used once, for the v0.2.2 fix; every deploy after it came from the tag through `make deploy`.
- **Client scripts run with `python -P`.**  The plan names `client/token.py`, which shadows the standard library `token` module when the script's directory is on `sys.path`; `-P` leaves it off.  `call.py` and `record.py` load their siblings by path.
- **Record switch on in the deployed stack.**  `CEDAR_ODCS_RECORD=1` is set on both interceptors so `make record` works; `cdk deploy -c record=false` turns it off.  The logs keep a week and hold bearer tokens while it is on.
- **Recorded fixtures are redacted.**  `client/record.py` replaces each bearer token's signature with `signature-redacted` and the `X-Forwarded-For` address with `203.0.113.10`.  The token payloads (Cognito UUIDs, the pool issuer, the app client id) are kept; none is a secret.
- **Each live fixture holds both events and what the client saw.**  `live-<user>-<tool>[-<orderId>].json` carries the request event, the response event (null when the request leg refused), and the observed status and JSON-RPC body.  `test_live_recording_matches_the_local_handlers` in `test_interceptor.py` runs the local handlers on the recorded events and asserts they decide what the live Gateway returned.

- **Grants reach the prover.**  The plan's step 10 lists build, `UseCase.policies`, `validate`, and `share`.  The corpus runner, `run-tests`, and the Rust `prove` read `policies.cedar` by path too; all of them now append `contract/generated/grants.cedar`, so the guardrails are proved against the same text the engine decides with.  `build` takes the descriptor's field verbs and defaults to `Read<Entity>Field` and `Update<Entity>Field`.
- **The gate checks every object and list tool.**  The plan says "for every tool whose `returns` is `object` or `list`"; all five orders tools qualify.  A governed tool with no entry or no `outputSchema` in `tools.json` fails too, with every leaf listed as missing.  Paths are spelled as the field round spells them (`a.b`, `a[].b`), and a list tool's top-level array is the paths of its items.
- **Demo step 8 changed.**  The plan's step 8 edits the contract and runs `make check` then `make deploy`.  The edit fails two corpus cases ("owner reads cardLast4 of own order", "support agent may not read cardLast4"), so `make check` fails and `make deploy` stops.  `docs/demo.md` shows the edit's effect with `dry-run` and the gate catching it, and says which two cases to update (checked: with them updated the corpus passes) for anyone who wants to deploy the change live.  `make demo` does the edit on a copy under `build/demo/`.

## Findings against the plan

- **Dave reads nothing.**  The plan expects Dave's `list_orders` to return every row with the five public fields, and his refund to echo public fields.  Under the unchanged policies no permit gives finance `ReadOrder` or `ReadOrderField`, and the guardrail `refund-implies-no-read` proves it.  `dry-run` with `dave.json` drops all three rows (`read denied`) and returns `[]`; the copied `test_finance_list_is_empty` and `test_write_tools_echoing_the_order_are_filtered` pin the same.  The policies were not changed.
- **Carol sees six fields.**  The plan says seven for Carol.  Public is five (`id`, `owner`, `status`, `total`, `estimatedDelivery`) and internal is one (`internalNotes`), so Carol gets six on every row.  Alice gets seven (five public, two confidential).
- **The Gateway rejected the interceptor's pass-through response (fixed in cedar-odcs v0.2.2).**  The first live call, and every method after it (`initialize`, `tools/list`, `tools/call`), returned `InterceptorException - Received invalid response from interceptor` with HTTP 500, while the logs showed the handlers deciding correctly.  The live response event's `gatewayResponse` carries `path`, `httpMethod`, `headers` (empty), `body`, `statusCode`, and `isStreamingResponse`; the handler echoed all of it back as `transformedGatewayResponse`.  The fixtures written from the documentation had only `statusCode`, `headers`, and `body`, so the tests never saw it.  cedar-odcs v0.2.2 returns only those three fields (and drops empty ones); with that bundle every call succeeds.  This is the plan's "Gateway event shape differs" risk, taken through its named fallback: adjust `handlers.py`, tag, rebundle.
- **Alice's `get_order` on Bob's order is a 403, not an empty object.**  The plan expected `{}` from the response leg.  The use case's `entities.json` (built from `facts.json`) knows `order-2002` is Bob's, so the request leg's verb round denies `ReadOrder` before the tool runs: `ReadOrder is not permitted for this caller`.  Local `dry-run` with `alice.json` gives the same rejection, so this is the plan's expectation, not a live/local difference.
- **No live result differed from the local handlers.**  Each of the six live fixtures is replayed through the local handlers by `make check` and matches.

## Live calls (step 8)

All against the deployed Gateway, recorded to `orders/tests/events/live-*.json`.

| Call | Status | What came back |
| --- | --- | --- |
| `alice list_orders` | 200 | order-1001, order-3003; seven fields (`id`, `owner`, `status`, `total`, `shippingAddress`, `cardLast4`, `estimatedDelivery`) |
| `carol list_orders` | 200 | all five orders; six fields (`id`, `owner`, `status`, `total`, `internalNotes`, `estimatedDelivery`) |
| `dave list_orders` | 200 | `[]` |
| `alice get_order order-2002` | 403 | `ReadOrder is not permitted for this caller` |
| `dave refund_order order-1001` | 200 | `{}`: the refund ran upstream and finance reads no field of the order |
| `alice refund_order order-1001` | 403 | `RefundOrder is not permitted for this caller` |

Dave's refund changes order-1001's `status` to `refunded` in the tool Lambda's memory until its next cold start; later calls show it.

## Unverified items

- **Tool name key in the Lambda context: confirmed.**  The tool Lambda logged `client_context {"bedrockAgentCoreTargetId": "0P9J5FNKGW", "bedrockAgentCoreGatewayId": "applied-odcs-qfff07owsu", "bedrockAgentCoreMessageVersion": "1.0", "bedrockAgentCoreMcpMessageId": "899640888", "bedrockAgentCoreAwsRequestId": "...", "bedrockAgentCoreToolName": "orders___list_orders"}`.  The key is `bedrockAgentCoreToolName` and its value carries the target prefix.
- **`passRequestHeaders` on the RESPONSE interceptor: confirmed.**  `LambdaInterceptor.forResponse(fn, { passRequestHeaders: true })` exists in aws-cdk-lib 2.273.0, synthesizes `InputConfiguration.PassRequestHeaders: true`, `get-gateway` shows it on both points, and the response interceptor's event carries `mcp.gatewayRequest.headers.Authorization`.  No L1 override or claims-header fallback was needed.
- **Gateway event shape: differs from the fixtures in four ways.**  (1) `gatewayResponse` has `path`, `httpMethod`, and `isStreamingResponse: false` beside `statusCode`, `headers`, and `body`; returning them broke every call (above).  (2) `gatewayRequest` has `"context": null`.  (3) The request interceptor's event has `"gatewayResponse": null` rather than no key.  (4) `gatewayRequest.headers` carries the full forwarded set (`X-Forwarded-For`, `X-Amzn-Trace-Id`, `x-amzn-tls-*`, `Host`, `Content-Length`), and `gatewayResponse.headers` is `{}`.  Bodies are parsed objects in both events, and the tool result arrives as `{"isError": false, "content": [{"type": "text", "text": "<the tool's JSON>"}]}` with no `structuredContent`, even though `tools.json` declares an `outputSchema`.  `tools/list` from the Gateway does not echo `outputSchema`.
- **Cognito access token claims: confirmed.**  Alice's token decodes with `username: alice`, `client_id` equal to the app client, a UUID `sub`, and no `cognito:groups`; Carol's and Dave's carry `cognito:groups`.  The ID-token fallback was not needed.
- **cedarpy Linux wheel: confirmed.**  `uv pip install --python-platform aarch64-manylinux2014` installed `cedarpy-4.12.2` with `_internal.cpython-312-aarch64-linux-gnu.so`; the ARM_64 functions import it (cold start init 172 to 192 ms, first decision 139 to 193 ms).
- **Cognito authorizer: worked.**  `GatewayAuthorizer.usingCognito` deployed on the first try; `usingCustomJwt` was not needed.
- **Interceptors in us-east-1: available.**  No `CREATE_FAILED`.
