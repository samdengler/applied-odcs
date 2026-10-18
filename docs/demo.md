# Demo for Monday

Ten minutes, terminal only.  `make demo` runs the whole sequence below against the deployed Gateway and prints each command with its output; the outputs here are pasted from that run on October 18, 2026.  Every command is short enough to type live.

Two things in the plan's demo script changed once real output existed.  Dave reads nothing of an order (no permit gives finance a read, and the `refund-implies-no-read` guardrail proves it), so his refund comes back as an empty object.  And step 8's edit fails `make check` on two corpus cases, which stops `make deploy`; the step now shows the edit's effect with `dry-run` and shows the gate catching it.  Both are in `docs/status.md`.

Order-1001 shows `status: refunded` in the live calls because Dave's refund ran earlier against the tool Lambda's in-memory data.  A cold start resets it.

## 1. The contract names the fields

```
$ cat orders/contract/order.odcs.yaml
```

Point at `internalNotes: internal`, `fraudScore: restricted`, and the `writer` properties.  A policy never names a field; this file does.  The lines that matter:

```
24:  - name: id
27:    classification: public
30:      value: system
34:  - name: owner
37:    classification: public
40:      value: system
46:  - name: status
49:    classification: public
52:      value: system
56:  - name: total
59:    classification: public
62:      value: system
66:  - name: shippingAddress
69:    classification: confidential
72:      value: owner
76:  - name: cardLast4
79:    classification: confidential
82:      value: system
86:  - name: internalNotes
89:    classification: internal
92:      value: support
96:  - name: fraudScore
99:    classification: restricted
102:      value: system
106:  - name: estimatedDelivery
109:    classification: public
112:      value: system
```

## 2. The pipeline gate, no AWS

Build, validate, run-tests, then the handler tests on every event fixture, the six recorded live calls included.  This is the gate a pipeline runs.

```
$ make check
...
validation passed
75 passed, 0 failed
build: ok
validate: ok
run-tests: ok
prove: skipped
pull: skipped
121 passed in 0.12s
```

## 3. Alice lists orders

Two rows, seven fields, no `internalNotes`, no `fraudScore`.  Bob's three orders are gone.

```
$ make -s call USER=alice TOOL=list_orders
alice  list_orders  200  2 rows
[
  {
    "id": "order-1001",
    "owner": "alice",
    "status": "refunded",
    "total": 120.0,
    "shippingAddress": "1 Oak Ln",
    "cardLast4": "4242",
    "estimatedDelivery": "2026-09-20"
  },
  {
    "id": "order-3003",
    "owner": "alice",
    "status": "processing",
    "total": 8.0,
    "shippingAddress": "1 Oak Ln",
    "cardLast4": "4242",
    "estimatedDelivery": "2026-09-25"
  }
]
```

## 4. Carol lists orders

Every row, six fields: public and internal.  No `shippingAddress`, no `cardLast4`.  Same tool, same API response, different caller.

```
$ make -s call USER=carol TOOL=list_orders
carol  list_orders  200  5 rows
[
  {
    "id": "order-1001",
    "owner": "alice",
    "status": "refunded",
    "total": 120.0,
    "internalNotes": "called back",
    "estimatedDelivery": "2026-09-20"
  },
  {
    "id": "order-2002",
    "owner": "bob",
    "status": "processing",
    "total": 45.5,
    "internalNotes": "",
    "estimatedDelivery": "2026-09-22"
  },
  {
    "id": "order-3003",
    "owner": "alice",
    "status": "processing",
    "total": 8.0,
    "internalNotes": "gift",
    "estimatedDelivery": "2026-09-25"
  },
  {
    "id": "order-4004",
    "owner": "bob",
    "status": "shipped",
    "total": 230.0,
    "internalNotes": "signature required",
    "estimatedDelivery": "2026-09-28"
  },
  {
    "id": "order-5005",
    "owner": "bob",
    "status": "processing",
    "total": 19.99,
    "internalNotes": "",
    "estimatedDelivery": "2026-10-02"
  }
]
```

## 5. Alice tries a refund

A 403 from the request interceptor, naming the verb.  The request leg never let it reach the API.

```
$ make -s call USER=alice TOOL=refund_order ARGS='{"orderId":"order-1001"}'
alice  refund_order  403  error
RefundOrder is not permitted for this caller
```

## 6. Dave refunds

Allowed: finance holds `RefundOrder`.  The refund ran upstream, and the response comes back empty, because finance reads no field of an order.

```
$ make -s call USER=dave TOOL=refund_order ARGS='{"orderId":"order-1001"}'
dave  refund_order  200  1 object
{}
```

## 7. Carol acting for Alice

Carol acting for Alice holds Alice's access and not her own: Alice's two rows, Alice's fields.  Cognito cannot mint the `act` claim; PingFederate's token exchange can, so this one runs from the command line on the hand-written identity.

