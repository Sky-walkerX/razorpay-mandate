"""The storefront's order history.

Every assertion here exists because the store sits downstream of the gateway and
must not become a second place where an agent-supplied number can surface. It
reads `AuditRecord.action`, a ResolvedAction, and nothing else.
"""
import inspect
from datetime import datetime, timedelta, timezone

import pytest

from mandate.downstream.fake import FakeDownstream
from mandate.gateway.action import ActionType, Proposal, ProposalItem
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Decision, Gateway, Mode
from mandate.gateway.state import Verdict
from mandate.money import rupees
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Provenance
from mandate.service.order_store import CLEAN, OrderStore
from tests.conftest import SyntheticPriceBook, priced_sku
from tests.policy.test_models import _policy

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=IST)


def _pol():
    return _policy(
        constraints={C.BUDGET_TOTAL: {"max": 200000},
                     C.BUDGET_PER_TRANSACTION: {"max": 100000},
                     C.TIME_WINDOW: {}},
        provenance=Provenance(stated=[C.BUDGET_TOTAL, C.BUDGET_PER_TRANSACTION,
                                      C.TIME_WINDOW], inferred=[]))


def _gw(tmp_path, down=None, mode=Mode.ENFORCE):
    return Gateway(policy=_pol(), downstream=down or FakeDownstream(),
                   audit=AuditLog(tmp_path / "audit.jsonl"), mode=mode,
                   pricebook=SyntheticPriceBook(), capability_secret="s")


def _prop(amount=None, sku=None, qty=1, merchant="zepto"):
    return Proposal(type=ActionType.CREATE_ORDER, merchant=merchant,
                    items=[ProposalItem(sku=sku or priced_sku(amount), qty=qty)])


def _place(gw, store, prop, source="http"):
    """Propose, then record the way the service does: decision plus its audit row."""
    dec = gw.propose(prop, now=NOW)
    recs = gw.audit.records()
    rec = recs[-1] if recs and recs[-1].idem_key == dec.idem_key else None
    return store.record(decision=dec, audit_record=rec, jti="tok_1",
                        mandate_id="mnd_test", source=source)


def test_an_allowed_order_is_recorded_as_executed(tmp_path):
    store = OrderStore()
    row = _place(_gw(tmp_path), store, _prop(rupees(500)))

    assert row.status == "EXECUTED"
    assert row.verdict == "ALLOW"
    assert row.amount_paise == 50000
    assert row.downstream_id is not None
    assert store.orders() == [row]


def test_a_refusal_carries_the_clause_that_fired(tmp_path):
    store = OrderStore()
    row = _place(_gw(tmp_path), store, _prop(rupees(1500)))

    assert row.status == "REFUSED"
    assert row.clause_id == C.BUDGET_PER_TRANSACTION
    assert row.downstream_id is None
    assert row.message


def test_the_amount_comes_from_the_price_book_not_the_agent(tmp_path):
    """The one rule, one layer out.

    An agent that states a price has it discarded by the gateway. If the store
    read the proposal instead of the resolved action, the storefront would show
    the agent's number while the rail charged another.
    """
    store = OrderStore()
    prop = Proposal(type=ActionType.CREATE_ORDER, merchant="zepto",
                    items=[ProposalItem(sku=priced_sku(rupees(500)), qty=2)])
    row = _place(_gw(tmp_path), store, prop)

    assert row.amount_paise == 100000
    assert row.items[0].unit_price_paise == 50000
    assert row.items[0].title == f"Test item {priced_sku(rupees(500))}"


def test_record_accepts_no_proposal():
    """A signature guard, so the rule above cannot be reopened by a later edit."""
    params = set(inspect.signature(OrderStore.record).parameters)
    assert not params & {"proposal", "prop", "action", "items", "amount"}


