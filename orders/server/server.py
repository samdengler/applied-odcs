"""The orders tool as an MCP server, for AgentCore Runtime.

The same five tools as orders/tool/handler.py, over the same orders.json,
with the same argument names.  It does no authorization, on purpose: every
tool returns every field of every row it is asked for, and the Gateway
interceptors in front of it decide each call.  Writes change memory only.

The Runtime's MCP contract: listen on 0.0.0.0:8000, streamable HTTP at
/mcp, stateless.  `python server.py` warms the request path up, then
serves.
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Annotated, Any

import httpx
import uvicorn
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


# The requests the Gateway sends for a tool call, made in process before the
# server listens, so that on Runtime platform V2 the snapshot holds a process
# that has run them: the lazy imports, the first use of each tool's argument
# validator, and the result serialization.  The write tools get an unknown
# orderId, so they validate their arguments and raise without changing ORDERS.
_UNKNOWN = "warm-up"
WARM_UP = [
    {"method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                                        "clientInfo": {"name": "warm-up", "version": "0"}}},
    {"method": "notifications/initialized"},
    {"method": "tools/list"},
    {"method": "tools/call", "params": {"name": "list_orders", "arguments": {}}},
    {"method": "tools/call", "params": {"name": "get_order", "arguments": {"orderId": next(iter(ORDERS))}}},
    {"method": "tools/call", "params": {"name": "update_order", "arguments": {"orderId": _UNKNOWN, "changes": {}}}},
    {"method": "tools/call", "params": {"name": "cancel_order", "arguments": {"orderId": _UNKNOWN}}},
    {"method": "tools/call", "params": {"name": "refund_order", "arguments": {"orderId": _UNKNOWN}}},
]


async def warm_up(app) -> float:
    """Posts WARM_UP to the app in process and returns the milliseconds taken.
    Any status other than 200, or 202 for a notification, raises."""
    start = time.perf_counter()
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
        for i, message in enumerate(WARM_UP):
            body = {"jsonrpc": "2.0", **message, **({} if message["method"].startswith("notifications/") else {"id": i})}
            response = await client.post(mcp.settings.streamable_http_path, json=body, headers=headers)
            if response.status_code not in (200, 202):
                raise RuntimeError(f"warm-up {message['method']}: {response.status_code} {response.text[:200]}")
    return (time.perf_counter() - start) * 1000


async def serve() -> None:
    """What mcp.run(transport="streamable-http") does, with the warm-up
    between starting the app's session manager and listening."""
    app = mcp.streamable_http_app()
    async with app.router.lifespan_context(app):
        print(f"warm-up: {len(WARM_UP)} requests in {await warm_up(app):.0f} ms", flush=True)
        config = uvicorn.Config(app, host=mcp.settings.host, port=mcp.settings.port,
                                log_level=mcp.settings.log_level.lower(), lifespan="off")
        await uvicorn.Server(config).serve()


if __name__ == "__main__":
    asyncio.run(serve())