```
$ uv run cedar-odcs dry-run orders --caller orders/tests/identities/carol-for-alice.json --tool orders___list_orders --response orders/tests/lists/orders.json
Identity   User::"carol", employee-for-customer, acting for alice
Tool       orders___list_orders  {}
Request    forwarded: the verb round passed
Response   row 1 (order-2002) dropped: read denied
Response   row 0 stripped: fraudScore, internalNotes
Response   row 2 stripped: fraudScore, internalNotes
Returned   [
             {
               "id": "order-1001",
               "owner": "alice",
               "status": "shipped",
               "total": 120.0,
               "shippingAddress": "1 Oak Ln",
               "cardLast4": "4242",
               "estimatedDelivery": "2026-09-20"
             },
             {
               "id": "order-3003",
               "owner": "alice",
               "status": "processing",
               "total": 8.0,
               "shippingAddress": "1 Oak Ln",
               "cardLast4": "4242",
               "estimatedDelivery": "2026-09-25"
             }
           ]
```

## 8. A classification change, and the gate catching it

Change `cardLast4` from `confidential` to `internal`.  `make demo` does it on a copy under `build/demo/` so the repository stays clean; live, edit `orders/contract/order.odcs.yaml` and revert after.

```
$ sed -i '' '/name: cardLast4/,/classification:/s/classification: confidential/classification: internal/' build/demo/orders/contract/order.odcs.yaml && uv run cedar-odcs build build/demo/orders >/dev/null && grep -n -A3 'name: cardLast4' build/demo/orders/contract/order.odcs.yaml
76:  - name: cardLast4
77-    logicalType: string
78-    required: false
79-    classification: internal
```

Alice no longer sees `cardLast4`; Carol now does.  No policy changed.

```
$ uv run cedar-odcs dry-run build/demo/orders --caller orders/tests/identities/alice.json --tool orders___list_orders --response orders/tests/lists/orders.json | grep -E '^(Identity|Response)'
Identity   User::"alice", customer-direct
Response   row 1 (order-2002) dropped: read denied
Response   row 0 stripped: cardLast4, fraudScore, internalNotes
Response   row 2 stripped: cardLast4, fraudScore, internalNotes

== 8. carol after the edit
$ uv run cedar-odcs dry-run build/demo/orders --caller orders/tests/identities/carol.json --tool orders___list_orders --response orders/tests/lists/orders.json | grep -E '^(Identity|Response)'
Identity   User::"carol", employee-direct
Response   row 0 stripped: fraudScore, shippingAddress
Response   row 1 stripped: fraudScore, shippingAddress
Response   row 2 stripped: fraudScore, shippingAddress
```

And `make check` refuses it: two corpus cases pinned the old decision.  The change needs those two cases updated in the same merge request, which is the review the platform team wants.  `make deploy` runs `make check` first, so it stops here too.

```
$ uv run cedar-odcs check build/demo/orders --skip pull --skip prove | grep -E 'FAIL|^(build|validate|run-tests): |passed'
validation passed
  FAIL  owner reads cardLast4 of own order
  FAIL  support agent may not read cardLast4
73 passed, 2 failed
build: ok
validate: ok
run-tests: failed
```

To show the deployed effect, update the two cases (`field-reads.json`: "owner reads cardLast4 of own order" to Deny with no reason, "support agent may not read cardLast4" to Allow with `support-fields-on-any-order`), then `make deploy` (about a minute) and step 3 again.  Or show the dry-run output above and move on.

## 9. What Carol may do

Every verb, every readable field, every writable field, from real authorization questions.

```
$ uv run cedar-odcs check-access orders --caller orders/tests/identities/carol.json
Access of User::"carol" (employee-direct)
On Order::"order-1001" with attributes {"owner": {"__entity": {"type": "User", "id": "alice"}}}

Verbs held      ReadOrder, UpdateOrder, CancelOrder, ListOrders
Verbs not held  RefundOrder

Readable        id (public), owner (public), status (public), total (public), internalNotes (internal), estimatedDelivery (public)
Not readable    shippingAddress (confidential), cardLast4 (confidential), fraudScore (restricted)

Writable        internalNotes (support)
Not writable    id (system), owner (system), status (system), total (system), shippingAddress (owner), cardLast4 (system), fraudScore (system), estimatedDelivery (system)
```

## 10. One case in Cedar's playground

Opens the case in Cedar's playground for anyone who wants to pull on it.

```
$ uv run cedar-odcs share orders --case 'support reads any order' | cut -c1-120
employee direct: support reads any order, unchanged from iteration 1
https://www.cedarpolicy.com/en/playground#data:H4sIALg01GoC/9VZW2/jthL+K6we2iwge+PtXroOinax7RYFipOi3fYlDlpaomx2ZVElqbg+g
...
```

## If the Gateway is down

Steps 3 to 6 run as `dry-run` against the recorded responses, and `make check` already replays the six live recordings in `orders/tests/events/live-*.json`:

```
uv run cedar-odcs dry-run orders --caller orders/tests/identities/alice.json --tool orders___list_orders --response orders/tests/lists/orders.json
```
