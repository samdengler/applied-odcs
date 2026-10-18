# Overnight status

The run of `docs/plan.md`, Work order steps 1 to 12, on October 17 and 18, 2026.  Each entry says what the plan asked, what was done, and what was observed.

## Commits and tags

(Filled in at step 12.)

## Defaults taken

- **cedar-odcs venv and analysis build.**  The cedar-odcs checkout's `.venv` and `analysis/target` were built when the repository was named `cedar-osdc`; `pytest` had a stale shebang and the prover looked for cvc5 under the old path.  Both were rebuilt locally (ignored paths, nothing committed).  `./check.sh` was green before any change: 712 tests, 211 history proofs.
- **Record switch in v0.2.0.**  The plan puts `CEDAR_ODCS_RECORD` in Build and check but not in a Work order step.  It landed in cedar-odcs before the `v0.2.0` tag, as its own commit, so the first bundle carries it.  The Lambda entry point sets the `cedar-odcs` logger to INFO (DEBUG with the switch), since the Lambda runtime's root logger does not show INFO from a library logger otherwise.
- **`check` from an installed cedar-odcs (v0.2.1).**  `cedar-odcs check orders` from the sample ran `pull`, which rewrites `contract/order.odcs.yaml` from `contract/unity/`, and then `prove`, which failed because an installed package has no `analysis/` crate beside it.  cedar-odcs `v0.2.1` adds `check --skip pull --skip prove` and `CEDAR_ODCS_ANALYSIS`.  The sample's `make check` skips both: its contract is the source (decision 11), and `make prove` points `CEDAR_ODCS_ANALYSIS` at `../cedar-odcs/analysis`.  `PULL` stays in `usecase.py` so `cedar-odcs pull orders` still shows the catalog path.  Because of this extra tag, the grants work is tagged `v0.2.2` and the tool-schema gate `v0.2.3` (the plan said `v0.2.1` and `v0.2.2`).
- **Copied tests that could not stay unchanged.**  `test_interceptor.py` and `test_corpus.py` import `orders.usecase` (they imported `usecases.orders.usecase`).  `test_policies_and_entities_are_the_proven_ones` was removed from `test_interceptor.py`: it compares against cedar-odcs's `history/`, which is not here.  `test_build.py` was rewritten: the cedar-odcs version compares committed generated files and the history chain, and here nothing generated is committed.  It now checks that build writes the schema, maps, and entities, and that every one of the nine leaves has a known level and a writer.  The corpus (`tests/test-cases/`) is unchanged and passes: 75 cases.
- **Build before tests.**  A root `conftest.py` builds `orders/contract/generated/` and `orders/entities.json` from the contract before any test loads the use case, so `uv run pytest` works on a fresh clone.
- **Identity files.**  Carol's identity carries `cognito:groups: [support]` and Dave's `[finance]`, as the plan's Identities and events section says; the live pool also puts both in `employee`.  UUIDs and the client id in the fixtures are made up.

## Findings against the plan

- **Dave reads nothing.**  The plan expects Dave's `list_orders` to return every row with the five public fields, and his refund to echo public fields.  Under the unchanged policies no permit gives finance `ReadOrder` or `ReadOrderField`, and the guardrail `refund-implies-no-read` proves it.  `dry-run` with `dave.json` drops all three rows (`read denied`) and returns `[]`; the copied `test_finance_list_is_empty` and `test_write_tools_echoing_the_order_are_filtered` pin the same.  The policies were not changed.
- **Carol sees six fields.**  The plan says seven for Carol.  Public is five (`id`, `owner`, `status`, `total`, `estimatedDelivery`) and internal is one (`internalNotes`), so Carol gets six on every row.  Alice gets seven (five public, two confidential).

## Unverified items

(Filled in from the live calls.)
