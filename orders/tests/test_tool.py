"""The tool Lambda against its data and the Gateway schema."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ORDERS = Path(__file__).resolve().parents[1]
FIELDS = {"id", "owner", "status", "total", "shippingAddress", "cardLast4",
          "internalNotes", "fraudScore", "estimatedDelivery"}


def _load():
    spec = importlib.util.spec_from_file_location("orders_tool_handler", ORDERS / "tool" / "handler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _ctx(name):
    return SimpleNamespace(client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": name}))


@pytest.fixture
def call():
    mod = _load()
    return lambda tool, event=None: mod.handler(event or {}, _ctx(f"orders___{tool}"))


def test_list_orders_returns_five_rows_with_all_fields(call):
    rows = call("list_orders")
    assert len(rows) == 5
    assert all(set(r) == FIELDS for r in rows)


def test_get_order_returns_bobs_order(call):
    o = call("get_order", {"orderId": "order-2002"})
    assert o["owner"] == "bob" and set(o) == FIELDS


def test_update_order_changes_notes(call):
    o = call("update_order", {"orderId": "order-1001", "changes": {"internalNotes": "x"}})
    assert o["internalNotes"] == "x"
    assert call("get_order", {"orderId": "order-1001"})["internalNotes"] == "x"


def test_cancel_and_refund_set_status(call):
    assert call("cancel_order", {"orderId": "order-3003"})["status"] == "cancelled"
    assert call("refund_order", {"orderId": "order-1001"})["status"] == "refunded"


def test_writes_do_not_leak_between_tests(call):
    assert call("get_order", {"orderId": "order-3003"})["status"] == "processing"


def test_unknown_tool_raises(call):
    with pytest.raises(ValueError, match="unknown tool"):
        call("drop_table")


def test_missing_tool_name_raises():
    ctx = SimpleNamespace(client_context=SimpleNamespace(custom={}))
    with pytest.raises(ValueError, match="unknown tool"):
        _load().handler({}, ctx)


def test_unknown_order_raises(call):
    with pytest.raises(ValueError):
        call("get_order", {"orderId": "order-0"})


def test_schema_matches_handler_and_usecase():
    from orders.usecase import TOOLS
    schema = json.loads((ORDERS / "tools.json").read_text())
    names = {t["name"] for t in schema}
    assert names == set(_load().TOOLS)
    assert {n.removeprefix("orders___") for n in TOOLS} <= names


def test_output_schemas_have_the_nine_leaves():
    for t in json.loads((ORDERS / "tools.json").read_text()):
        out = t["outputSchema"]
        order = out["items"] if t["name"] == "list_orders" else out
        assert set(order["properties"]) == FIELDS
