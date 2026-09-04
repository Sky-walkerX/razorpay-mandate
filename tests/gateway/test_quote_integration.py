"""Integration tests for quote resolution in Gateway."""
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mandate.downstream.fake import FakeDownstream
from mandate.gateway.action import Proposal, ProposalItem
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway
from mandate.gateway.idem import Ledger
from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.quote import MerchantKeyring, mint_quote
from mandate.gateway.state import Verdict
from mandate.money import Paise
from mandate.policy.crypto import generate_keypair
from mandate.policy.models import CompilerInfo, ConstraintId, Policy, Provenance

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _policy() -> Policy:
    c = {
        ConstraintId.BUDGET_TOTAL: {"max": 200000},
        ConstraintId.BUDGET_PER_TRANSACTION: {"max": 100000},
    }
    return Policy(
        mandate_id="mnd_test_quotes",
        principal="user@example.com",
        agent="shopping_agent",
        issued=NOW - timedelta(days=1),
        expires=NOW + timedelta(days=1),
        constraints=c,
        provenance=Provenance(stated=list(c.keys()), inferred=[]),
        source_text="quote test policy",
        compiler=CompilerInfo(model="offline", temperature=0.0, version="1.0"),
    )


def _pricebook() -> DictPriceBook:
    return DictPriceBook({
        "sku_01": PriceBookItem(sku="sku_01", title="Item 01", unit_price=Paise(50000),
                                category="grocery", merchant="zepto"),
    })


def test_a_quote_the_gateway_cannot_verify_moves_no_money(tmp_path: Path):
    """An unverified quote denies and executes zero orders downstream."""
    untrusted_priv, _ = generate_keypair()
    # Keyring has no keys for zepto
    keyring = MerchantKeyring()
    downstream = FakeDownstream()
    gw = Gateway(
        policy=_policy(),
        downstream=downstream,
        audit=AuditLog(tmp_path / "audit.jsonl"),
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        pricebook=_pricebook(),
        capability_secret="secret",
        merchant_keyring=keyring,
    )
    quote = mint_quote("zepto", "sku_01", 50000, untrusted_priv, issued=NOW, expires=NOW + timedelta(minutes=10))
    prop = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1, quote=quote)])

    dec = gw.propose(prop, now=NOW)
    assert dec.verdict is Verdict.DENY
    assert dec.clause_id == "quote.unknown_merchant"
    assert not dec.executed
    assert len(downstream._orders) == 0


def test_a_quote_at_book_price_executes(tmp_path: Path):
    """A valid quote matching the price book passes and executes downstream."""
    priv, pub = generate_keypair()
    keyring = MerchantKeyring({"zepto": [pub]})
    downstream = FakeDownstream()
    audit = AuditLog(tmp_path / "audit.jsonl")
    gw = Gateway(
        policy=_policy(),
        downstream=downstream,
        audit=audit,
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        pricebook=_pricebook(),
        capability_secret="secret",
        merchant_keyring=keyring,
    )
    quote = mint_quote("zepto", "sku_01", 50000, priv, issued=NOW, expires=NOW + timedelta(minutes=10))
    prop = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1, quote=quote)])

    dec = gw.propose(prop, now=NOW)
    assert dec.verdict is Verdict.ALLOW
    assert dec.executed
    assert len(downstream._orders) == 1

    # Check that quote.confirmed was recorded
    records = audit.records()
    assert len(records) == 1
    assert any(c.id == "quote.confirmed" for c in records[0].clauses)


def test_quote_disagrees_with_book_denies_and_moves_no_money(tmp_path: Path):
    """Quote price differing from price book fails with quote.disagreement."""
    priv, pub = generate_keypair()
    keyring = MerchantKeyring({"zepto": [pub]})
    downstream = FakeDownstream()
    audit = AuditLog(tmp_path / "audit.jsonl")
    gw = Gateway(
        policy=_policy(),
        downstream=downstream,
        audit=audit,
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        pricebook=_pricebook(),
        capability_secret="secret",
        merchant_keyring=keyring,
    )
    # Quoted at 60000 vs 50000 book price
    quote = mint_quote("zepto", "sku_01", 60000, priv, issued=NOW, expires=NOW + timedelta(minutes=10))
    prop = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1, quote=quote)])

    dec = gw.propose(prop, now=NOW)
    assert dec.verdict is Verdict.DENY
    assert dec.clause_id == "quote.disagreement"
    assert not dec.executed
    assert len(downstream._orders) == 0

    # Assert the refusal was audited with stripped quote action
    records = audit.records()
    assert len(records) == 1
    assert records[0].verdict == Verdict.DENY
    assert records[0].clauses[0].id == "quote.disagreement"


def test_a_rejected_quote_does_not_poison_the_idempotency_key(tmp_path: Path):
    """A rejected quote never reaches open_pending, so a clean retry succeeds."""
    priv, pub = generate_keypair()
    keyring = MerchantKeyring({"zepto": [pub]})
    downstream = FakeDownstream()
    audit = AuditLog(tmp_path / "audit.jsonl")
    gw = Gateway(
        policy=_policy(),
        downstream=downstream,
        audit=audit,
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        pricebook=_pricebook(),
        capability_secret="secret",
        merchant_keyring=keyring,
    )
    # Proposal 1: with bad quote -> DENY
    bad_quote = mint_quote("zepto", "sku_01", 60000, priv, issued=NOW, expires=NOW + timedelta(minutes=10))
    prop_bad = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1, quote=bad_quote)])
    dec1 = gw.propose(prop_bad, now=NOW)
    assert dec1.verdict is Verdict.DENY

    # Proposal 2: same basket, no quote -> ALLOW and executed
    prop_clean = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1, quote=None)])
    dec2 = gw.propose(prop_clean, now=NOW)
    assert dec2.verdict is Verdict.ALLOW
    assert dec2.executed
    assert len(downstream._orders) == 1


def test_a_signed_quote_does_not_widen_the_divergence_band(tmp_path: Path):
    """Quoted order whose rail settles even 1 paisa different triggers rail.divergence."""
    priv, pub = generate_keypair()
    keyring = MerchantKeyring({"zepto": [pub]})

    class SlightlyDivergentDownstream:
        def __init__(self):
            self._orders = {}
        def create_order(self, amount, receipt=None, notes=None, skus=None, action=None):
            # Diverges by 1 paisa
            divergent = int(amount) + 1
            order_id = f"order_{receipt}"
            order = {"id": order_id, "amount": divergent, "status": "created", "receipt": receipt}
            self._orders[order_id] = order
            return order
        def void_order(self, order_id):
            if order_id in self._orders:
                self._orders[order_id]["status"] = "voided"
            return self._orders.get(order_id)

    downstream = SlightlyDivergentDownstream()
    gw = Gateway(
        policy=_policy(),
        downstream=downstream,
        audit=AuditLog(tmp_path / "audit.jsonl"),
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        pricebook=_pricebook(),
        capability_secret="secret",
        merchant_keyring=keyring,
    )
    quote = mint_quote("zepto", "sku_01", 50000, priv, issued=NOW, expires=NOW + timedelta(minutes=10))
    prop = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1, quote=quote)])

    dec = gw.propose(prop, now=NOW)
    assert dec.verdict is Verdict.UNKNOWN
    assert dec.clause_id == "rail.divergence"
    assert not dec.executed
