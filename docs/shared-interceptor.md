# Shared interceptor and policy files in S3

The `shared-interceptor` branch, October 29, 2026.  The binding of MCP
tools to the ODCS contract moves to the agentic registry, so the
interceptor Lambda no longer carries a use case.  One function serves
every Gateway target and decides each call from the policy file the
registry publishes for that target.  The demonstration is use case 1 of
the doc "Writes the Gateway decides from the request": an employee
changes their own address.

## What changed from the orders demo

| Area | orders demo, tag `demo-lambda-target` | shared interceptor |
| --- | --- | --- |
| Engine | cedar-odcs v0.2.4 | cedar-odcs v0.2.6, tagged at `6c9db2b` after `./check.sh` passed (873 tests, every use case's check, 212 history proofs) |
| Governed tool | `orders/` | `hr/`, copied from cedar-odcs `usecases/hr`; only three import lines differ |
| Interceptor code | cedar-odcs plus `orders/` and its generated files, loaded from `/var/task/orders` | cedar-odcs plus `interceptor/`, no use case |
| Policies reach the Lambda | in the deployment package | `s3://<PolicyBucket>/hr.json`, read on first use and rechecked every 60 seconds |
| Stack | `AppliedOdcs` | `AppliedOdcsShared`, every physical name `applied-odcs-shared` |

## The policy file

One JSON document per Gateway target, written by `scripts/publish.py`
from the use case folder after `cedar-odcs build`.  It holds what the
engine cannot decide without, and nothing that belongs to the token, the
response, or the Gateway.

| Part | What reads it |
| --- | --- |
| `policies` | Every decision.  The Cedar text, with the rendered grants when a use case has them. |
| `tools` | The tool table: which action a tool call asks, which argument names the record, which go into `context.input`, which is the write payload, and whether the result is an object or a list.  This is the registry's binding. |
| `resource` | How a row the tool returns becomes a Cedar entity: its type, its id field, and the fields that become attributes. |
| `entities` | The `Contract` entities (each field's level and writer, which the field policies look up with `getTag`) and the `Role` hierarchy. |

Left out, and where each comes from instead:

- Users and their stored roles: the token.  Every role a policy reads is
  a Cognito group (`employee`, `hr`).
- Records: the response.  cedar-odcs v0.2.6 decides writes on what the
  call names and reads on the record the API returns.
- `read_action`, `read_field_action`, `field_actions`: the convention
  `Read<Type>`, `Read<Type>Field`, and `<Verb>Field` for every tool with
  a payload.  `publish.py` refuses a descriptor that names them
  otherwise.
- The claims mapping: the Lambda's `CEDAR_ODCS_CLAIMS`, since it
  describes the Gateway's identity provider and is the same for every
  target.

The HR file holds 3 tools, 4 entities, and 12 policies.

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

`interceptor/test_interceptor.py` replays all 22 HR fixture events
through the policy-file interceptor and asserts the same output as
cedar-odcs's handlers built from the folder, with the users left out of
the file.

## The deployed stack

`AppliedOdcsShared` in account 009080466601, us-east-1, deployed on
October 29 in 62 seconds, beside `AppliedOdcs`.  `make deploy` wrote the
outputs to `.env.applied-odcs-shared` and published `hr.json` to the
policy bucket.

| Output | Value |
| --- | --- |
| GatewayUrl | `https://applied-odcs-shared-ahp4n92fyp.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp` |
| GatewayId | `applied-odcs-shared-ahp4n92fyp` (`READY`, target `hr` `READY`) |
| UserPoolId | `us-east-1_lWWGYM33o` |
| PolicyBucket | `appliedodcsshared-policies05f61e66-fuanecg2qzf3` |

Users from `make users`: `alice`, `bob`, and `maya` in group `employee`,
`hana` in group `hr`.  Teardown, not run: `cd infra && npx cdk destroy
AppliedOdcsShared`.  The bucket empties itself on delete.

### Use case 1, live

`make demo`, against the Gateway:

| Call | Status | What came back |
| --- | --- | --- |
| Alice updates her own address | 200 | Her record with the new address; `hrNotes` and `bankAccount` stripped on the response |
| Alice updates Bob's address | 403 | `UpdateEmployee is not permitted for this caller` |
| Alice updates her address and salary | 403 | `UpdateEmployee rejected; fields not permitted: salary` |
| Bob reads Alice's record | 200 | The six directory fields: `employeeId`, `name`, `workEmail`, `jobTitle`, `department`, `manager` |

The tool's log shows two invocations, `hr___update_employee` and
`hr___get_employee`: the two refused calls never reached it.  Each
interceptor logged `loaded hr's policy file "2827c0fa..."`, the ETag
`publish.py` reported.  Init took 313 ms (request) and 410 ms (response),
the first two invocations of each function 259 to 509 ms (the S3 client
and the one read), and every call after that about 2 ms.

The four calls are recorded in `hr/tests/live/`, with token signatures
and the caller's address redacted, and
`test_live_recording_matches_the_shared_interceptor` replays them through
the interceptor with Cognito's claims.

### A published change, live, with no deploy

A file without `employee-updates-own-record` was put in the bucket, and
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
  `hr/tests/events/` carry the use case's own claims (`sub`, `roles`);
  recordings carry Cognito's, and are replayed with them.

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
  `_request_id`).  It would sit beside `gateway/handler.py` as a second
  entry point.
- **Use cases 2 and 3.**  The signed-in customer needs the interceptor to
  copy a `reservations` claim into `context.token`, which the policy file
  would have to name per target.  Neither reservations use case is in
  this repository.
