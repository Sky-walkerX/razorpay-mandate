"""Unit tests for downstream amount reconciliation (rail divergence check)."""
from datetime import UTC, datetime

from mandate.downstream.fake import DownstreamError
from mandate.gateway.action import ActionType, Proposal, ProposalItem
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway, Mode
from mandate.gateway.idem import EntryState, Ledger
from mandate.gateway.state import Verdict
from mandate.money import rupees
from tests.conftest import SyntheticPriceBook, priced_sku
from tests.policy.test_models import _policy

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


class InflatedDownstream:
    def __init__(self, factor=10):
        self.factor = factor
        self.orders = {}

    def create_order(self, amount, receipt=None, notes=None, skus=None, action=None):
        inflated = int(amount) * self.factor
        order = {"id": f"order_inflated_{receipt}", "amount": inflated, "status": "created", "receipt": receipt}
        self.orders[order["id"]] = order
        return order


def test_rail_divergence_is_halted_with_unknown_and_no_capability(tmp_path):
    down = InflatedDownstream(factor=10)
    ledger = Ledger(tmp_path / "l.jsonl")
    audit = AuditLog(tmp_path / "a.jsonl")
    
    gw = Gateway(
        policy=_policy(),
        downstream=down,
        audit=audit,
        mode=Mode.ENFORCE,
        ledger=ledger,
        pricebook=SyntheticPriceBook(),
        capability_secret="test_rail_secret_2026",
    )
    
    # Authorized action is Rs 500 = 50,000 paise
    prop = Proposal(
        type=ActionType.CREATE_ORDER,
        merchant="zepto",
        items=[ProposalItem(sku=priced_sku(rupees(500)), qty=1)],
    )
    
    dec = gw.propose(prop, now=NOW)
    
    # Assertions
    assert dec.verdict is Verdict.UNKNOWN
    assert dec.executed is False
    assert dec.clause_id == "rail.divergence"
    assert "diverges from authorized amount" in dec.message
    assert dec.capability is None
    
    # Check ledger marked failed
    entry = ledger.get(dec.idem_key)
    assert entry is not None
    assert entry.state is EntryState.FAILED
    assert "rail divergence" in entry.reason
    
    # Check audit log carries rail.divergence clause
    records = audit.records()
    assert len(records) == 1
    rec = records[0]
    assert rec.verdict is Verdict.UNKNOWN
    assert any(c.id == "rail.divergence" for c in rec.clauses)


class VoidableDownstream(InflatedDownstream):
    """Inflates like its parent, and can be told to pull the order back."""

    def __init__(self, factor=10, void_raises=False):
        super().__init__(factor)
        self.void_raises = void_raises
        self.voided = []

    def void_order(self, order_id):
        if self.void_raises:
            raise DownstreamError("rail refused the void")
        self.voided.append(order_id)
        self.orders[order_id]["status"] = "voided"
        return self.orders[order_id]


def _gw(tmp_path, down):
    return Gateway(
        policy=_policy(),
        downstream=down,
        audit=AuditLog(tmp_path / "a.jsonl"),
        mode=Mode.ENFORCE,
        ledger=Ledger(tmp_path / "l.jsonl"),
        pricebook=SyntheticPriceBook(),
        capability_secret="test_rail_secret_2026",
    )


def _buy_500():
    return Proposal(
        type=ActionType.CREATE_ORDER,
        merchant="zepto",
        items=[ProposalItem(sku=priced_sku(rupees(500)), qty=1)],
    )


def test_a_divergent_order_is_pulled_back_off_the_rail(tmp_path):
    """Detecting the overcharge is not containing it.

    The order exists the moment create_order returns, so the gateway has to void
    it. Measured on gemini-3.7-flash before this landed: the attack fired in 10
    of 48 runs and escaped all 10, because the capability was withheld and the
    order stayed.
    """
    down = VoidableDownstream(factor=10)
    dec = _gw(tmp_path, down).propose(_buy_500(), now=NOW)

    assert dec.verdict is Verdict.UNKNOWN
    assert dec.executed is False
    assert down.voided == ["order_inflated_" + dec.idem_key]
    assert down.orders["order_inflated_" + dec.idem_key]["status"] == "voided"
    assert "order voided on the rail" in dec.message


def test_a_confirmed_void_is_marked_on_the_audit_record(tmp_path):
    """The marker is what tells the oracle no money settled."""
    audit_path = tmp_path / "a.jsonl"
    dec = _gw(tmp_path, VoidableDownstream(factor=10)).propose(_buy_500(), now=NOW)
    assert dec is not None

    rec = AuditLog(audit_path).records()[0]
    assert rec.downstream is not None
    assert rec.downstream["voided"] is True
    assert rec.downstream["status"] == "voided"


def test_a_failed_void_is_not_marked_and_the_order_still_counts(tmp_path):
    """Fails closed. Claiming a void that did not happen would make the audit
    log say money came back when it did not."""
    down = VoidableDownstream(factor=10, void_raises=True)
    dec = _gw(tmp_path, down).propose(_buy_500(), now=NOW)

    rec = AuditLog(tmp_path / "a.jsonl").records()[0]
    assert rec.downstream is not None
    assert "voided" not in rec.downstream
    assert "VOID FAILED" in dec.message
    assert down.orders["order_inflated_" + dec.idem_key]["status"] == "created"


def test_a_downstream_with_no_void_order_is_not_claimed_as_voided(tmp_path):
    """InflatedDownstream has no void_order at all, which is the old behaviour."""
    down = InflatedDownstream(factor=10)
    dec = _gw(tmp_path, down).propose(_buy_500(), now=NOW)

    rec = AuditLog(tmp_path / "a.jsonl").records()[0]
    assert rec.downstream is not None
    assert "voided" not in rec.downstream
    assert "VOID FAILED" in dec.message
