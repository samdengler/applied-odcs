#!/bin/bash
# The Monday sequence in docs/demo.md, run end to end.  Each step prints
# its command, then its output.  Step 8, the contract edit, runs on a
# copy of orders/ under build/, so the repository is never changed.
set -u
cd "$(dirname "$0")/.."

step() { printf '\n== %s\n$ %s\n' "$1" "$2"; eval "$2"; }

step "1. The contract names the fields" \
  "grep -nE '^  - name:|classification:|value: (system|owner|support)' orders/contract/order.odcs.yaml | head -40"
step "2. The pipeline gate, no AWS" \
  "make -s check 2>&1 | grep -E '^(pull|build|validate|run-tests|prove): |passed'"
step "3. Alice lists orders" "make -s call USER=alice TOOL=list_orders"
step "4. Carol lists orders" "make -s call USER=carol TOOL=list_orders"
step "5. Alice tries a refund" "make -s call USER=alice TOOL=refund_order ARGS='{\"orderId\":\"order-1001\"}'"
step "6. Dave refunds" "make -s call USER=dave TOOL=refund_order ARGS='{\"orderId\":\"order-1001\"}'"
step "7. Carol acting for Alice, from the command line" \
  "uv run cedar-odcs dry-run orders --caller orders/tests/identities/carol-for-alice.json --tool orders___list_orders --response orders/tests/lists/orders.json"

rm -rf build/demo && mkdir -p build/demo && rsync -a --exclude contract/generated --exclude entities.json orders/ build/demo/orders/
step "8. cardLast4 from confidential to internal (on a copy in build/demo)" \
  "sed -i '' '/name: cardLast4/,/classification:/s/classification: confidential/classification: internal/' build/demo/orders/contract/order.odcs.yaml && uv run cedar-odcs build build/demo/orders >/dev/null && grep -n -A3 'name: cardLast4' build/demo/orders/contract/order.odcs.yaml"
for who in alice carol; do
  step "8. $who after the edit" \
    "uv run cedar-odcs dry-run build/demo/orders --caller orders/tests/identities/$who.json --tool orders___list_orders --response orders/tests/lists/orders.json | grep -E '^(Identity|Response)'"
done
step "8. the gate on the edited contract" \
  "uv run cedar-odcs check build/demo/orders --skip pull --skip prove | grep -E 'FAIL|^(build|validate|run-tests): |passed'"

step "9. What Carol may do" "uv run cedar-odcs check-access orders --caller orders/tests/identities/carol.json"
step "10. One case in Cedar's playground" "uv run cedar-odcs share orders --case 'support reads any order' | cut -c1-120"
