# applied-odcs

One governed MCP tool, deployed behind an AgentCore Gateway with cedar-odcs's
two interceptors.  The plan is `docs/plan.md`; its Work order section is the
task list for an implementation session.  Decisions behind the plan are in the
questions doc linked at the top of `docs/plan.md`.

## Layout and interfaces

- `hr/` is the governed tool: the folder a tool team would copy.  The
  engine comes from cedar-odcs as a git dependency; nothing from
  `cedar_odcs/` is copied here.
- `interceptor/` is the shared interceptor Lambda.  It holds no use case
  and reads each target's policy file from S3 (`docs/shared-interceptor.md`).
- `make deploy` deploys only the `AppliedOdcsShared` stack, with
  `.env.applied-odcs-shared`.  `AppliedOdcs` is the earlier orders demo, at
  tag `demo-lambda-target`; nothing here deploys it.
- `Makefile` is the interface.  Every verification in the plan is a target.
- `cedar-odcs` is checked out at `../cedar-odcs`.  Changes to it follow its
  own `CLAUDE.md` (Beads for its task tracking: `bd` an issue per change,
  close it when done).  This repo does not use Beads.

## Conventions

- Prose (README, docs, commit messages, comments): two spaces after a
  period, no em dashes or en dashes, plain declarative sentences.  Headings
  are noun phrases.
- Alice, Bob, Carol, Dave, Maya, and Hana are capitalized as people in
  prose.  Lowercase only when quoting an identifier (`hana-for-alice.json`,
  a `username` claim, an `owner` value).
- Commit messages in the cedar-odcs style: one sentence saying what changed
  and why, no type prefix, body only when the diff does not explain itself.
- Generated outputs are never committed: `hr/contract/generated/`,
  `hr/entities.json`, `build/`, `infra/cdk.out/`.
- Secrets are never committed.  The demo password lives in
  `.env.applied-odcs-shared` (ignored); `docs/shared-interceptor.md` says
  where it is, not what it is.

## Working unattended

- Take the plan's default instead of asking.  Record every default taken,
  every fallback, and every item the plan marked unverified in
  `docs/status.md`, with what was observed.
- A step that fails its verification is fixed or its named fallback is
  taken; it is never committed over.
- Steps 1 to 9 of the Work order come first.  Steps 10 and 11 run only
  once step 9 is green, and have a 03:00 local cutoff.
- Never deploy to, or read from, anything but the personal account in
  `us-east-1`.  Do not run `cdk destroy` unless the plan says so.

## Sub-agents

- `log-reader` (haiku): CloudWatch log reading, file inventories, grep
  across the two repos.
- `fixture-writer` (sonnet): regenerating test fixtures, writing the tool
  Lambda and its tests, Makefile targets.
- Anything that changes `../cedar-odcs`, the CDK app, or a decision in
  `docs/status.md` stays on the main session's model.
