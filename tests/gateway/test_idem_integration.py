from datetime import datetime, timezone, timedelta
from mandate.gateway.core import Gateway, Mode
from mandate.gateway.audit import AuditLog
from mandate.gateway.idem import Ledger, EntryState
from mandate.gateway.reconcile import Reconciler
from mandate.gateway.state import Verdict
from mandate.downstream.fake import FakeDownstream
from mandate.money import rupees
from tests.gateway.test_core import _pol, _act

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=IST)


def _gw(tmp_path, down=None):
    return Gateway(policy=_pol(), downstream=down or FakeDownstream(),
                   audit=AuditLog(tmp_path / "a.jsonl"), mode=Mode.ENFORCE,
                   ledger=Ledger(tmp_path / "l.jsonl"))

def test_replaying_the_same_intent_does_not_charge_twice(tmp_path):
    down = FakeDownstream(); gw = _gw(tmp_path, down)
    a = _act(rupees(500))
    d1 = gw.propose(a, now=NOW)
    d2 = gw.propose(a.model_copy(update={"attempt": 2}), now=NOW)
    assert d1.idem_key == d2.idem_key
    assert len(down.find_orders_by_receipt(d1.idem_key)) == 1
    assert d2.downstream == d1.downstream

def test_twenty_small_orders_stop_at_the_total_budget(tmp_path):
    """Salami. Each order is individually fine; together they are not."""
    gw = _gw(tmp_path)
    verdicts = [gw.propose(_act(rupees(99), sku=f"s{i}"), now=NOW).verdict for i in range(25)]
    assert Verdict.DENY in verdicts
    assert sum(v is Verdict.ALLOW for v in verdicts) <= 20   # 20 * 99 = 1980 <= 2000

def test_timeout_leaves_a_pending_entry(tmp_path):
    down = FakeDownstream(); down.fail_next("timeout")
    gw = _gw(tmp_path, down)
    d = gw.propose(_act(rupees(500)), now=NOW)
    assert d.verdict is Verdict.UNKNOWN
    assert gw.ledger.get(d.idem_key).state is EntryState.PENDING

def test_retry_while_pending_escalates_rather_than_re_executing(tmp_path):
    down = FakeDownstream(); down.fail_next("timeout")
    gw = _gw(tmp_path, down)
    a = _act(rupees(500))
    gw.propose(a, now=NOW)
    d2 = gw.propose(a.model_copy(update={"attempt": 2}), now=NOW)
    assert d2.verdict is Verdict.UNKNOWN and not d2.executed
    assert len(down.find_orders_by_receipt(d2.idem_key)) == 1

def test_reconciler_promotes_pending_to_committed_when_the_order_exists(tmp_path):
    down = FakeDownstream(); down.fail_next("timeout")
    gw = _gw(tmp_path, down)
    d = gw.propose(_act(rupees(500)), now=NOW)
    assert Reconciler(gw.ledger, down).run()[d.idem_key] is EntryState.COMMITTED
    assert gw.ledger.get(d.idem_key).state is EntryState.COMMITTED
