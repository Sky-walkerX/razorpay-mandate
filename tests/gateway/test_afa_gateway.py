"""afa.required through the Gateway, not beside it.

Testing the ApprovalStore directly proves the store works and proves nothing
about the boundary. These run the whole request path, so they fail if the gateway
stops consulting the store or starts keying approvals on something the agent
controls.
"""
from datetime import datetime, timedelta, timezone

from mandate.downstream.fake import FakeDownstream
from mandate.gateway.action import ActionType, Proposal, ProposalItem
from mandate.gateway.approval import ApprovalStore
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
THRESHOLD = int(rupees(15000))


def _pol():
    cons = {
        C.BUDGET_TOTAL: {"max": int(rupees(100000))},
        C.BUDGET_PER_TRANSACTION: {"max": int(rupees(100000))},
        C.TIME_WINDOW: {},
        C.AFA_REQUIRED: {"threshold": THRESHOLD},
    }
    return _policy(constraints=cons,
                   provenance=Provenance(stated=list(cons.keys()), inferred=[]))


def _gw(tmp_path, approvals=None, down=None):
    return Gateway(policy=_pol(), downstream=down or FakeDownstream(),
                   audit=AuditLog(tmp_path / "audit.jsonl"), mode=Mode.ENFORCE,
                   pricebook=SyntheticPriceBook(), capability_secret="test_secret",
                   approvals=approvals)


def _act(amount, sku=None):
    return Proposal(type=ActionType.CREATE_ORDER, merchant="zepto",
                    items=[ProposalItem(sku=sku or priced_sku(amount), qty=1)])


def test_below_the_threshold_executes_with_no_approval(tmp_path):
    d = _gw(tmp_path, ApprovalStore()).propose(_act(rupees(9000)), now=NOW)
    assert d.verdict is Verdict.ALLOW and d.executed


def test_above_the_threshold_escalates_and_does_not_reach_the_rail(tmp_path):
    down = FakeDownstream()
    d = _gw(tmp_path, ApprovalStore(), down=down).propose(_act(rupees(20000)), now=NOW)
    assert d.verdict is Verdict.UNKNOWN
    assert not d.executed
    assert d.clause_id == "afa.required"
    assert down.find_orders_by_receipt(d.idem_key) == []


def test_the_same_action_executes_once_the_principal_approves(tmp_path):
    store = ApprovalStore()
    gw = _gw(tmp_path, store)
    first = gw.propose(_act(rupees(20000), sku="p_2000000"), now=NOW)
    assert first.verdict is Verdict.UNKNOWN

    store.approve(first.idem_key, approver="user_local", factor="otp")

    second = gw.propose(_act(rupees(20000), sku="p_2000000"), now=NOW)
    assert second.verdict is Verdict.ALLOW
    assert second.executed


def test_an_approval_for_one_basket_does_not_authorise_another(tmp_path):
    """The whole point of keying on the resolved intent.

    Both baskets cost the same. Approving one must not release the other, or the
    agent could get a cheap approval signed off and swap the contents.
    """
    store = ApprovalStore()
    gw = _gw(tmp_path, store)

    approved = gw.propose(_act(rupees(20000), sku="p_2000000"), now=NOW)
    store.approve(approved.idem_key)

    other = gw.propose(_act(rupees(20000), sku="p_2000000_dairy"), now=NOW)
    assert other.idem_key != approved.idem_key
    assert other.verdict is Verdict.UNKNOWN
    assert not other.executed


def test_a_gateway_with_no_approval_store_still_escalates(tmp_path):
    """Fails closed. A missing store must not read as blanket approval."""
    d = _gw(tmp_path, approvals=None).propose(_act(rupees(20000)), now=NOW)
    assert d.verdict is Verdict.UNKNOWN and not d.executed


def test_the_escalation_is_written_to_the_audit_log(tmp_path):
    gw = _gw(tmp_path, ApprovalStore())
    gw.propose(_act(rupees(20000)), now=NOW)
    rec = gw.audit.records()[-1]
    clause = next(c for c in rec.clauses if c.id == "afa.required")
    assert clause.result is Verdict.UNKNOWN
    gw.audit.verify_chain()
