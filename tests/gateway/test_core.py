from datetime import datetime, timedelta, timezone

from mandate.downstream.fake import FakeDownstream
from mandate.gateway.action import ActionType, Proposal, ProposalItem
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway, Mode
from mandate.gateway.state import Verdict
from mandate.money import rupees
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Provenance
from tests.conftest import SyntheticPriceBook, priced_sku
from tests.policy.test_models import _policy

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=IST)


def _pol():
    return _policy(
        constraints={C.BUDGET_TOTAL: {"max": 200000},
                     C.BUDGET_PER_TRANSACTION: {"max": 200000},
                     C.TIME_WINDOW: {}},
        provenance=Provenance(stated=[C.BUDGET_TOTAL, C.BUDGET_PER_TRANSACTION,
                                      C.TIME_WINDOW], inferred=[]))

def _gw(tmp_path, mode=Mode.ENFORCE, down=None):
    return Gateway(policy=_pol(), downstream=down or FakeDownstream(),
                   audit=AuditLog(tmp_path / "audit.jsonl"), mode=mode,
                   pricebook=SyntheticPriceBook(), capability_secret="test_secret")

def _act(amount, sku=None):
    """The agent names a SKU. The price book, not the agent, says what it costs."""
    return Proposal(type=ActionType.CREATE_ORDER, merchant="zepto",
                    items=[ProposalItem(sku=sku or priced_sku(amount), qty=1)])

def test_allowed_action_executes(tmp_path):
    d = _gw(tmp_path).propose(_act(rupees(500)), now=NOW)
    assert d.verdict is Verdict.ALLOW and d.executed and d.downstream["id"].startswith("order_")

def test_denied_action_does_not_execute(tmp_path):
    down = FakeDownstream()
    d = _gw(tmp_path, down=down).propose(_act(rupees(50000)), now=NOW)
    assert d.verdict is Verdict.DENY and not d.executed
    assert down.find_orders_by_receipt(d.idem_key) == []

def test_denial_names_the_violated_clause(tmp_path):
    d = _gw(tmp_path).propose(_act(rupees(50000)), now=NOW)
    assert d.clause_id == "budget.per_transaction" and "2000" in d.message

def test_observe_mode_records_the_verdict_but_still_executes(tmp_path):
    """The baseline arm. Same code, enforcement switched off."""
    d = _gw(tmp_path, mode=Mode.OBSERVE).propose(_act(rupees(50000)), now=NOW)
    assert d.verdict is Verdict.DENY and d.executed

def test_every_proposal_is_audited_regardless_of_verdict(tmp_path):
    gw = _gw(tmp_path)
    gw.propose(_act(rupees(500)), now=NOW)
    gw.propose(_act(rupees(50000)), now=NOW)
    assert len(gw.audit.records()) == 2
    gw.audit.verify_chain()

def test_audit_record_carries_all_ten_clause_results(tmp_path):
    gw = _gw(tmp_path)
    gw.propose(_act(rupees(500)), now=NOW)
    assert len(gw.audit.records()[0].clauses) == 10

def test_expired_mandate_denies(tmp_path):
    gw = _gw(tmp_path)
    d = gw.propose(_act(rupees(100)), now=_pol().expires + timedelta(seconds=1))
    assert d.verdict is Verdict.DENY and d.clause_id == "time.window"
