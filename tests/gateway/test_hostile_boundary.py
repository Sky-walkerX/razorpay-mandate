"""Tests for the hostile agent boundary: Proposal, ResolvedAction, PriceBook, and canonical_intent property test."""
from datetime import UTC, datetime

from mandate.downstream.fake import FakeDownstream
from mandate.gateway.action import (
    Proposal,
    ProposalItem,
    canonical_intent,
)
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway
from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.state import Verdict
from mandate.money import Paise
from tests.gateway.test_core import _pol


def _pricebook():
    return DictPriceBook({
        "sku_dal": PriceBookItem(
            sku="sku_dal",
            title="Organic Toor Dal 1kg",
            unit_price=Paise(8000),
            category="grocery",
            merchant="zepto",
        ),
        "sku_oil": PriceBookItem(
            sku="sku_oil",
            title="Cooking Oil 1L",
            unit_price=Paise(15000),
            category="grocery",
            merchant="zepto",
        ),
    })


def test_proposal_is_dereferenced_from_pricebook_not_agent_facts(tmp_path):
    pb = _pricebook()
    gw = Gateway(policy=_pol(), downstream=FakeDownstream(),
                 audit=AuditLog(tmp_path / "audit.jsonl"), pricebook=pb,
                 capability_secret="test_secret")
    
    # Agent sends wire proposal with NO prices or titles
    prop = Proposal(
        merchant="zepto",
        items=[ProposalItem(sku="sku_dal", qty=2), ProposalItem(sku="sku_oil", qty=1)],
    )
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    dec = gw.propose(prop, now)
    assert dec.verdict is Verdict.ALLOW
    assert dec.executed is True
    # Evaluated and charged amount: 2*8000 + 1*15000 = 31000 paise = Rs 310.00
    assert dec.downstream["amount"] == 31000


def test_proposal_with_unknown_sku_is_denied_fail_closed(tmp_path):
    pb = _pricebook()
    gw = Gateway(policy=_pol(), downstream=FakeDownstream(),
                 audit=AuditLog(tmp_path / "audit.jsonl"), pricebook=pb,
                 capability_secret="test_secret")
    
    prop = Proposal(
        merchant="zepto",
        items=[ProposalItem(sku="sku_nonexistent", qty=1)],
    )
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    dec = gw.propose(prop, now)
    assert dec.verdict is Verdict.DENY
    assert dec.clause_id == "pricebook"
    assert "unknown SKU" in dec.message


def test_canonical_intent_is_invariant_under_agent_controlled_fields():
    """The load-bearing property test.

    `canonical_intent()` must be identical across proposals differing in anything
    the agent controls. If this holds, idem.forge is dead by construction rather
    than by vigilance. If a new field appears on `Proposal`, it belongs in the
    perturbation list below or it belongs nowhere.
    """
    base = Proposal(
        merchant="Zepto",
        items=[ProposalItem(sku="sku_01", qty=2), ProposalItem(sku="sku_02", qty=1)],
        attempt=1,
    )
    key = canonical_intent(base, mandate_id="mnd_01")

    # Every field the agent can steer, perturbed one at a time.
    perturbations = [
        ("merchant whitespace and case", base.model_copy(update={"merchant": "  zepto  "})),
        ("attempt number", base.model_copy(update={"attempt": 99})),
        ("downstream_ref", base.model_copy(update={"downstream_ref": "ref_the_agent_chose"})),
        ("capability", base.model_copy(update={"capability": "forged_capability"})),
        ("line order", Proposal(
            merchant="Zepto", attempt=1,
            items=[ProposalItem(sku="sku_02", qty=1), ProposalItem(sku="sku_01", qty=2)])),
    ]
    for what, p in perturbations:
        assert canonical_intent(p, mandate_id="mnd_01") == key, (
            f"perturbing {what} steered the idempotency key; idem.forge is reopened"
        )


