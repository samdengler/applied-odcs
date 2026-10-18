"""The orders tool as an MCP server, for AgentCore Runtime.

The same five tools as orders/tool/handler.py, over the same orders.json,
with the same argument names.  It does no authorization, on purpose: every
tool returns every field of every row it is asked for, and the Gateway
interceptors in front of it decide each call.  Writes change memory only.

The Runtime's MCP contract: listen on 0.0.0.0:8000, streamable HTTP at
/mcp, stateless.  `python server.py` runs it.
"""
import json
from pathlib import Path
from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field

# build/server has orders.json beside this file; in the repository it is
# the tool's data file, so the data has one source.
_HERE = Path(__file__).resolve().parent
_PATH = next(p for p in (_HERE / "orders.json", _HERE.parent / "tool" / "data" / "orders.json") if p.exists())
ORDERS = {o["id"]: o for o in json.loads(_PATH.read_text())}

mcp = FastMCP("orders", host="0.0.0.0", port=8000, streamable_http_path="/mcp", stateless_http=True)

OrderId = Annotated[str, Field(description="The order id, for example order-1001.")]


def _order(order_id: str) -> dict[str, Any]:
    if order_id not in ORDERS:
        raise ToolError(f"unknown orderId: {order_id!r}")
    return ORDERS[order_id]


@mcp.tool(description="Return one order by id.")
def get_order(orderId: OrderId) -> dict[str, Any]:
    return _order(orderId)


@mcp.tool(description="Change the writable fields of one order and return it.")
def update_order(orderId: Annotated[str, Field(description="The order id.")],
                 changes: Annotated[dict[str, Any], Field(description="Fields to change.")]) -> dict[str, Any]:
    order = _order(orderId)
    order.update(changes or {})
    return order


@mcp.tool(description="Cancel one order and return it.")
def cancel_order(orderId: OrderId) -> dict[str, Any]:
    order = _order(orderId)
    order["status"] = "cancelled"
    return order


@mcp.tool(description="Refund one order and return it.")
def refund_order(orderId: OrderId) -> dict[str, Any]:
    order = _order(orderId)
    order["status"] = "refunded"
    return order


@mcp.tool(description="Return every order.")
def list_orders() -> list[dict[str, Any]]:
    return list(ORDERS.values())


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
