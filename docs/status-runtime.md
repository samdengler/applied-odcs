# Runtime port status

The run of `docs/plan-runtime.md` on branch `runtime-mcp`, in the worktree at `~/src/github.com/samdengler/applied-odcs-runtime`, started October 18, 2026 from tag `demo-lambda-target` (`e8126a9`).  Each entry says what the plan asked, what was done, and what was observed.

## Steps

| Step | State | Commit |
| --- | --- | --- |
| 1. Variant switch and baseline | done | see `git log` |
| 2. Orders MCP server | | |
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

## Defaults taken

| Step | Default | Why |
| --- | --- | --- |
| 1 | The variant is `-c variant=` with `''` or `runtime`; any other value fails synth with a message. | A typo must not synthesize `AppliedOdcs`. |
| 1 | Physical names that derive from the prefix: the user pool and the Gateway.  The target stays `orders` in both variants, because the tool names the interceptors see are `orders___<tool>`.  The Cognito group names stay `support`, `finance`, `employee`: they are scoped to the pool and are the role claims the policies read.  Log groups, functions, and roles have no physical name in the template; CloudFormation names them from the stack name, so they already differ per stack. | The plan says every physical name; these are all of them. |
| 1 | The Makefile derives `STACK`, `OUTPUTS` (`build/outputs-runtime.json` for the runtime variant), and `ENV` from `VARIANT`.  `make deploy` names the stack on the `cdk deploy` line as well. | Two variants must not share an outputs file, and `cdk deploy` with no stack name would pick whatever the app synthesizes. |
| 1 | `make demo` passes the env file to `scripts/demo.sh` as `ENV_FILE`, and the Makefile's `ENV` takes `ENV_FILE` when set, so the `make -s call` lines inside the script use it without printing it.  The demo's printed commands stay as in `docs/demo.md`. | The plan asks that the script read the env file the Makefile passes. |
| 1 | `scripts/env.py` takes the outputs file and the env file as arguments, reads the one stack in the outputs file, and copies only the outputs present, so the runtime variant can add or drop keys. | Step 3 adds outputs. |
| 1 | `make compare-baseline` is the target for the baseline check.  It needs `build/baseline-AppliedOdcs.template.json`, which is regenerated only by checking out the tag and running `make synth`. | Every verification is a target (`CLAUDE.md`). |

## Fallbacks

None yet.

## Known unknowns

| | Observed |
| --- | --- |
| K1 | |
| K2 | |
| K3 | |
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
