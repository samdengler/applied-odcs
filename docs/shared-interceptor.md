# Shared interceptor and policy files in S3

The `shared-interceptor` branch, October 29, 2026.  The binding of MCP
tools to the ODCS contract moves to the agentic registry, so the
interceptor Lambda no longer carries a use case.  One function serves
every Gateway target and decides each call from the policy file the
registry publishes for that target.  The demonstration is use case 1 of
the doc "Writes the Gateway decides from the request": an employee
changes their own address.

On October 30 `hr/` was cut down to one rule, an employee sees their
own profile and changes their own address, so the example shows the
interceptor and the policy file and little else.  Its two tools are
named for a business intent, `get_profile` and `update_address`, and
each returns its own model of the contract, `Employee` and
`AddressChange`.  The larger HR use case is on branch `hr-full`.  The
live results below are from this version unless they say October 29.

## What changed from the orders demo

| Area | orders demo, tag `demo-lambda-target` | shared interceptor |
| --- | --- | --- |
| Engine | cedar-odcs v0.2.4 | cedar-odcs v0.2.6, tagged at `6c9db2b` after `./check.sh` passed (873 tests, every use case's check, 212 history proofs) |
| Governed tool | `orders/` | `hr/`, cut down from cedar-odcs `usecases/hr` to two intent tools, two models, seven policies, and two employees |
| Interceptor code | cedar-odcs plus `orders/` and its generated files, loaded from `/var/task/orders` | cedar-odcs plus `interceptor/`, no use case |
| Policies reach the Lambda | in the deployment package | `s3://<PolicyBucket>/hr.json`, read on first use and rechecked every 60 seconds |
| Results | every tool returns the one record type | each tool returns its own model, filtered by the cedar-odcs handlers built for that model |
| Stack | `AppliedOdcs` | `AppliedOdcsShared`, every physical name `applied-odcs-shared` |

## The policy file

One JSON document per Gateway target, written by `scripts/publish.py`
from the use case folder after `cedar-odcs build`.  It holds what the
engine cannot decide without, and nothing that belongs to the token, the
response, or the Gateway.

| Part | What reads it |
| --- | --- |
| `policies` | Every decision.  The Cedar text, with the rendered grants when a use case has them. |
| `tools` | The tool table: which action a tool call asks, which argument names the employee, which go into `context.input`, which is the payload and which contract field it writes, whether the result is an object or a list, and which model it is.  This is the registry's binding. |
| `resource` | The model a call names on the request leg: `Employee`, so a call is about `Employee::"alice"`. |
| `models` | For each model a tool returns, how a result becomes a Cedar entity: its id field and the fields that become attributes.  The interceptor builds one set of cedar-odcs handlers per model. |
| `entities` | The `Contract` entities, two per model (each field's level and writer, which the field policies look up with `getTag`), and the `Role` hierarchy when a target's policies read roles.  HR's read none. |

The file is format 2.  The interceptor still reads format 1, one model
for every tool, as format 2 with a single model.  `publish.py` checks
the binding before it writes: each model is a schema object of the
contract, each tool's `outputSchema` in `tools.json` names exactly its
model's fields, and a payload names exactly the lines of the field it
writes.  That replaces cedar-odcs's tools gate, which requires every
tool to return the whole `Employee` record.

Left out, and where each comes from instead:

- Users: the token.  The HR policies compare the token's username with
  the employee a call names, and read no role.  A target whose policies
  read roles would get them from Cognito groups.
- Records: the response.  cedar-odcs v0.2.6 decides writes on what the
  call names and reads on the record the API returns.
- `read_action`, `read_field_action`, `field_actions`: the convention
  `Read<Model>`, `Read<Model>Field`, and `<Verb>Field` for every tool
  with a payload.  `publish.py` refuses a descriptor that names them
  otherwise.
- The claims mapping: the Lambda's `CEDAR_ODCS_CLAIMS`, since it
  describes the Gateway's identity provider and is the same for every
  target.

The HR file holds 2 tools, 2 models, 4 entities, and 7 policies, 7,344 bytes.

## How the interceptor finds a policy file

The Gateway names each tool `<target>___<tool>`.  On a `tools/call` the
interceptor takes the target from the name, gets `<target>.json` from
`CEDAR_ODCS_POLICIES`, builds cedar-odcs's `Handlers` from it, and hands
over the event.  Any other method passes without a file.

- A loaded file is used for `CEDAR_ODCS_POLICIES_TTL` seconds (60).  The
  next call after that asks S3 with the cached ETag, and the handlers are
  rebuilt only when the file changed.
- A target with no file is not governed: its tools are rejected with
  cedar-odcs's own message, `tool <name> is not governed; no policy
  covers it`.
- A file that cannot be read or parsed on first use rejects the call.  A
  file that cannot be reread keeps the copy in memory and logs a
  warning.  A deleted file stops governing at the next check.
- A tool name whose prefix is not a target name (`../x___y`) never
  reaches S3.

`interceptor/test_interceptor.py` replays all 8 HR fixture events
through the policy-file interceptor and asserts the same output as
cedar-odcs's handlers built from the folder, with the users left out of
the file.

## The deployed stack

`AppliedOdcsShared` in account 009080466601, us-east-1, deployed on
October 29 in 62 seconds, beside `AppliedOdcs`, and redeployed on
October 30 with the cut-down `hr/` in 53 seconds.  `make deploy` wrote the
outputs to `.env.applied-odcs-shared` and published `hr.json` to the
policy bucket.

| Output | Value |
| --- | --- |
| GatewayUrl | `https://applied-odcs-shared-ahp4n92fyp.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp` |
| GatewayId | `applied-odcs-shared-ahp4n92fyp` (`READY`, target `hr` `READY`) |
| UserPoolId | `us-east-1_lWWGYM33o` |
| PolicyBucket | `appliedodcsshared-policies05f61e66-fuanecg2qzf3` |

Users from `make users`: `alice` and `bob`, in no group.  The redeploy
removed the `employee` and `hr` groups, and `maya` and `hana` were
deleted from the pool.  Teardown, not run: `cd infra && npx cdk destroy
AppliedOdcsShared`.  The bucket empties itself on delete.

### Use case 1, live

`make demo`, against the Gateway:

| Call | Status | What came back |
| --- | --- | --- |
| Alice views her profile | 200 | The `Employee` model; `bankAccount` cut on the response |
| Alice updates her own address | 200 | The `AddressChange` model: `chg-0001`, the new address, `effectiveDate`, `payrollNotified`; `fraudScore` cut on the response |
| Alice updates Bob's address | 403 | `UpdateAddress is not permitted for this caller` |
| Alice sends a salary inside the address | 403 | `UpdateAddress rejected; fields not permitted: homeAddress.salary` |
| Bob views Alice's profile | 403 | `ViewProfile is not permitted for this caller` |

The Gateway passed the salary inside the address to the interceptor:
it does not hold the call to the tool's `inputSchema`.  While the five
calls were recorded, the tool's log showed two invocations,
`hr___get_profile` and `hr___update_address`, both Alice's own: the
three refused calls never reached it.  After the redeploy each
interceptor logged `loaded hr's policy file "0e874ea5..."`, the ETag
`publish.py` reported.  Init took 399 ms (request) and 407 ms
(response), as on October 29 (313 and 410 ms).

The calls are recorded in `hr/tests/live/`, with token signatures
and the caller's address redacted, and
`test_live_recording_matches_the_shared_interceptor` replays them through
the interceptor with Cognito's claims.

### A published change, live, with no deploy

On October 29, a file without `employee-updates-own-record` was put in the bucket, and
Alice's own address change was called before and after the TTL.  Then
`make publish` restored the real file (its gate ran first: 103 cases
passed).

| Time | Event | Alice updates her own address |
| --- | --- | --- |
| 23:34:26 | The published file | 200 |
| 23:34:28 | The changed file published, ETag `6884df3a...` | |
| 23:34:29 | Within the TTL | 200, from the copy in memory |
| 23:35:35 | 65 seconds later | 403 `UpdateEmployee is not permitted for this caller` |
| 23:35:36 | `make publish` restores the real file, ETag `2827c0fa...` | |
| 23:36:43 | 65 seconds later | 200 |

Each interceptor logged three loads, at 23:32, 23:35:36, and 23:36:45,
the request and response functions in the same second each time.  No
`kept` warning was logged, so the rechecks of the unchanged file before
23:34:26 took the S3 `304` path, which logs nothing.

## Defaults taken

- **v0.2.6 at the head of cedar-odcs `main`.**  The version commit is
  `cb15664`; the head, `6c9db2b`, adds only `usecases/hr`, so the tag is
  on the commit `./check.sh` ran against.
- **orders leaves the repository.**  v0.2.6's build refuses a
  `facts.json` holding order records, and its orders policies, tool
  arguments, and fixtures changed.  Tag `demo-lambda-target` keeps orders
  on v0.2.4.
- **A separate stack.**  `AppliedOdcsShared` is deployed beside the
  orders demo's `AppliedOdcs`, which keeps working.  The demo password is in
  `.env.applied-odcs-shared` under `APPLIED_ODCS_PASSWORD`.
- **One JSON document per target.**  A target's policies, tool table,
  and contract facts change together, in one object with one ETag.
- **Keep the last good copy on a failed reread.**  The alternative,
  failing closed after a maximum age, is an open question below.
- **Live recordings in `hr/tests/live/`.**  The HR fixtures in
  `hr/tests/events/` carry the use case's own claim (`sub`); recordings
  carry Cognito's (`username`), and are replayed with them.
- **One rule in `hr/`.**  The guardrails, the `prove` target, the roles,
  and the list tool went with the cut-down use case.  `hr-full` keeps
  them.
- **Intent tools and per-tool models in this repository.**  cedar-odcs
  v0.2.6 has one record type per use case and decides a payload at the
  paths the argument spells.  `interceptor/` builds one cedar-odcs use
  case per model and re-roots a `writes` payload at its contract field,
  with no change to cedar-odcs.

## Open questions

- **The two legs can disagree during a change.**  The request and
  response interceptors are separate functions with separate caches, so
  for up to 60 seconds after a publish one leg may decide with the new
  file and the other with the old.
- **Policy files are trusted as published.**  The interceptor checks the
  format, the target, and that the Cedar parses.  It does not check a
  signature, and it does not validate the policies against a schema;
  `make publish` runs `make check` first.
- **Parse once.**  The engine passes Cedar text to every
  `is_authorized` call.  cedarpy 4.12's `PolicySet.from_str` would parse
  each file once at load.
- **The router belongs in cedar-odcs.**  `interceptor/handler.py` uses
  two private helpers of `cedar_odcs.gateway.handlers` (`_reject`,
  `_request_id`), replaces the `engine` of a `Handlers` to re-root a
  `writes` payload, and `policy_file.py` reads a contract's schema
  objects with the private `_leaves`.  Per-tool models and `writes`
  would sit in cedar-odcs's tool table, with a tools gate that compares
  each tool with its own model.
- **The Gateway does not hold a call to its input schema.**  A salary
  sent inside `address` reached the interceptor.  The interceptor
  refuses it because the field round asks about every line; a tool
  without a `writes` binding and no field round would pass it to the
  API.
- **Use cases 2 and 3.**  The signed-in customer needs the interceptor to
  copy a `reservations` claim into `context.token`, which the policy file
  would have to name per target.  Neither reservations use case is in
  this repository.
