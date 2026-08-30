"""Unit tests for downstream amount reconciliation (rail divergence check)."""
from datetime import UTC, datetime
from pathlib import Path
import pytest

from mandate.downstream.fake import FakeDownstream
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

    def create_order(self, amount, receipt=None, notes=None, skus=None):
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