def test_a_decision_with_no_audit_row_still_lands(tmp_path):
    """An unknown SKU is denied before anything is written to the audit log.

    `core.py` returns early on `pricebook` and `authentication`, so the store has
    a Decision and no record. Dropping the row would hide exactly the refusals a
    judge most wants to see.
    """
    store = OrderStore()
    row = _place(_gw(tmp_path), store, _prop(sku="no_such_sku"))

    assert row.status == "REFUSED"
    assert row.clause_id == "pricebook"
    assert row.items == []
    assert row.amount_paise == 0


def test_an_observe_arm_order_executes_while_carrying_its_deny(tmp_path):
    """Unenforced money moving is the control arm, and must stay legible as such."""
    store = OrderStore()
    row = _place(_gw(tmp_path, mode=Mode.OBSERVE), store, _prop(rupees(1500)))

    assert row.status == "EXECUTED"
    assert row.verdict == "DENY"
    assert row.clause_id == C.BUDGET_PER_TRANSACTION


def test_rows_survive_a_reload(tmp_path):
    path = tmp_path / "store" / "orders.jsonl"
    store = OrderStore(path)
    _place(_gw(tmp_path), store, _prop(rupees(500)))
    store.advance_week(family="injection.description")
    _place(_gw(tmp_path / "b"), store, _prop(rupees(300)))

    reopened = OrderStore(path)
    assert [r.amount_paise for r in reopened.orders()] == [50000, 30000]
    assert reopened.current_week == 2
    assert reopened.week_family() == "injection.description"


def test_no_path_writes_no_file(tmp_path):
    """The service default. A shared on-disk default would have every test in the
    suite appending to one file."""
    store = OrderStore()
    _place(_gw(tmp_path), store, _prop(rupees(500)))

    assert store.path is None
    assert list(tmp_path.glob("**/orders.jsonl")) == []


def test_weeks_partition_the_order_list(tmp_path):
    store = OrderStore()
    _place(_gw(tmp_path), store, _prop(rupees(500)))
    store.advance_week(family="injection.description")
    _place(_gw(tmp_path / "b"), store, _prop(rupees(300)))

    assert [r.week for r in store.orders()] == [1, 2]
    assert [r.amount_paise for r in store.orders(week=1)] == [50000]
    assert [r.amount_paise for r in store.orders(week=2)] == [30000]


def test_an_empty_week_is_still_a_week(tmp_path):
    store = OrderStore()
    store.advance_week()
    store.advance_week()

    assert store.current_week == 3
    assert [w.week for w in store.weeks()] == [1, 2, 3]
    assert store.orders(week=2) == []


def test_week_one_is_clean_by_default():
    assert OrderStore().week_family() == CLEAN


def test_trimming_drops_the_oldest_orders_and_keeps_every_week(tmp_path):
    store = OrderStore(max_rows=2)
    gw = _gw(tmp_path)
    for _ in range(3):
        _place(gw, store, _prop(rupees(100)))
    store.advance_week()

    assert len(store.orders()) == 2
    assert [w.week for w in store.weeks()] == [1, 2]


def test_the_etag_moves_when_an_order_lands(tmp_path):
    store = OrderStore()
    before = store.etag()
    _place(_gw(tmp_path), store, _prop(rupees(500)))

    assert store.etag() != before


@pytest.mark.parametrize("source", ["http", "mcp", "agent"])
def test_the_source_of_an_order_is_kept(tmp_path, source):
    """A judge asking 'did that come from my Claude or from your button' gets an
    answer from the row rather than from the demo script."""
    store = OrderStore()
    row = _place(_gw(tmp_path), store, _prop(rupees(500)), source=source)
    assert row.source == source


def test_a_bare_decision_needs_no_gateway():
    """The store is usable from any call site, including one that never reached
    the audit log at all."""
    store = OrderStore()
    row = store.record(
        decision=Decision(verdict=Verdict.DENY, clause_id="authentication",
                          message="token_revoked", idem_key=""),
        audit_record=None, jti="tok_9", mandate_id="mnd_test", source="mcp")

    assert row.status == "REFUSED"
    assert row.clause_id == "authentication"
    assert row.merchant == ""
