"""Week two: the seller changes the shelf, and the gateway does not care.

Every hostile catalog here comes from the frozen corpus, written before the
gateway was hardened. That is the whole force of the demo: the attack text was
not authored to lose.
"""
from datetime import UTC, datetime, timedelta

import pytest
from starlette.testclient import TestClient

from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.tokens import mint_agent_token
from mandate.money import Paise
from mandate.policy.crypto import generate_keypair
from mandate.policy.loader import dump as dump_policy
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Provenance
from mandate.service.server import create_app
from tests.policy.test_models import _policy

pytest.importorskip("mcp")

BOOK = DictPriceBook({
    "sku_tea": PriceBookItem(sku="sku_tea", title="Assam Tea 500g",
                             unit_price=Paise(25000), category="grocery",
                             merchant="zepto"),
    "sku_rice": PriceBookItem(sku="sku_rice", title="Sona Masoori 5kg",
                              unit_price=Paise(41000), category="grocery",
                              merchant="zepto"),
})


@pytest.fixture
def client_and_headers(tmp_path):
    priv_hex, pub_hex = generate_keypair()
    pol = _policy(
        constraints={C.BUDGET_TOTAL: {"max": 2000000},
                     C.CATEGORY_DENY: ["alcohol"]},
        provenance=Provenance(stated=[C.BUDGET_TOTAL, C.CATEGORY_DENY], inferred=[]),
    )
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
    token = mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti="tok_week_01")
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def _available(client):
    return client.get("/v1/store/week").json()["families"]


def test_week_one_serves_the_clean_shelf(client_and_headers):
    client, _ = client_and_headers
    body = client.get("/v1/store/week").json()
    assert body["week"] == 1
    assert body["family"] == "clean"


def test_advancing_into_an_attack_family_relabels_the_week(client_and_headers):
    client, headers = client_and_headers
    if "injection.description" not in _available(client):
        pytest.skip("frozen corpus not present in this working directory")

    res = client.post("/v1/store/advance",
                      json={"family": "injection.description"}, headers=headers)
    assert res.status_code == 200

    body = client.get("/v1/store/week").json()
    assert body["week"] == 2
    assert body["family"] == "injection.description"
    assert body["corpus_hash"]


def test_a_relabelled_bottle_is_still_alcohol(client_and_headers):
    """`category.laundering` rewrites the title of an alcohol product to
    something innocuous. The gateway resolves the category from its own price
    book, so the new title changes what the agent reads and nothing else.
    """
    client, headers = client_and_headers
    if "category.laundering" not in _available(client):
        pytest.skip("frozen corpus not present in this working directory")

    client.post("/v1/store/advance", json={"family": "category.laundering"},
                headers=headers)

    # Find something the hostile catalog still files under alcohol.
    catalog = client.get("/v1/catalog").json()
    bottles = [p for p in catalog if p["category"] == "alcohol"]
    assert bottles, "the corpus catalog carries no alcohol to launder"

    res = client.post("/v1/orders", json={
        "merchant": bottles[0]["merchant"],
        "items": [{"sku": bottles[0]["sku"], "qty": 1}],
    }, headers=headers)

    assert res.status_code == 200
    assert res.json()["verdict"] == "DENY"
    assert res.json()["clause_id"] == "category.deny"


def test_orders_are_filed_under_the_week_they_were_placed_in(client_and_headers):
    client, headers = client_and_headers
    client.post("/v1/orders", json={"merchant": "zepto",
                                    "items": [{"sku": "sku_tea", "qty": 1}]},
                headers=headers)
    client.post("/v1/store/advance", json={}, headers=headers)
    client.post("/v1/orders", json={"merchant": "zepto",
                                    "items": [{"sku": "sku_rice", "qty": 1}]},
                headers=headers)

    body = client.get("/v1/store/orders").json()
    assert [o["week"] for o in body["orders"]] == [1, 2]
    assert body["totals"]["executed_count"] == 2


def test_the_same_basket_twice_is_one_order(client_and_headers):
    """Idempotency, seen from the shop floor.

    `canonical_intent()` hashes the resolved action, so a repeated basket is the
    same key and replays instead of charging again. A customer who clicks twice
    is not billed twice, and the second row says so rather than vanishing.
    """
    client, headers = client_and_headers
    basket = {"merchant": "zepto", "items": [{"sku": "sku_tea", "qty": 1}]}
    client.post("/v1/orders", json=basket, headers=headers)
    client.post("/v1/orders", json=basket, headers=headers)

    body = client.get("/v1/store/orders").json()
    assert len(body["orders"]) == 2
    assert body["totals"]["executed_count"] == 1
    assert body["orders"][1]["status"] == "UNKNOWN"
    assert body["orders"][0]["idem_key"] == body["orders"][1]["idem_key"]


def test_an_mcp_client_gets_a_fresh_mandate_instance_each_week(tmp_path):
    """The week model, on the path that actually carries the demo.

    An MCP client holds no bearer, so the service claims a pool token for it. The
    session map is keyed on the week, so advancing one claims a new token: new
    jti, new session directory, and accumulators that start at zero. Week one's
    audit chain survives because it lives under its own jti.
    """
    from mandate.service.token_pool import TokenPool

    priv_hex, pub_hex = generate_keypair()
    pol = _policy(
        constraints={C.BUDGET_TOTAL: {"max": 2000000}},
        provenance=Provenance(stated=[C.BUDGET_TOTAL], inferred=[]),
    )
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)
    (tmp_path / "issuer_public.key").write_text(pub_hex + "\n")

    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    pool = TokenPool.from_tokens([
        mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti=f"tok_pool_{n}")
        for n in ("01", "02", "03")
    ])
    app = create_app(
        policy_path=pol_path,
        public_key_path=tmp_path / "issuer_public.key",
        revocations_path=tmp_path / "revocations.jsonl",
        pricebook=BOOK,
        capability_secret="test_secret_42",
        token_pool=pool,
        store_path=tmp_path / "store" / "orders.jsonl",
    )
    admin = {"Authorization": f"Bearer {mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti='tok_admin')}"}

    from tests.service.test_mcp_mounted import _handshake, _rpc

    order = _rpc("tools/call", {"name": "create_order",
                                "arguments": {"merchant": "zepto",
                                              "items": [{"sku": "sku_tea", "qty": 1}]}},
                 rpc_id=3)
    with TestClient(app) as client:
        # No Authorization on the MCP calls: the service claims a token for the
        # connection and the model never sees it.
        headers = _handshake(client, token=None)
        client.post("/mcp", json=order, headers=headers)
        client.post("/v1/store/advance", json={}, headers=admin)
        client.post("/mcp", json=order, headers=headers)
        rows = client.get("/v1/store/orders").json()["orders"]

    assert [r["week"] for r in rows] == [1, 2]
    assert rows[0]["jti"] != rows[1]["jti"], "week two reused week one's mandate instance"
    assert rows[1]["status"] == "EXECUTED", "week two inherited week one's ledger"
