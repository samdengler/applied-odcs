#!/bin/bash
# The directory against the deployed Gateway: a field labelled restricted
# never leaves.  Each step prints its command, then its output.  The proofs
# run on copies under build/demo.  The relabel edits the contract and
# restores it on the way out, including when the script is interrupted.
set -u
cd "$(dirname "$0")/.."
ENV=.env.applied-odcs-shared
CONTRACT=directory/contract/employee.odcs.yaml
SAVED=build/demo/employee.odcs.yaml.saved
WAIT=65
ANALYSIS=${CEDAR_ODCS_CHECKOUT:-../cedar-odcs}/analysis
ALICE='{"employeeId":"alice"}'

step() { printf '\n== %s\n$ %s\n' "$1" "$2"; eval "$2"; }
lookup() { make -s call USER="$1" TOOL=directory___look_up_employee ARGS="${2:-$ALICE}"; }
prove_copy() { CEDAR_ODCS_ANALYSIS=$ANALYSIS uv run cedar-odcs prove "build/demo/$1/directory" 2>&1 | grep -E '^  (PASS|FAIL)|proved,'; }
restore() {
  if [ -f "$SAVED" ]; then
    cp -f "$SAVED" "$CONTRACT" && rm -f "$SAVED"
    echo "contract restored; publishing it"
    make -s publish >/dev/null
  fi
}
trap restore EXIT

rm -rf build/demo && mkdir -p build/demo
uv run cedar-odcs build directory >/dev/null

step "1. The whole policy: two statements that read no caller, role, or record" \
  "grep -v '^//' directory/policies.cedar | grep -v '^\$'"
step "2. The labels the registry published for this target, read back from S3" \
  "uv run --env-file $ENV python -c \"import json, os, boto3; d = json.load(boto3.client('s3').get_object(Bucket=os.environ['POLICY_BUCKET'], Key='directory.json')['Body']); print(os.environ['POLICY_BUCKET'] + '/directory.json:', next(e for e in d['entities'] if e['uid']['id'] == 'Employee')['tags'])\""
step "3. Alice looks up Alice: no ssn, no passportNumber" "lookup alice"
step "4. What the tool actually returned" "uv run --env-file $ENV python scripts/tool_returned.py"
step "5. Bob looks up Alice: the response is byte for byte the same" \
  "diff <(lookup alice | tail -n +2) <(lookup bob | tail -n +2) && echo identical"
step "6. The tool fails and its error names a value: the text does not leave" \
  "lookup alice '{\"employeeId\":\"000-12-3456\"}'"
step "7. The proofs, for every caller, every record, and every set of labels" \
  "CEDAR_ODCS_ANALYSIS=$ANALYSIS uv run cedar-odcs prove directory 2>&1 | grep -E '^  (PASS|FAIL)|proved,'"

mkdir -p build/demo/broad build/demo/exempt
cp -R directory build/demo/broad/directory
cat >> build/demo/broad/directory/policies.cedar <<'CEDAR'

@id("someone-later-opens-every-field")
permit(principal, action == Action::"ReadEmployeeField", resource);
CEDAR
step "8. Someone later adds a permit that opens every field: the forbid still wins" \
  "tail -2 build/demo/broad/directory/policies.cedar; prove_copy broad"

cp -R directory build/demo/exempt/directory
cat > build/demo/exempt/directory/policies.cedar <<'CEDAR'
@id("everything-else-passes")
permit(principal, action, resource);

@id("restricted-never-leaves")
forbid(principal, action == Action::"ReadEmployeeField", resource)
unless {
  principal == User::"carol" ||
  (context has field &&
   Contract::"Employee".hasTag(context.field) &&
   Contract::"Employee".getTag(context.field) != "restricted")
};
CEDAR
step "9. Someone exempts one user, Carol, from the forbid: every test case still passes and the proofs fail, so make publish stops" \
  "grep -n carol build/demo/exempt/directory/policies.cedar; uv run cedar-odcs run-tests build/demo/exempt/directory | tail -1; prove_copy exempt"

cp -f "$CONTRACT" "$SAVED"
sed -i '' 's/classification: internal/classification: restricted/' "$CONTRACT"
step "10. Security reclassifies personalPhone: one label in the contract, then publish" \
  "diff '$SAVED' '$CONTRACT'; make -s publish >/dev/null && echo published"
step "11. Within the TTL the interceptors may still use the old file; after $WAIT seconds, with no deploy" \
  "sleep $WAIT; lookup alice"
restore
step "12. The label restored and published; after $WAIT seconds personalPhone is back" \
  "sleep $WAIT; lookup alice"
