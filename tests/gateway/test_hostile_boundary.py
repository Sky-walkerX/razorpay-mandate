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
                 audit=AuditLog(tmp_path / "audit.jsonl"), pricebook=pb)
    
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
                 audit=AuditLog(tmp_path / "audit.jsonl"), pricebook=pb)
    
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
    """Load-bearing property test:
    Agent mutating prices, titles, categories or whitespace cannot steer or forge the idempotency key.
    """
    # Base proposal
    p1 = Proposal(
        merchant="Zepto",
        items=[ProposalItem(sku="sku_01", qty=2), ProposalItem(sku="sku_02", qty=1)],
        attempt=1,
    )
    # Mutated proposal: different case merchant, reversed line items, attempt number 99
    p2 = Proposal(
        merchant="  zepto  ",
        items=[ProposalItem(sku="sku_02", qty=1), ProposalItem(sku="sku_01", qty=2)],
        attempt=99,
    )
    
    k1 = canonical_intent(p1, mandate_id="mnd_01")
    k2 = canonical_intent(p2, mandate_id="mnd_01")
    assert k1 == k2, "canonical_intent must be invariant under formatting and line order"
    
    # Changing quantity or SKU MUST change the key
    p3 = Proposal(
        merchant="Zepto",
        items=[ProposalItem(sku="sku_01", qty=3), ProposalItem(sku="sku_02", qty=1)],
    )
    k3 = canonical_intent(p3, mandate_id="mnd_01")
    assert k1 != k3, "quantity change must change canonical_intent"


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
                 ledger=ledger, pricebook=pb)

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

