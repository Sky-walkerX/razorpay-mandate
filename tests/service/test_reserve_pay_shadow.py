"""The shadow answers every proposal as UPI Reserve Pay would.

Razorpay already ships spending limits for agents on Reserve Pay, so "we cap
what an agent can spend" is not a claim worth making. The claim worth making is
that a block against one payee is the wrong *shape* for a stated intent, in both
directions: it lets an attack through that the mandate refuses, and it refuses a
legitimate order at a second shop that the mandate allows.

The shadow is a real `Gateway` on a projected policy, never a second evaluator.
A demo-only path would let the comparison keep working while the gateway broke.
"""
from datetime import UTC, datetime, timedelta

import pytest

from mandate.downstream.fake import FakeDownstream
from mandate.gateway.action import Proposal, ProposalItem
from mandate.gateway.core import Verdict
from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.revocation import RevocationList
from mandate.gateway.tokens import mint_agent_token, verify_agent_token
from mandate.money import Paise
from mandate.policy.crypto import generate_keypair
from mandate.policy.models import CompilerInfo, Policy, Provenance
from mandate.policy.models import ConstraintId as C
from mandate.service.session import SessionManager


def _pricebook() -> DictPriceBook:
    return DictPriceBook({
        "sku_dal": PriceBookItem(sku="sku_dal", title="Toor Dal 1kg",
                                 unit_price=Paise(20000), category="grocery",
                                 merchant="zepto"),
        "sku_gin": PriceBookItem(sku="sku_gin", title="Gin 750ml",
                                 unit_price=Paise(23600), category="alcohol",
                                 merchant="zepto"),
    })


def _policy() -> Policy:
    now = datetime.now(UTC)
    return Policy(
        mandate_id="mnd_shadow_01", principal="user_1", agent="agt_1",
        issued=now - timedelta(hours=1), expires=now + timedelta(days=30),
        constraints={
            C.BUDGET_TOTAL: {"max": 200000},
            C.CATEGORY_DENY: ["alcohol"],
            C.MERCHANT_ALLOW: ["zepto", "blinkit", "instamart"],
        },
        provenance=Provenance(
            stated=[C.BUDGET_TOTAL, C.CATEGORY_DENY, C.MERCHANT_ALLOW], inferred=[]
        ),
        source_text="groceries under 2000, nothing alcoholic",
        compiler=CompilerInfo(model="test", temperature=0.0, version="1.0.0"),
    )


@pytest.fixture
def session(tmp_path):
    priv, pub = generate_keypair()
    pol = _policy()
    mgr = SessionManager(
        policy=pol, pricebook=_pricebook(), downstream=FakeDownstream(),
        capability_secret="s", issuer_public_key=pub,
        revocations=RevocationList(tmp_path / "rev.jsonl"),
        base_dir=tmp_path / "sessions",
    )
    tok = mint_agent_token(
        mandate_id=pol.mandate_id, private_key_hex=priv,
        expires_iso=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        jti="tok_shadow_1",
    )
    claims = verify_agent_token(tok, pub)
    return mgr.create_session(tok, claims), tok


def test_a_session_carries_a_shadow_on_the_projected_policy(session):
    sess, _ = session
    assert set(sess.shadow.policy.constraints) == {C.BUDGET_TOTAL, C.MERCHANT_ALLOW}


def test_the_shadow_never_writes_to_the_mandates_own_audit_chain(session):
    """The shadow's spend is not the mandate's spend. If it shared the chain, the
    signed record of what this mandate authorised would include orders no one
    ever authorised under it."""
    sess, tok = session
    p = Proposal(type="create_order", merchant="zepto",
                 items=[ProposalItem(sku="sku_dal", qty=1)])
    sess.shadow.propose(p, now=datetime.now(UTC), token=tok)
    assert sess.audit.records() == []


def test_reserve_pay_lets_through_the_alcohol_the_mandate_refuses(session):
    """The rail never sees categories, so `category.deny` has nowhere to live on
    it. This is the money story, and it is the whole reason the shadow exists."""
    sess, tok = session
    p = Proposal(type="create_order", merchant="zepto",
                 items=[ProposalItem(sku="sku_gin", qty=1)])
    now = datetime.now(UTC)
    real = sess.gateway.propose(p, now=now, token=tok)
    shadow = sess.shadow.propose(p, now=now, token=tok)

    assert real.verdict is Verdict.DENY and not real.executed
    assert shadow.verdict is Verdict.ALLOW and shadow.executed


def test_reserve_pay_refuses_a_second_shop_the_mandate_allows(session):
    """A block names one payee. So the rail is not merely weaker than the mandate,
    it is a different shape: it over-blocks legitimate multi-shop buying while
    under-blocking the attack above. Stating only the first half would overstate
    the gap, which is the failure `rails.py` exists to avoid."""
    sess, tok = session
    p = Proposal(type="create_order", merchant="blinkit",
                 items=[ProposalItem(sku="sku_dal", qty=1)])
    now = datetime.now(UTC)
    real = sess.gateway.propose(p, now=now, token=tok)
    shadow = sess.shadow.propose(p, now=now, token=tok)

    assert real.verdict is Verdict.ALLOW and real.executed
    assert shadow.verdict is Verdict.DENY and not shadow.executed


def _app(tmp_path):
    from starlette.testclient import TestClient

    from mandate.policy.loader import dump as dump_policy
    from mandate.service.server import create_app
    from mandate.service.token_pool import TokenPool

    priv, pub = generate_keypair()
    pol = _policy()
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv)
    pub_path = tmp_path / "issuer_public.key"
    pub_path.write_text(pub + "\n")

    exp = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    pool = TokenPool([
        mint_agent_token(pol.mandate_id, priv, expires_iso=exp, jti=f"tok_rp_{i:02d}")
        for i in range(1, 4)
    ])
    app = create_app(
        policy_path=pol_path, public_key_path=pub_path,
        revocations_path=tmp_path / "rev.jsonl",
        audit_path=tmp_path / "audit.jsonl", ledger_path=tmp_path / "ledger.jsonl",
        pricebook=_pricebook(), capability_secret="shadow_secret_2026",
        token_pool=pool,
    )
    return TestClient(app)


def test_the_order_response_says_what_reserve_pay_would_have_done(tmp_path):
    client = _app(tmp_path)
    tok = client.post("/v1/sessions").json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}

    r = client.post("/v1/orders",
                    json={"merchant": "zepto", "items": [{"sku": "sku_gin", "qty": 1}]},
                    headers=hdr)
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "DENY"
    assert body["reserve_pay"]["verdict"] == "ALLOW"


def test_a_broken_shadow_never_changes_the_real_verdict(tmp_path, monkeypatch):
    """The shadow is a talking point; the gateway is the product. If projecting
    the policy ever raises, the order must still be decided and answered, with
    the comparison simply absent rather than a 500 over a real ALLOW."""
    from mandate.service import server as server_mod

    def boom(*a, **k):
        raise RuntimeError("shadow exploded")

    monkeypatch.setattr(server_mod, "_reserve_pay_shadow", boom)

    client = _app(tmp_path)
    tok = client.post("/v1/sessions").json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}

    r = client.post("/v1/orders",
                    json={"merchant": "zepto", "items": [{"sku": "sku_dal", "qty": 1}]},
                    headers=hdr)
    assert r.status_code == 200
    assert r.json()["verdict"] == "ALLOW"
    assert r.json()["reserve_pay"] is None
