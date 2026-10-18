"""The build's outputs from the contract.  The contract is the source in
this repository: nothing generated is committed, and the corpus pins
the decisions the levels produce."""

import json

from cedar_odcs.engine.contract import build
from orders.usecase import CONTRACT, ROOT

LEVELS = {"public", "internal", "confidential", "restricted"}
LEAVES = {"id", "owner", "status", "total", "estimatedDelivery",
          "shippingAddress", "cardLast4", "internalNotes", "fraudScore"}


def _tags(outputs, entity_id):
    entities = json.loads(outputs["contract/generated/contract.entities.json"])
    return next(e["tags"] for e in entities if e["uid"]["id"] == entity_id)


def test_build_writes_the_schema_maps_and_entities():
    outputs = build(ROOT, CONTRACT)
    assert {"contract/generated/contract.entities.json", "contract/generated/order.cedarschema",
            "entities.json"} <= set(outputs)


def test_every_leaf_has_a_known_level():
    levels = _tags(build(ROOT, CONTRACT), "Order")
    assert set(levels) == LEAVES
    assert set(levels.values()) <= LEVELS


def test_every_leaf_has_a_writer():
    writers = _tags(build(ROOT, CONTRACT), "Order/writers")
    assert set(writers) == LEAVES
