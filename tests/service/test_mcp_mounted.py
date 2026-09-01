"""The MCP surface is reachable over HTTP from the same app as everything else.

One deploy, one URL, one process. A judge adds the Cloud Run URL to their own MCP
client and shops through the gateway with a client this repo never saw.
"""
import json
from datetime import UTC, datetime, timedelta

import pytest
from mcp.types import LATEST_PROTOCOL_VERSION
from starlette.testclient import TestClient

from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.tokens import mint_agent_token
from mandate.money import Paise
from mandate.policy.crypto import generate_keypair
from mandate.policy.loader import dump as dump_policy
from mandate.service.server import create_app
from tests.policy.test_models import _policy

MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
BOOK = DictPriceBook({
    "sku_tea": PriceBookItem(sku="sku_tea", title="Assam Tea 500g",
                             unit_price=Paise(25000), category="grocery",
                             merchant="zepto"),
})


def _rpc(method, params=None, rpc_id=1):
    body = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if rpc_id is not None:
        body["id"] = rpc_id
    return body


def _payload(res):
    """One JSON-RPC response, from either an SSE body or a plain JSON one."""
    if res.headers.get("content-type", "").startswith("text/event-stream"):
        for line in res.text.splitlines():
            if line.startswith("data: "):
                return json.loads(line[6:])
        raise AssertionError(f"no data frame in {res.text!r}")
    return res.json()


@pytest.fixture
def app_and_token(tmp_path):
    priv_hex, pub_hex = generate_keypair()
    pol = _policy()
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)
    (tmp_path / "issuer_public.key").write_text(pub_hex + "\n")

    app = create_app(
        policy_path=pol_path,
        public_key_path=tmp_path / "issuer_public.key",
        revocations_path=tmp_path / "revocations.jsonl",
        pricebook=BOOK,
        capability_secret="test_secret_42",
        store_path=tmp_path / "store" / "orders.jsonl",
    )
    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    token = mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti="tok_mcp_http")
    return app, token


def _handshake(client, token):
    """initialize, then the initialized notification. Returns the session headers.

    `token=None` drives the path a real MCP client takes: no bearer, so the
    service claims a pool token for the connection and the model never sees it.
    """
    headers = dict(MCP_HEADERS)
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    res = client.post("/mcp", json=_rpc("initialize", {
        "protocolVersion": LATEST_PROTOCOL_VERSION,
        "capabilities": {},
        "clientInfo": {"name": "pytest", "version": "1"},
    }), headers=headers)
    assert res.status_code == 200, res.text

    session_id = res.headers.get("mcp-session-id")
    assert session_id, "the server issued no MCP session id"
    headers["mcp-session-id"] = session_id

    client.post("/mcp", json=_rpc("notifications/initialized", rpc_id=None),
                headers=headers)
    return headers


def test_the_six_tools_are_listed_over_http(app_and_token):
    from mandate.adapters.mcp_server import TOOL_NAMES

    app, token = app_and_token
    with TestClient(app) as client:
        headers = _handshake(client, token)
        res = client.post("/mcp", json=_rpc("tools/list", rpc_id=2), headers=headers)
        payload = _payload(res)

    assert {t["name"] for t in payload["result"]["tools"]} == set(TOOL_NAMES)


def test_an_order_placed_over_mcp_reaches_the_storefront(app_and_token):
    """The whole point. A client that never touched /v1/orders moves money, and
    the customer's order history shows it."""
    app, token = app_and_token
    with TestClient(app) as client:
        headers = _handshake(client, token)
        res = client.post("/mcp", json=_rpc("tools/call", {
            "name": "create_order",
            "arguments": {"merchant": "zepto", "items": [{"sku": "sku_tea", "qty": 2}]},
        }, rpc_id=3), headers=headers)
        payload = _payload(res)

        assert payload["result"]["isError"] is False
        rows = client.get("/v1/store/orders").json()["orders"]

    assert len(rows) == 1
    assert rows[0]["source"] == "mcp"
    assert rows[0]["status"] == "EXECUTED"
    assert rows[0]["amount_paise"] == 50000


def test_the_mcp_route_does_not_shadow_the_rest_of_the_service(app_and_token):
    app = app_and_token[0]
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/v1/catalog").status_code == 200


def test_the_service_still_works_without_entering_the_lifespan(app_and_token):
    """Every existing service test drives `TestClient(app)` bare, which never runs
    a lifespan. Adding one for the MCP session manager must not break them."""
    app = app_and_token[0]
    assert TestClient(app).get("/health").status_code == 200
