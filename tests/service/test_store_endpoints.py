"""The storefront's read surface.

The order history is deliberately unauthenticated: it is a shop's own list of
what it sold, exposes no token and no capability, and requiring a bearer would
mean the page claims a pool token just to render. Advancing the week writes, so
that one is gated like `/v1/revoke`.
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

BOOK = DictPriceBook({
    "sku_tea": PriceBookItem(sku="sku_tea", title="Assam Tea 500g",
                             unit_price=Paise(25000), category="grocery",
                             merchant="zepto"),
    "sku_gin": PriceBookItem(sku="sku_gin", title="Dry Gin 750ml",
                             unit_price=Paise(180000), category="alcohol",
                             merchant="zepto"),
})


@pytest.fixture
def client_and_headers(tmp_path):
    priv_hex, pub_hex = generate_keypair()
    # The default test policy carries budget.total alone, under which a bottle of
    # gin is a perfectly legal grocery order. category.deny is what makes the
    # refusal in these tests a refusal.
    pol = _policy(
        constraints={C.BUDGET_TOTAL: {"max": 200000}, C.CATEGORY_DENY: ["alcohol"]},
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
    token = mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti="tok_store_01")
    return TestClient(app), {"Authorization": f"Bearer {token}"}


def _order(client, headers, sku="sku_tea", qty=1):
    return client.post("/v1/orders",
                       json={"merchant": "zepto", "items": [{"sku": sku, "qty": qty}]},
                       headers=headers)


def test_an_order_reaches_the_storefront(client_and_headers):
    client, headers = client_and_headers
    assert _order(client, headers).status_code == 200

    body = client.get("/v1/store/orders").json()
    assert len(body["orders"]) == 1
    row = body["orders"][0]
    assert row["status"] == "EXECUTED"
    assert row["merchant"] == "zepto"
    assert row["amount_paise"] == 25000
    assert row["items"][0]["title"] == "Assam Tea 500g"


def test_the_amount_shown_is_the_one_the_gateway_resolved(client_and_headers):
    """An agent naming a price gets it discarded. The storefront must show what
    the rail was told, not what was asked for."""
    client, headers = client_and_headers
    client.post("/v1/orders", json={
        "merchant": "zepto",
        "items": [{"sku": "sku_tea", "qty": 2, "unit_price": 1, "title": "Free Tea"}],
    }, headers=headers)

    row = client.get("/v1/store/orders").json()["orders"][0]
    assert row["amount_paise"] == 50000
    assert row["items"][0]["title"] == "Assam Tea 500g"


def test_a_refusal_is_listed_with_its_clause(client_and_headers):
    client, headers = client_and_headers
    _order(client, headers, sku="sku_gin")

    row = client.get("/v1/store/orders").json()["orders"][0]
    assert row["status"] == "REFUSED"
    assert row["clause_id"] == "category.deny"
    assert row["downstream_id"] is None


def test_the_order_history_needs_no_bearer(client_and_headers):
    client, _ = client_and_headers
    assert client.get("/v1/store/orders").status_code == 200
    assert client.get("/v1/store/week").status_code == 200


def test_advancing_the_week_needs_a_bearer(client_and_headers):
    client, headers = client_and_headers
    assert client.post("/v1/store/advance", json={}).status_code == 401
    assert client.post("/v1/store/advance", json={}, headers=headers).status_code == 200


def test_a_new_week_does_not_disturb_the_last_one(client_and_headers):
    client, headers = client_and_headers
    _order(client, headers)
    client.post("/v1/store/advance", json={"family": "injection.description"},
                headers=headers)
    _order(client, headers, qty=2)

    assert client.get("/v1/store/week").json()["week"] == 2
    assert client.get("/v1/store/week").json()["family"] == "injection.description"

    week_one = client.get("/v1/store/orders?week=1").json()
    assert [o["amount_paise"] for o in week_one["orders"]] == [25000]
    week_two = client.get("/v1/store/orders?week=2").json()
    assert [o["amount_paise"] for o in week_two["orders"]] == [50000]


def test_an_unknown_family_is_refused(client_and_headers):
    """Advancing into a family the corpus does not carry would leave the store
    labelled with an attack that never loads."""
    client, headers = client_and_headers
    res = client.post("/v1/store/advance", json={"family": "not.a.family"},
                      headers=headers)
    assert res.status_code == 400
    assert client.get("/v1/store/week").json()["week"] == 1


def test_totals_count_what_moved_and_what_did_not(client_and_headers):
    client, headers = client_and_headers
    _order(client, headers)
    _order(client, headers, sku="sku_gin")

    totals = client.get("/v1/store/orders").json()["totals"]
    assert totals["executed_paise"] == 25000
    assert totals["executed_count"] == 1
    assert totals["refused_count"] == 1


def test_the_etag_lets_the_page_poll_cheaply(client_and_headers):
    client, headers = client_and_headers
    first = client.get("/v1/store/orders")
    tag = first.headers["etag"]

    unchanged = client.get("/v1/store/orders", headers={"If-None-Match": tag})
    assert unchanged.status_code == 304

    _order(client, headers)
    changed = client.get("/v1/store/orders", headers={"If-None-Match": tag})
    assert changed.status_code == 200
    assert changed.headers["etag"] != tag


def test_the_week_reports_the_frozen_corpus_it_draws_from(client_and_headers):
    """The force of a hostile week is that the text predates the gateway. A page
    claiming that should name the corpus it came from."""
    client, _ = client_and_headers
    body = client.get("/v1/store/week").json()
    assert "corpus_hash" in body
    assert set(body["families"]) >= {"clean"}