def test_canonical_intent_still_separates_genuinely_different_purchases():
    """The other half: invariance is worthless if every basket hashes the same."""
    base = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=2)])
    key = canonical_intent(base, mandate_id="mnd_01")

    different = [
        ("quantity", Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=3)])),
        ("sku", Proposal(merchant="zepto", items=[ProposalItem(sku="sku_02", qty=2)])),
        ("merchant", Proposal(merchant="blinkit", items=[ProposalItem(sku="sku_01", qty=2)])),
        ("extra line", Proposal(merchant="zepto", items=[
            ProposalItem(sku="sku_01", qty=2), ProposalItem(sku="sku_02", qty=1)])),
    ]
    for what, p in different:
        assert canonical_intent(p, mandate_id="mnd_01") != key, f"{what} must change the key"

    # And the mandate scopes it, so two mandates never share an idempotency key.
    assert canonical_intent(base, mandate_id="mnd_02") != key


def test_the_proposal_has_nowhere_to_put_a_price():
    """The wire format is the enforcement. There is no field to lie in."""
    fields = set(Proposal.model_fields) | set(ProposalItem.model_fields)
    forbidden = {"unit_price", "amount", "price", "total", "title", "category"}
    assert not (fields & forbidden), f"Proposal grew a fact-carrying field: {fields & forbidden}"


def test_a_gateway_with_no_pricebook_refuses_rather_than_trusting_the_agent(tmp_path):
    """Fail closed. The old code fell back to the agent's own prices here."""
    gw = Gateway(policy=_pol(), downstream=FakeDownstream(),
                 audit=AuditLog(tmp_path / "audit.jsonl"), pricebook=None,
                 capability_secret="test_secret")
    dec = gw.propose(Proposal(merchant="zepto", items=[ProposalItem(sku="sku_dal", qty=1)]),
                     datetime(2026, 9, 1, 12, 0, tzinfo=UTC))
    assert dec.verdict is Verdict.DENY
    assert dec.clause_id == "pricebook" and not dec.executed


def test_the_resolved_title_not_the_agents_reaches_the_category_resolver(tmp_path):
    """Closes the title-steering path named in the design spec."""
    seen = []

    class SpyResolver:
        def merchant(self, name):
            return name

        def category(self, sku, title):
            seen.append(title)
            return "grocery"

    gw = Gateway(policy=_pol(), downstream=FakeDownstream(),
                 audit=AuditLog(tmp_path / "audit.jsonl"),
                 pricebook=_pricebook(), resolver=SpyResolver(),
                 capability_secret="test_secret")
    gw.propose(Proposal(merchant="zepto", items=[ProposalItem(sku="sku_dal", qty=1)]),
               datetime(2026, 9, 1, 12, 0, tzinfo=UTC))
    assert seen == ["Organic Toor Dal 1kg"], (
        "the resolver must see the price book's title, never one the agent chose"
    )


def test_concurrent_velocity_race_is_locked(tmp_path):
    """Four concurrent proposals fired at velocity limit 3. Exactly 3 must execute, 1 must be blocked."""
    import concurrent.futures

    from mandate.gateway.idem import Ledger
    from mandate.policy.models import ConstraintId, Provenance
    from tests.policy.test_models import _policy

    pol = _policy(
        constraints={ConstraintId.VELOCITY: {"max_actions": 3, "window_seconds": 3600}},
        provenance=Provenance(stated=[ConstraintId.VELOCITY], inferred=[]),
    )
    ledger = Ledger(tmp_path / "ledger.jsonl")
    pb = _pricebook()
    gw = Gateway(policy=pol, downstream=FakeDownstream(), audit=AuditLog(tmp_path / "audit.jsonl"),
                 ledger=ledger, pricebook=pb, capability_secret="test_secret")

    # 4 distinct proposals to test velocity window
    props = [
        Proposal(merchant="zepto", items=[ProposalItem(sku="sku_dal", qty=1)]),
        Proposal(merchant="zepto", items=[ProposalItem(sku="sku_oil", qty=1)]),
        Proposal(merchant="zepto", items=[ProposalItem(sku="sku_dal", qty=2)]),
        Proposal(merchant="zepto", items=[ProposalItem(sku="sku_oil", qty=2)]),
    ]

    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(gw.propose, p, now) for p in props]
        decisions = [f.result() for f in futures]

    allows = [d for d in decisions if d.verdict is Verdict.ALLOW]
    denies = [d for d in decisions if d.verdict is Verdict.DENY]

    assert len(allows) == 3, f"Expected exactly 3 allows under velocity 3, got {len(allows)}"
    assert len(denies) == 1, f"Expected exactly 1 deny under velocity 3, got {len(denies)}"
    assert denies[0].clause_id == "velocity"

