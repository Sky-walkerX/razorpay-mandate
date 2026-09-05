"""The AFA approval loop, driven the whole way round.

`afa.required` is the clause `/rails` singles out: RBI requires it and neither AP2
nor Reserve Pay can carry it, so the gateway holds it because the rails cannot. It
had never fired anywhere in the product.

  - On the signed mandate it is structurally unreachable. `budget.total` is Rs 2,000
    and the statutory threshold is Rs 15,000, and DENY outranks UNKNOWN, so any order
    large enough to need an additional factor is refused on a budget clause first.
  - On a visitor's mandate it was simply absent, because the compiler never emits it
    and nothing put it back.

So the only place the loop can run is a mandate whose caps a visitor set above the
threshold, which is why the sandbox session issues a principal key.
"""
import json
from datetime import UTC, datetime, timedelta

from starlette.testclient import TestClient

from mandate.gateway.pricebook import DictPriceBook
from mandate.gateway.tokens import mint_agent_token
from mandate.harness.catalog import generate_catalog
from mandate.policy.crypto import generate_keypair
from mandate.policy.loader import dump as dump_policy
from mandate.policy.models import ConstraintId, Provenance
from mandate.policy.regulatory import AFA_THRESHOLD_PAISE
from mandate.service.sandbox import SANDBOX_JTI_PREFIX, SANDBOX_MANDATE_ID
from mandate.service.server import create_app
from mandate.service.token_pool import TokenPool
from tests.policy.test_models import _policy

#: A visitor who authorises far more than the statutory threshold. Nothing here
#: mentions an additional factor, because nobody dictating an intent ever does.
RICH_READING = {
    "constraints": {
        "budget.total": {"max": 20_000_000},
        "budget.per_transaction": {"max": 5_000_000},
        "budget.per_item": {"max": 5_000_000},
    },
    "provenance": {
        "stated": ["budget.total", "budget.per_transaction", "budget.per_item"],
        "inferred": [],
    },
    "questions": [],
}

def _qty_over_the_floor(item) -> int:
    """Enough units of this item to clear Rs 15,000, whatever the catalog prices it at.

    Hardcoding a quantity ties the test to today's generated prices: 60 units cleared
    the floor for one SKU and not for another, which is a fixture failing rather than
    a property failing.
    """
    return -(-int(AFA_THRESHOLD_PAISE * 12 // 10) // int(item.unit_price))


class _Scripted:
    model = "scripted-test"

    def next_text(self, system, history):
        return json.dumps(RICH_READING)


def _app(tmp_path, monkeypatch):
    tmp_path.mkdir(parents=True, exist_ok=True)
    catalog = generate_catalog(seed=42)
    priv_hex, pub_hex = generate_keypair()
    pol = _policy(
        constraints={ConstraintId.BUDGET_TOTAL: {"max": 200000}},
        provenance=Provenance(stated=[ConstraintId.BUDGET_TOTAL], inferred=[]),
    )
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)
    pub_path = tmp_path / "issuer_public.key"
    pub_path.write_text(pub_hex + "\n")

    monkeypatch.setattr("mandate.llm.provider_for", lambda *a, **k: _Scripted())

    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    app = create_app(
        policy_path=pol_path, public_key_path=pub_path,
        revocations_path=tmp_path / "revocations.jsonl",
        audit_path=tmp_path / "audit.jsonl", ledger_path=tmp_path / "ledger.jsonl",
        pricebook=DictPriceBook.from_catalog(catalog),
        capability_secret="test_secret_42", catalog=catalog,
        approval_store_path=tmp_path / "approvals.jsonl",
        token_pool=TokenPool([
            mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti="tok_pool_001")
        ]),
        sandbox_pool=TokenPool([
            mint_agent_token(
                SANDBOX_MANDATE_ID, priv_hex, expires_iso=exp,
                jti=f"{SANDBOX_JTI_PREFIX}_001",
            )
        ]),
    )
    return TestClient(app), catalog


def _dear_item(catalog):
    """The dearest thing the visitor's mandate allows, so ORDER_QTY clears the floor."""
    return max(
        (p for p in catalog.products if p.category not in ("alcohol", "tobacco")),
        key=lambda p: int(p.unit_price),
    )


