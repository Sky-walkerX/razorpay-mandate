"""`GET /v1/quote` is the shop speaking, and the gateway must not hold its key.

The demo plays two roles from one process because a stage cannot run three daemons.
They are separated by the key, not by the process, so the separation is only as real
as the test that pins it.
"""
import inspect
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from mandate.gateway.core import Gateway
from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.quote import MerchantKeyring
from mandate.gateway.tokens import mint_agent_token
from mandate.money import Paise
from mandate.policy.crypto import generate_keypair
from mandate.policy.loader import dump as dump_policy
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Provenance
from mandate.service.server import create_app
from mandate.service.shop import Shop, ShopUnavailable
from mandate.service.token_pool import TokenPool
from tests.policy.test_models import IST, _policy

#: Rs 400 list. At the shop's 1.7x this signs at Rs 680, which clears the Rs 500
#: per-item cap below -- the surge is what breaks the limit, not the list price.
LIST_PAISE = 40000
PER_ITEM_CAP = 50000


def _pricebook() -> DictPriceBook:
    return DictPriceBook({
        "sku_oil": PriceBookItem(
            sku="sku_oil", title="Olive Oil 1L", unit_price=Paise(LIST_PAISE),
            category="grocery", merchant="zepto",
        )
    })


@pytest.fixture
def shop_keys(tmp_path: Path) -> tuple[Path, str]:
    """A merchant keypair, split the way the two roles are split."""
    merchant_priv, merchant_pub = generate_keypair()
    keyring_path = tmp_path / "merchants.json"
    MerchantKeyring({"zepto": [merchant_pub]}).save(keyring_path)
    return keyring_path, json.dumps({"zepto": merchant_priv})


def _app(tmp_path: Path, keyring_path: Path, monkeypatch, shop_keys_json: str):
    priv_hex, pub_hex = generate_keypair()
    pol = _policy(
        constraints={
            C.BUDGET_TOTAL: {"max": 500000},
            C.BUDGET_PER_ITEM: {"max": PER_ITEM_CAP},
        },
        provenance=Provenance(stated=[C.BUDGET_TOTAL, C.BUDGET_PER_ITEM], inferred=[]),
        expires=datetime.now(IST) + timedelta(days=2),
    )
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)
    pub_path = tmp_path / "issuer_public.key"
    pub_path.write_text(pub_hex + "\n")

    # The shop reads its key from the environment here, which is the path a
    # deployment takes: the image cannot carry a file whose name says "private".
    monkeypatch.setenv("MANDATE_SHOP_PRIVATE_KEYS", shop_keys_json)

    return create_app(
        policy_path=pol_path,
        public_key_path=pub_path,
        revocations_path=tmp_path / "revocations.jsonl",
        audit_path=tmp_path / "audit.jsonl",
        ledger_path=tmp_path / "ledger.jsonl",
        pricebook=_pricebook(),
        capability_secret="secret_test_42",
        merchant_keys_path=keyring_path,
        token_pool=TokenPool.from_tokens([
            mint_agent_token(
                pol.mandate_id, priv_hex,
                expires_iso=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                jti="tok_shop_quote",
            )
        ]),
    )


def test_the_gateway_never_reads_a_merchant_private_key():
    """The separation the whole quote feature rests on.

    If a gateway could reach a signing key it would be able to mint the quotes it
    verifies, and `quote.forge` would be testing a component against itself. This
    asserts on the type rather than on one instance, so it holds for every gateway
    the service builds.
    """
    assert not hasattr(Gateway, "shop")
    keyring = MerchantKeyring({"zepto": ["ab" * 32]})
    assert not hasattr(keyring, "sign")
    assert not hasattr(keyring, "mint_quote")
    # The keyring's whole public surface, and none of it yields a private key.
    for name, member in inspect.getmembers(MerchantKeyring, inspect.isfunction):
        assert "private" not in name, f"MerchantKeyring.{name} sounds like a private key"
        assert "sign" not in name, f"MerchantKeyring.{name} sounds like signing"
        assert member is not None

    gw_source = inspect.getsource(Gateway)
    assert "mint_quote" not in gw_source, "the gateway must verify quotes, never mint them"


