"""The mechanical failure, handled: a timeout that already wrote, then a retry.

This is the failure mode the README calls the one most likely to bite in production,
and the only one in the project that has nothing to do with AI. `create_order` reaches
the rail, the rail writes the order, the response never comes back. The agent knows
only that it got no answer, so it does the obvious thing and tries again.

Naively that is two orders and two charges for one intent. The ledger is what makes it
one. Runs with no model: the behaviour under test is deterministic gateway code, and a
demo that must not break on stage should not depend on a model to make its point.
"""
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from mandate.downstream.fake import DownstreamTimeout, FakeDownstream
from mandate.gateway.action import Action, ActionType, LineItem
from mandate.gateway.audit import AuditChainBroken, AuditLog
from mandate.gateway.core import Gateway, Mode
from mandate.gateway.idem import EntryState, Ledger
from mandate.gateway.reconcile import Reconciler
from mandate.money import Paise
from mandate.policy.models import Policy


class Step(BaseModel):
    n: int
    what: str
    verdict: str = "-"
    clause: str = "-"
    executed: bool = False
    detail: str = ""


class FailureDemoResult(BaseModel):
    steps: list[Step] = []
    orders_downstream: int = 0
    charged: Paise = Paise(0)
    budget_consumed: Paise = Paise(0)
    audit_records: int = 0
    chain_intact: bool = False
    naive_orders: int = 0
    naive_charged: Paise = Paise(0)


def _action(policy: Policy) -> Action:
    """One ordinary basket, well inside every limit. The attack here is not the basket."""
    items = [
        LineItem(sku="sku_0012", title="Toor Dal 1kg", qty=1,
                 unit_price=Paise(8000), amount=Paise(8000)),
        LineItem(sku="sku_0014", title="Amul Milk 1kg", qty=1,
                 unit_price=Paise(7900), amount=Paise(7900)),
    ]
    return Action(type=ActionType.CREATE_ORDER, amount=Paise(15900),
                  merchant="zepto", items=items)


def _naive_retry(policy: Policy, now: datetime) -> tuple[int, Paise]:
    """The same two calls with no ledger: what a retry costs when nothing dedupes it."""
    down = FakeDownstream()
    gw = Gateway(policy=policy, downstream=down, audit=AuditLog(Path("/dev/null")),
                 mode=Mode.ENFORCE, ledger=None)
    action = _action(policy)
    down.fail_next("timeout")
    try:
        gw.propose(action, now=now)
    except DownstreamTimeout:
        pass
    gw.propose(action, now=now)
    return len(down._orders), Paise(sum(int(o["amount"]) for o in down._orders.values()))


def run_failure_demo(policy: Policy, root: Path, now: datetime | None = None) -> FailureDemoResult:
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    now = now or (policy.issued.replace(tzinfo=policy.issued.tzinfo))

    down = FakeDownstream()
    ledger = Ledger(root / "ledger.jsonl")
    audit = AuditLog(root / "audit.jsonl")
    gw = Gateway(policy=policy, downstream=down, audit=audit,
                 mode=Mode.ENFORCE, ledger=ledger)
    action = _action(policy)
    res = FailureDemoResult()

    # 1. The rail writes the order, then the response is lost.
    down.fail_next("timeout")
    d1 = gw.propose(action, now=now)
    entry = ledger.get(d1.idem_key)
    res.steps.append(Step(
        n=1, what="agent proposes ₹159.00 order",
        verdict=str(d1.verdict), clause=d1.clause_id or "-", executed=d1.executed,
        detail=f"downstream wrote the order, then timed out. ledger={entry.state}. "
               f"the agent learned nothing."))

    # 2. The agent never heard back, so it retries the identical intent.
    d2 = gw.propose(action, now=now)
    res.steps.append(Step(
        n=2, what="agent retries the identical order",
        verdict=str(d2.verdict), clause=d2.clause_id or "-", executed=d2.executed,
        detail="same canonical intent, so the same idem key. held, not re-executed. "
               "no second charge."))

    # 3. Ask the rail what actually happened, using the idem key as the receipt.
    resolved = Reconciler(ledger, down).run()
    entry = ledger.get(d1.idem_key)
    res.steps.append(Step(
        n=3, what="reconciler asks the downstream what landed",
        verdict="-", clause="-", executed=False,
        detail=f"found the order by receipt. ledger={entry.state}. "
               f"resolved {len(resolved)} pending entry."))

    # 4. A retry after reconciliation returns the cached result rather than paying twice.
    d4 = gw.propose(action, now=now)
    res.steps.append(Step(
        n=4, what="agent retries once more, after reconciliation",
        verdict=str(d4.verdict), clause=d4.clause_id or "-", executed=d4.executed,
        detail="cached result returned. allowed, but not executed again."))

    res.orders_downstream = len(down._orders)
    res.charged = Paise(sum(int(o["amount"]) for o in down._orders.values()))
    # `spent` is committed plus pending on purpose: an outcome we never learned still
    # consumes budget, so a lost response cannot quietly free up room to spend again.
    res.budget_consumed = Paise(int(ledger.state().spent))
    records = audit.records()
    res.audit_records = len(records)
    try:
        audit.verify_chain()
        res.chain_intact = True
    except AuditChainBroken:
        res.chain_intact = False

    res.naive_orders, res.naive_charged = _naive_retry(policy, now)
    return res


__all__ = ["EntryState", "FailureDemoResult", "Step", "run_failure_demo"]
