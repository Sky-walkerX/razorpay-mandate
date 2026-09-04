"""Execute an allowed action by calling Razorpay's own MCP server.

This is the gateway's downstream for the `/mcp/razorpay` surface. It exists so
that the proxy's forwarding happens *inside* `Gateway.propose`, on the allow
branch, under the same lock and the same ledger as every other execution path. A
proxy that decided in the gateway and forwarded beside it would have two
enforcement paths, and this project has already recorded why that is the failure
worth designing against.

It receives the **resolved** action and nothing else. `create_order`'s `action`
keyword is the resolved action the constraints evaluated, so the amount reaching
Razorpay is arithmetically the amount that was checked. The agent's own argument
dict never reaches this module: three of the four bound tools are forwarded with
`{amount, currency}` alone, and everything else the agent sent is dropped rather
than passed along.
"""
from mandate.adapters.razorpay_upstream import RazorpayMCPUpstream, UpstreamError
from mandate.downstream.fake import DownstreamError
from mandate.money import Paise

# The upstream tool each action type executes as. Keyed on ActionType's value, so
# a new bound tool has to name its action rather than being inferred.
_TOOL_FOR = {
    "create_order": "create_order",
    "create_payment_link": "create_payment_link",
    "payment_link_upi_create": "payment_link_upi_create",
    "capture_payment": "capture_payment",
}


class RazorpayMCPDownstream:
    """Forwards one allowed action to Razorpay's MCP server."""

    def __init__(self, upstream: RazorpayMCPUpstream) -> None:
        self.upstream = upstream

    def create_order(
        self,
        amount: Paise,
        receipt: str,
        notes: dict,
        skus: list[str] | None = None,
        action=None,
    ) -> dict:
        tool = _TOOL_FOR.get(str(getattr(action, "type", "")), "create_order")

        # Built from `amount`, the gateway's own resolved figure. Nothing here is
        # copied from what the agent sent.
        args: dict = {"amount": int(amount), "currency": "INR"}
        if tool == "create_order":
            args["receipt"] = receipt[:40]   # Razorpay caps this field at 40 chars
            args["notes"] = {k: str(v) for k, v in (notes or {}).items()}
        if tool == "capture_payment":
            ref = getattr(action, "downstream_ref", None)
            if not ref:
                raise DownstreamError("capture_payment needs a payment id and got none")
            args["payment_id"] = ref

        try:
            result = self.upstream.call_tool(tool, args)
        except UpstreamError as e:
            raise DownstreamError(str(e)) from e

        body = _first_json(result)
        # The gateway compares this against the authorised amount and voids on
        # divergence, so echoing our own figure when the upstream does not return
        # one would disable that check. Absent means absent.
        body.setdefault("id", body.get("id") or _any_id(body))
        return body


def _first_json(result: dict) -> dict:
    """The tool result's payload, which MCP wraps as text content."""
    import json
    for part in result.get("content") or []:
        if part.get("type") == "text":
            try:
                parsed = json.loads(part.get("text") or "")
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return dict(result.get("structuredContent") or {})


def _any_id(body: dict) -> str | None:
    """Razorpay names the id differently per entity; a payment link has none."""
    for key in ("id", "order_id", "payment_id", "short_url"):
        if body.get(key):
            return str(body[key])
    return None
