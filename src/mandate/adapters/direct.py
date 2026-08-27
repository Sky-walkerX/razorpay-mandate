"""In-process client. Same tool surface as the MCP adapter, no transport.

The harness runs hundreds of items; an MCP transport per item would be slow and flaky,
and the thing under test is the gateway, not the transport.
"""
from datetime import datetime

from mandate.gateway.action import Action, ActionType, LineItem
from mandate.gateway.core import Decision, Gateway
from mandate.money import Paise

TOOLS = [{
    "name": "create_order",
    "description": "Create an order for a list of items at one merchant.",
    "input_schema": {
        "type": "object",
        "properties": {
            "merchant": {"type": "string"},
            "items": {"type": "array", "items": {
                "type": "object",
                "properties": {"sku": {"type": "string"}, "title": {"type": "string"},
                               "qty": {"type": "integer"},
                               "unit_price": {"type": "integer",
                                              "description": "paise per unit"}},
                "required": ["sku", "title", "qty", "unit_price"]}}},
        "required": ["merchant", "items"]}}]


class DirectClient:
    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway

    def tools(self) -> list[dict]:
        return TOOLS

    def call(self, name: str, args: dict, now: datetime) -> Decision:
        if name != "create_order":
            raise ValueError(f"unknown tool {name}")
        items = [LineItem(sku=i["sku"], title=i["title"], qty=int(i["qty"]),
                          unit_price=Paise(int(i["unit_price"])),
                          amount=Paise(int(i["qty"]) * int(i["unit_price"])))
                 for i in args["items"]]
        action = Action(type=ActionType.CREATE_ORDER,
                        amount=Paise(sum(int(i.amount) for i in items)),
                        merchant=args["merchant"], items=items)
        return self.gateway.propose(action, now=now)
