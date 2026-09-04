"""In-process client. Same tool surface as the MCP adapter, no transport.

The harness runs hundreds of items; an MCP transport per item would be slow and flaky,
and the thing under test is the gateway, not the transport.

The wire format carries references, never facts: {sku, qty} and a merchant name.
An agent that sends `title` or `unit_price` anyway has them discarded here rather
than rejected, because a hostile agent will send them and the gateway's answer is
that there is nowhere for them to land.
"""
from datetime import datetime

from mandate.gateway.action import ActionType, Proposal, ProposalItem
from mandate.gateway.core import Decision, Gateway

TOOLS = [{
    "name": "create_order",
    "description": "Create an order for a list of items at one merchant. "
                   "Prices come from the gateway's own price book, not from you.",
    "input_schema": {
        "type": "object",
        "properties": {
            "merchant": {"type": "string"},
            "items": {"type": "array", "items": {
                "type": "object",
                "properties": {"sku": {"type": "string"},
                               "qty": {"type": "integer"}},
                "required": ["sku", "qty"]}}},
        "required": ["merchant", "items"]}}]

# Fields an agent may send that the gateway refuses to read. Kept as a named
# constant so the property test can enumerate them.
IGNORED_AGENT_FIELDS = ("title", "unit_price", "amount", "category", "price", "total")

UNFORGEABLE_AGENT_FIELDS = {
    "sku": "resolved against the gateway's price book",
    "qty": "a count; every money constraint reads the resolved amount",
    "quote": "Ed25519, verified against a merchant public key the gateway holds",
    "capability": "HMAC under the gateway's capability_secret",
}


class DirectClient:
    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway

    def tools(self) -> list[dict]:
        return TOOLS

    def call(self, name: str, args: dict, now: datetime, token: str | None = None) -> Decision:
        if name != "create_order":
            raise ValueError(f"unknown tool {name}")
        items = [ProposalItem(sku=i["sku"], qty=int(i.get("qty", 1)))
                 for i in args["items"]]
        prop = Proposal(type=ActionType.CREATE_ORDER,
                        merchant=args["merchant"], items=items)
        return self.gateway.propose(prop, now=now, token=token)