def test_the_shop_signs_its_own_price_and_the_gateway_honours_it(
    tmp_path: Path, shop_keys, monkeypatch
):
    keyring_path, shop_keys_json = shop_keys
    client = TestClient(_app(tmp_path, keyring_path, monkeypatch, shop_keys_json))
    session = client.post("/v1/sessions").json()
    headers = {"Authorization": f"Bearer {session['token']}"}

    q = client.get("/v1/quote?sku=sku_oil", headers=headers)
    assert q.status_code == 200, q.text
    body = q.json()
    assert body["list_price_paise"] == LIST_PAISE
    # The markup is stated, not hidden inside the price.
    assert body["unit_price_paise"] == round(LIST_PAISE * body["surge_factor"])
    assert body["unit_price_paise"] > PER_ITEM_CAP

    # The surged price is over the per-item cap, so the order is refused -- at the
    # price the shop signed, not the one on the list. A gateway checking the list
    # price would allow this and then hand the rail the surged figure.
    res = client.post(
        "/v1/orders",
        json={"merchant": "zepto",
              "items": [{"sku": "sku_oil", "qty": 1, "quote": body["quote"]}]},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    decision = res.json()
    assert decision["verdict"] == "DENY"
    assert decision["clause_id"] == "budget.per_item"
    assert not decision["executed"]

    breached = [c for c in decision["record"]["clauses"] if c["id"] == "budget.per_item"]
    assert breached[0]["observed"] == body["unit_price_paise"], (
        "the refusal must quote the signed price, not the list price"
    )


def test_the_shop_will_not_sign_a_price_the_caller_names(tmp_path: Path, shop_keys, monkeypatch):
    """The caller names the item; the shop names the price.

    A shop that signed whatever figure it was handed would be a signing oracle, and
    an agent could mint its own Rs 1,900 quote through the front door instead of
    forging one -- which would hollow out every quote attack in the suite.
    """
    keyring_path, shop_keys_json = shop_keys
    client = TestClient(_app(tmp_path, keyring_path, monkeypatch, shop_keys_json))
    session = client.post("/v1/sessions").json()
    headers = {"Authorization": f"Bearer {session['token']}"}

    asked = client.get(
        "/v1/quote?sku=sku_oil&unit_price_paise=1&amount=1&price=1", headers=headers
    ).json()
    assert asked["unit_price_paise"] == round(LIST_PAISE * asked["surge_factor"])


def test_a_deployment_with_no_shop_key_refuses_rather_than_inventing_a_quote(
    tmp_path: Path, shop_keys, monkeypatch
):
    """Prefer the loud failure. This is the /v1/compile lesson at another endpoint."""
    keyring_path, _ = shop_keys
    client = TestClient(_app(tmp_path, keyring_path, monkeypatch, ""))
    session = client.post("/v1/sessions").json()
    headers = {"Authorization": f"Bearer {session['token']}"}

    res = client.get("/v1/quote?sku=sku_oil", headers=headers)
    assert res.status_code == 503
    assert res.json()["error"] == "shop_unavailable"
    assert "quote" not in res.json(), "a refusal must not carry a quote"


def test_an_unknown_sku_is_a_404_and_not_a_signed_price(tmp_path: Path, shop_keys, monkeypatch):
    keyring_path, shop_keys_json = shop_keys
    client = TestClient(_app(tmp_path, keyring_path, monkeypatch, shop_keys_json))
    session = client.post("/v1/sessions").json()
    headers = {"Authorization": f"Bearer {session['token']}"}

    res = client.get("/v1/quote?sku=sku_not_stocked", headers=headers)
    assert res.status_code == 404
    assert "quote" not in res.json()


def test_the_quote_endpoint_needs_the_agent_token(tmp_path: Path, shop_keys, monkeypatch):
    keyring_path, shop_keys_json = shop_keys
    client = TestClient(_app(tmp_path, keyring_path, monkeypatch, shop_keys_json))
    assert client.get("/v1/quote?sku=sku_oil").status_code == 401


def test_the_shop_reads_its_file_before_the_environment(tmp_path: Path, monkeypatch):
    """File first, then environment, matching the log signing key.

    Locally the key you just generated wins over a stale exported variable.
    """
    from_file, _ = generate_keypair()
    from_env, _ = generate_keypair()
    key_path = tmp_path / "shop_private.json"
    key_path.write_text(json.dumps({"zepto": from_file}), encoding="utf-8")
    monkeypatch.setenv("MANDATE_SHOP_PRIVATE_KEYS", json.dumps({"zepto": from_env}))

    shop = Shop.from_environment(key_path)
    assert shop.can_quote("zepto")
    # Signed by the file's key, so the file won.
    quoted = shop.quote("zepto", "sku_oil", _pricebook())
    ring = MerchantKeyring({"zepto": [generate_keypair()[1]]})
    assert quoted["quote"], "a quote was produced"
    assert not ring.has_merchant("nobody")

    shop_env_only = Shop.from_environment(tmp_path / "absent.json")
    assert shop_env_only.can_quote("zepto")

    with pytest.raises(ShopUnavailable):
        Shop(private_keys={}).quote("zepto", "sku_oil", _pricebook())
