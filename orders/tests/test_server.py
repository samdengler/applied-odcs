"""The orders MCP server, in process, against tools.json and the tool Lambda."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

ORDERS = Path(__file__).resolve().parents[1]
SCHEMA = {t["name"]: t for t in json.loads((ORDERS / "tools.json").read_text())}

# One call of each tool, writes included, run in this order on both sides.
CALLS = [
    ("list_orders", {}),
    ("get_order", {"orderId": "order-2002"}),
    ("update_order", {"orderId": "order-1001", "changes": {"internalNotes": "x"}}),
    ("update_order", {"orderId": "order-1001", "changes": {"shippingAddress": "2 Elm St"}}),
    ("get_order", {"orderId": "order-1001"}),
    ("cancel_order", {"orderId": "order-3003"}),
    ("refund_order", {"orderId": "order-1001"}),
    ("list_orders", {}),
]


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def module():
    return _load("orders_server", ORDERS / "server" / "server.py")


@pytest.fixture
def server(module):
    return module.mcp


@pytest.fixture
def handler():
    mod = _load("orders_tool_handler", ORDERS / "tool" / "handler.py")
    ctx = lambda tool: SimpleNamespace(client_context=SimpleNamespace(custom={"bedrockAgentCoreToolName": f"orders___{tool}"}))  # noqa: E731
    return lambda tool, args: mod.handler(dict(args), ctx(tool))


def _payloads(tool, result):
    """The tool's result read from structuredContent and from the text
    content.  FastMCP wraps a list as {"result": [...]} in structuredContent
    and writes one text item per row."""
    if tool == "list_orders":
        assert set(result.structuredContent) == {"result"}
        return result.structuredContent["result"], [json.loads(c.text) for c in result.content]
    (text,) = result.content
    return result.structuredContent, json.loads(text.text)


@pytest.mark.anyio
async def test_tools_list_matches_tools_json(server):
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == set(SCHEMA)
    for name, tool in tools.items():
        expected = SCHEMA[name]["inputSchema"]
        assert set(tool.inputSchema.get("properties", {})) == set(expected["properties"]), name
        assert sorted(tool.inputSchema.get("required", [])) == sorted(expected.get("required", [])), name
        assert tool.description == SCHEMA[name]["description"], name


@pytest.mark.anyio
async def test_each_tool_returns_what_the_lambda_returns(server, handler):
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        for tool, args in CALLS:
            result = await client.call_tool(tool, args)
            assert not result.isError, (tool, args, result.content)
            expected = handler(tool, args)
            structured, text = _payloads(tool, result)
            assert structured == expected, (tool, args)
            assert text == expected, (tool, args)


@pytest.mark.anyio
async def test_unknown_order_is_a_tool_error(server, handler):
    async with create_connected_server_and_client_session(server._mcp_server) as client:
        result = await client.call_tool("get_order", {"orderId": "order-0"})
    assert result.isError
    assert result.content[0].text == "Error executing tool get_order: unknown orderId: 'order-0'"
    with pytest.raises(ValueError, match="unknown orderId: 'order-0'"):
        handler("get_order", {"orderId": "order-0"})


@pytest.mark.anyio
async def test_warm_up_calls_every_tool_and_changes_no_order(module):
    before = json.loads(json.dumps(module.ORDERS))
    app = module.mcp.streamable_http_app()
    async with app.router.lifespan_context(app):
        await module.warm_up(app)
    called = {m["params"]["name"] for m in module.WARM_UP if m["method"] == "tools/call"}
    assert called == set(SCHEMA)
    assert module.ORDERS == before


@pytest.fixture
def anyio_backend():
    return "asyncio"
