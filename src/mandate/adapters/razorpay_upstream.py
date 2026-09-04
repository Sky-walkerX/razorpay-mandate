"""A thin client for Razorpay's own remote MCP server.

`https://mcp.razorpay.com/mcp` is a public streamable-HTTP MCP endpoint that
authenticates with the merchant's API keys over HTTP Basic. Measured against it
on 4 Sep 2026 with this project's `rzp_test_` keys: it serves **42 tools, 16 of
them flagged `destructiveHint`**, and both `tools/list` and `tools/call` answer a
plain JSON-RPC POST. There is no `initialize` handshake and no `mcp-session-id`,
which is why this module is forty lines rather than an MCP client session.

That surface is the reason the proxy exists. An agent handed these credentials
can call `create_payment_link`, `capture_payment` or `revoke_token` with nothing
between it and the money. This class is the only thing in the codebase that holds
those keys, and `RazorpayMCPProxy` is the only thing that calls it.

The `rzp_test_` guard matches `RazorpayDownstream`'s. A proxy pointed at live
keys by accident is the one mistake here that spends real money.
"""
import json
from typing import Any

import httpx

UPSTREAM_URL = "https://mcp.razorpay.com/mcp"

# Razorpay answers either a bare JSON body or an SSE frame depending on the
# request. Asking for both and parsing both is cheaper than guessing.
_ACCEPT = "application/json, text/event-stream"

DEFAULT_TIMEOUT_S = 20.0


class UpstreamError(RuntimeError):
    """The upstream refused, failed, or answered something unparseable."""


def _parse(body: str) -> dict[str, Any]:
    """A JSON-RPC response, whether it arrived bare or inside an SSE frame."""
    text = body.strip()
    if text.startswith(("event:", "data:")):
        for line in text.splitlines():
            if line.startswith("data:"):
                text = line[len("data:"):].strip()
                break
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise UpstreamError(f"unparseable upstream response: {body[:200]}") from e


class RazorpayMCPUpstream:
    """Razorpay's MCP server, reachable only from inside the gateway."""

    def __init__(self, key_id: str, key_secret: str, *, url: str = UPSTREAM_URL,
                 timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        if not key_id.startswith("rzp_test_"):
            raise ValueError(f"refusing to start outside test mode: {key_id[:9]}...")
        self._auth = (key_id, key_secret)
        self._url = url
        self._timeout = timeout_s
        self._next_id = 0

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        self._next_id += 1
        payload = {"jsonrpc": "2.0", "id": self._next_id,
                   "method": method, "params": params}
        try:
            resp = httpx.post(
                self._url, json=payload, auth=self._auth, timeout=self._timeout,
                headers={"Content-Type": "application/json", "Accept": _ACCEPT},
            )
        except httpx.HTTPError as e:
            raise UpstreamError(f"{method} failed to reach the upstream: {e}") from e

        if resp.status_code >= 400:
            raise UpstreamError(f"{method} returned HTTP {resp.status_code}")

        body = _parse(resp.text)
        if "error" in body:
            raise UpstreamError(f"{method}: {body['error']}")
        return body.get("result") or {}

    def list_tools(self) -> list[dict[str, Any]]:
        """Every tool the upstream currently serves, in its own order."""
        return list(self._rpc("tools/list", {}).get("tools") or [])

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Forward one call. The proxy decides whether a call gets this far."""
        return self._rpc("tools/call", {"name": name, "arguments": arguments})


def destructive_names(tools: list[dict[str, Any]]) -> set[str]:
    """The tools the upstream itself marks as destructive.

    Read off the annotations rather than a list here, so the count on the screen
    is the upstream's own claim about itself and cannot drift from it.
    """
    return {t["name"] for t in tools
            if (t.get("annotations") or {}).get("destructiveHint")}
