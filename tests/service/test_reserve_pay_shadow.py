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
from mandate.policy.rails import reserve_pay_exposure
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
def mgr_session(tmp_path):
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
    return mgr, mgr.create_session(tok, claims), tok


def test_a_shadow_carries_only_what_the_rail_can_hold(mgr_session):
    mgr, sess, _ = mgr_session
    shadow = mgr.shadow_for(sess, "zepto")
    assert set(shadow.policy.constraints) == {C.BUDGET_TOTAL, C.MERCHANT_ALLOW}


def test_a_shadow_is_opened_against_the_shop_being_used(mgr_session):
    """The block a user would actually have opened, not whichever payee sorts first.

    Narrowing to `payees[0]` made every order at another allowed shop refuse on
    the payee, so the comparison only ever said "the rail names one payee" and
    never reached the clauses the rail cannot express at all. That is why the
    console could not show the disagreement the shadow exists to show.
    """
    mgr, sess, _ = mgr_session
    assert mgr.shadow_for(sess, "blinkit").policy.constraints[C.MERCHANT_ALLOW] == ["blinkit"]
    assert mgr.shadow_for(sess, "zepto").policy.constraints[C.MERCHANT_ALLOW] == ["zepto"]


def test_a_payee_the_user_never_allowed_gets_no_block_of_its_own(mgr_session):
    """Falling back rather than inventing a block for a shop nobody authorised."""
    mgr, sess, _ = mgr_session
    shadow = mgr.shadow_for(sess, "some-shop-nobody-allowed")
    assert shadow.policy.constraints[C.MERCHANT_ALLOW] == ["zepto"]


def test_each_payee_gets_its_own_block_and_they_do_not_share_a_total(mgr_session):
    """Which is the cost, not a convenience: three blocks is three times the money."""
    mgr, sess, tok = mgr_session
    now = datetime.now(UTC)
    p = Proposal(type="create_order", merchant="zepto",
                 items=[ProposalItem(sku="sku_dal", qty=1)])
    mgr.shadow_for(sess, "zepto").propose(p, now=now, token=tok)

    assert int(mgr.shadow_for(sess, "zepto")._state().spent) == 20000
    assert int(mgr.shadow_for(sess, "blinkit")._state().spent) == 0


def test_the_shadow_never_writes_to_the_mandates_own_audit_chain(mgr_session):
    """The shadow's spend is not the mandate's spend. If it shared the chain, the
    signed record of what this mandate authorised would include orders no one
    ever authorised under it."""
    mgr, sess, tok = mgr_session
    p = Proposal(type="create_order", merchant="zepto",
                 items=[ProposalItem(sku="sku_dal", qty=1)])
    mgr.shadow_for(sess, "zepto").propose(p, now=datetime.now(UTC), token=tok)
    assert sess.audit.records() == []


def test_reserve_pay_lets_through_the_alcohol_the_mandate_refuses(mgr_session):
    """The rail never sees categories, so `category.deny` has nowhere to live on
    it. This is the money story, and it is the whole reason the shadow exists."""
    mgr, sess, tok = mgr_session
    p = Proposal(type="create_order", merchant="zepto",
                 items=[ProposalItem(sku="sku_gin", qty=1)])
    now = datetime.now(UTC)
    real = sess.gateway.propose(p, now=now, token=tok)
    shadow = mgr.shadow_for(sess, "zepto").propose(p, now=now, token=tok)

    assert real.verdict is Verdict.DENY and not real.executed
    assert shadow.verdict is Verdict.ALLOW and shadow.executed


def test_the_attack_gets_through_at_every_allowed_shop_not_just_the_first(mgr_session):
    """The bug this change fixes, pinned so it cannot come back.

    Every attack preset in the console orders from `blinkit`. With one block
    narrowed to `payees[0]` the shadow refused all of them on the payee, so the
    "the rail would have let this through" branch could never fire and the
    strongest thing on the screen was unreachable.
    """
    mgr, sess, tok = mgr_session
    now = datetime.now(UTC)
    p = Proposal(type="create_order", merchant="blinkit",
                 items=[ProposalItem(sku="sku_gin", qty=1)])
    real = sess.gateway.propose(p, now=now, token=tok)
    shadow = mgr.shadow_for(sess, "blinkit").propose(p, now=now, token=tok)

    assert real.verdict is Verdict.DENY, "the mandate refuses alcohol anywhere"
    assert shadow.verdict is Verdict.ALLOW and shadow.executed


def test_one_block_still_over_blocks_the_shops_it_does_not_name(mgr_session):
    """The other half of the gap, and it must not be dropped.

    Per-payee blocks fix the demo, and they do it by spending more of the user's
    money. Modelled as the single block a user is likelier to actually open, the
    rail refuses a shop the mandate allows. Both readings are true and neither
    equals the mandate, which is the finding.
    """
    mgr, sess, tok = mgr_session
    p = Proposal(type="create_order", merchant="blinkit",
                 items=[ProposalItem(sku="sku_dal", qty=1)])
    now = datetime.now(UTC)
    real = sess.gateway.propose(p, now=now, token=tok)
    one_block = mgr.shadow_for(sess, None)     # falls back to the first payee

    assert real.verdict is Verdict.ALLOW and real.executed
    assert one_block.propose(p, now=now, token=tok).verdict is Verdict.DENY


def test_the_cost_of_covering_every_shop_is_reported(mgr_session):
    """Rs 2,000 of stated intent becomes Rs 6,000 of blocked funds."""
    _mgr, sess, _ = mgr_session
    exposure = reserve_pay_exposure(sess.gateway.policy)
    assert exposure.payees == 3
    assert int(exposure.mandate_cap) == 200000
    assert exposure.blocks_needed == 3
    assert int(exposure.blocked_total) == 600000
    assert exposure.refused_payees == ["blinkit", "instamart"]
