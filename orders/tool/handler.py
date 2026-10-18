"""The orders tool Lambda.

It does no authorization, on purpose: every tool returns every field of every
row it is asked for.  Access control belongs to the Gateway interceptors in
front of it, and this tool is what they are tested against.  Writes change
memory only and do not survive a cold start.
"""
import json
import os

_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "orders.json")
with open(_PATH) as _f:
    ORDERS = {o["id"]: o for o in json.load(_f)}

_KEY = "bedrockAgentCoreToolName"


def _order(event):
    order_id = (event or {}).get("orderId")
    if order_id not in ORDERS:
        raise ValueError(f"unknown orderId: {order_id!r}")
    return ORDERS[order_id]


def get_order(event):
    return _order(event)


def update_order(event):
    order = _order(event)
    order.update(event.get("changes") or {})
    return order


def cancel_order(event):
    order = _order(event)
    order["status"] = "cancelled"
    return order


def refund_order(event):
    order = _order(event)
    order["status"] = "refunded"
    return order


def list_orders(event):
    return list(ORDERS.values())


TOOLS = {f.__name__: f for f in
         (get_order, update_order, cancel_order, refund_order, list_orders)}


def handler(event, context):
    custom = getattr(getattr(context, "client_context", None), "custom", None)
    print("client_context " + json.dumps(custom, default=str))
    raw = (custom or {}).get(_KEY)
    if not raw:
        raise ValueError(f"unknown tool: {_KEY} missing, received {custom!r}")
    name = raw.split("___", 1)[1] if "___" in raw else raw
    if name not in TOOLS:
        raise ValueError(f"unknown tool: {raw!r}")
    return TOOLS[name](event)
