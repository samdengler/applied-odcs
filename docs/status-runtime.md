# Runtime port status

The run of `docs/plan-runtime.md` on branch `runtime-mcp`, in the worktree at `~/src/github.com/samdengler/applied-odcs-runtime`, started October 18, 2026 from tag `demo-lambda-target` (`e8126a9`).  Each entry says what the plan asked, what was done, and what was observed.

## Steps

| Step | State | Commit |
| --- | --- | --- |
| 1. Variant switch and baseline | done | see `git log` |
| 2. Orders MCP server | done | see `git log` |
| 3. Runtime, M2M client, and MCP server target | | |
| 4. Live calls and comparison | | |
| 5. cedar-odcs fix | | |
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

## Defaults taken

| Step | Default | Why |
| --- | --- | --- |
| 1 | The variant is `-c variant=` with `''` or `runtime`; any other value fails synth with a message. | A typo must not synthesize `AppliedOdcs`. |
| 1 | Physical names that derive from the prefix: the user pool and the Gateway.  The target stays `orders` in both variants, because the tool names the interceptors see are `orders___<tool>`.  The Cognito group names stay `support`, `finance`, `employee`: they are scoped to the pool and are the role claims the policies read.  Log groups, functions, and roles have no physical name in the template; CloudFormation names them from the stack name, so they already differ per stack. | The plan says every physical name; these are all of them. |
| 1 | The Makefile derives `STACK`, `OUTPUTS` (`build/outputs-runtime.json` for the runtime variant), and `ENV` from `VARIANT`.  `make deploy` names the stack on the `cdk deploy` line as well. | Two variants must not share an outputs file, and `cdk deploy` with no stack name would pick whatever the app synthesizes. |
| 1 | `make demo` passes the env file to `scripts/demo.sh` as `ENV_FILE`, and the Makefile's `ENV` takes `ENV_FILE` when set, so the `make -s call` lines inside the script use it without printing it.  The demo's printed commands stay as in `docs/demo.md`. | The plan asks that the script read the env file the Makefile passes. |
| 1 | `scripts/env.py` takes the outputs file and the env file as arguments, reads the one stack in the outputs file, and copies only the outputs present, so the runtime variant can add or drop keys. | Step 3 adds outputs. |
| 2 | `mcp==1.30.0`, the last 1.x release (September 7, 2026).  The newest release is 2.3.0 (October 2), where `mcp.server.fastmcp` is removed and FastMCP is renamed `mcp.server.mcpserver.MCPServer`. | The plan names FastMCP, and the AgentCore Runtime MCP examples use `mcp.server.fastmcp`.  Moving to 2.x is a question for a later plan. |
| 2 | `update_order`'s `changes` is `dict[str, Any]`, so its input schema is an object with `additionalProperties: true` and no nested properties, where `tools.json` lists `shippingAddress` and `internalNotes`.  The test compares top-level properties and required lists, as the plan asks. | A typed `changes` would drop or reject keys that `handler.py` accepts, which would change behavior.  The interceptors decide which keys may be written. |
| 2 | An unknown `orderId` raises FastMCP's `ToolError` with the handler's message.  FastMCP prefixes it: `Error executing tool get_order: unknown orderId: 'order-0'`. | The plan says a tool error. |
| 2 | The server finds `orders.json` beside itself (in `build/server/`) or, in the repository, at `orders/tool/data/orders.json`. | One data source, and the in-process tests run from the repository. |
| 2 | `make server-smoke` is the target for the local HTTP check. | Every verification is a target. |
| 1 | `make compare-baseline` is the target for the baseline check.  It needs `build/baseline-AppliedOdcs.template.json`, which is regenerated only by checking out the tag and running `make synth`. | Every verification is a target (`CLAUDE.md`). |

## Fallbacks

None yet.

## Known unknowns

| | Observed |
| --- | --- |
| K1 | |
| K2 | Wrapped.  FastMCP 1.30.0 puts a list result in `structuredContent` as `{"result": [...]}` (step 2 table).  Run locally through v0.2.4's response handler, a Carol `list_orders` response event with that result is withheld: `response withheld; it could not be filtered: list tool returned no list`.  Whether the Gateway passes `structuredContent` through to the interceptor for an MCP server target is for step 3 to see live. |
| K3 | Docker is installed (`/opt/homebrew/bin/docker`) and the daemon answers `docker info`; Finch is not installed.  Default taken: a container image from `build/server/`. |
| K4 | |
| K5 | |
| K6 | |
| K7 | |

## Findings

None yet.

## Live comparison

Step 4 fills this in: each of the eight runtime recordings against its Lambda function target recording.

## Secrets

The runtime stack's demo password and the M2M client secret are in `.env.applied-odcs-runtime` at the worktree root, ignored by git, mode 600.  `.claude/settings.json` denies reading it.
