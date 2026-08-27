"""MCP adapter. Mirrors razorpay-mcp-server's tool name so an agent is drop-in.

Used for the live demo. The harness uses DirectClient instead; both call the same
Gateway.propose, so there is one enforcement implementation, not two.

Written against mcp>=2.0's MCPServer (mcp.server.mcpserver), not the mcp 1.x
`Server` + `@server.list_tools()`/`@server.call_tool()` decorator pair the original
plan assumed -- the installed SDK's low-level `Server` no longer exposes those.
See BREAKAGE.md, Day 11.
"""
from datetime import datetime, timedelta, timezone

from mcp.server.mcpserver import MCPServer

from mandate.adapters.direct import DirectClient
from mandate.gateway.core import Gateway

IST = timezone(timedelta(hours=5, minutes=30))


def build_mcp_server(gateway: Gateway) -> MCPServer:
    server = MCPServer("mandate")
    client = DirectClient(gateway)

    @server.tool(name="create_order",
                description="Create an order for a list of items at one merchant.")
    def create_order(merchant: str, items: list[dict]) -> str:
        d = client.call("create_order", {"merchant": merchant, "items": items},
                        now=datetime.now(IST))
        return (f"OK {d.downstream}" if d.verdict.value == "ALLOW"
                else f"REFUSED by {d.clause_id}: {d.message}")

    return server