def test_the_whole_approval_loop(tmp_path, monkeypatch):
    client, catalog = _app(tmp_path, monkeypatch)
    sbx = client.post("/v1/sandbox", json={"prompt": "Spend up to Rs 50,000 an order"}).json()
    assert sbx["compiled"] is True

    agent = {"Authorization": f"Bearer {sbx['token']}"}
    principal = {"X-Principal-Key": sbx["principal_key"]}
    item = _dear_item(catalog)
    qty = _qty_over_the_floor(item)
    basket = {"merchant": item.merchant, "items": [{"sku": item.sku, "qty": qty}]}
    assert int(item.unit_price) * qty > AFA_THRESHOLD_PAISE

    # 1. Held, not refused. The order is not forbidden, it is unauthorised so far.
    first = client.post("/v1/orders", json=basket, headers=agent).json()
    assert first["verdict"] == "UNKNOWN"
    assert first["clause_id"] == "afa.required"
    assert first["executed"] is False

    # 2. The ref is the credential for this order, and the agent must never hold it.
    ref_seen_by_agent = json.dumps(first)
    assert "approval" not in ref_seen_by_agent.lower() or "ref" not in first

    # 3. The agent's own credential does not open the principal's channel.
    denied = client.get("/v1/pending", headers=agent)
    assert denied.status_code == 401

    # 4. The principal's does, and only theirs carries the ref.
    queue = client.get("/v1/pending", headers=principal).json()["pending"]
    assert len(queue) == 1
    ref = queue[0]["ref"]
    assert ref and ref not in ref_seen_by_agent

    # 5. Approving that one basket releases that one basket.
    approved = client.post("/v1/approve", json={"ref": ref, "decision": "approve"})
    assert approved.status_code == 200

    retry = client.post("/v1/orders", json=basket, headers=agent).json()
    assert retry["verdict"] == "ALLOW"
    assert retry["executed"] is True


def test_a_different_basket_of_the_same_value_is_not_released(tmp_path, monkeypatch):
    """`ApprovalStore` keys on the canonical intent hash of the resolved action.

    Keyed on the amount instead, approving one basket would release any basket of
    equal value, which is the whole reason the docstring on `approval.py` says not
    to "simplify" it to an amount comparison.
    """
    client, catalog = _app(tmp_path, monkeypatch)
    sbx = client.post("/v1/sandbox", json={"prompt": "Spend up to Rs 50,000 an order"}).json()
    agent = {"Authorization": f"Bearer {sbx['token']}"}
    principal = {"X-Principal-Key": sbx["principal_key"]}

    item = _dear_item(catalog)
    other = max(
        (p for p in catalog.products
         if p.sku != item.sku and p.category not in ("alcohol", "tobacco")),
        key=lambda p: int(p.unit_price),
    )

    client.post(
        "/v1/orders",
        json={"merchant": item.merchant, "items": [{"sku": item.sku, "qty": _qty_over_the_floor(item)}]},
        headers=agent,
    )
    ref = client.get("/v1/pending", headers=principal).json()["pending"][0]["ref"]
    client.post("/v1/approve", json={"ref": ref, "decision": "approve"})

    # A different SKU, still above the threshold, never approved.
    swapped = client.post(
        "/v1/orders",
        json={"merchant": other.merchant, "items": [{"sku": other.sku, "qty": _qty_over_the_floor(other)}]},
        headers=agent,
    ).json()
    assert swapped["verdict"] == "UNKNOWN"
    assert swapped["executed"] is False


def test_the_signed_mandate_can_never_reach_the_threshold(tmp_path, monkeypatch):
    """Stated so it is a known property rather than a surprise on stage.

    The house mandate carries `afa.required` and cannot fire it: every basket large
    enough breaches a budget clause first, and DENY outranks UNKNOWN. That is why
    the loop above runs on a visitor's mandate.
    """
    client, catalog = _app(tmp_path, monkeypatch)
    house = client.post("/v1/sessions").json()
    agent = {"Authorization": f"Bearer {house['token']}"}
    item = _dear_item(catalog)

    body = client.post(
        "/v1/orders",
        json={"merchant": item.merchant, "items": [{"sku": item.sku, "qty": _qty_over_the_floor(item)}]},
        headers=agent,
    ).json()
    assert body["verdict"] == "DENY"
    assert body["clause_id"] != "afa.required"
