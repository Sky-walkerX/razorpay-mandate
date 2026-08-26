from datetime import datetime, timezone, timedelta
from mandate.gateway.idem import Ledger, EntryState
from mandate.gateway.action import Action, LineItem, ActionType, canonical_intent
from mandate.money import rupees

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=IST)


def _act(amount, sku="s1"):
    return Action(type=ActionType.CREATE_ORDER, amount=amount, merchant="zepto",
                  items=[LineItem(sku=sku, title="t", qty=1, unit_price=amount,
                                  amount=amount)])

def test_unknown_key_returns_none(tmp_path):
    assert Ledger(tmp_path / "l.jsonl").get("nope") is None

def test_open_pending_then_commit(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    a = _act(rupees(500)); k = canonical_intent(a)
    led.open_pending(k, a, NOW)
    assert led.get(k).state is EntryState.PENDING
    led.mark_committed(k, {"id": "order_1"})
    assert led.get(k).state is EntryState.COMMITTED

def test_pending_counts_toward_spend(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    a = _act(rupees(500)); led.open_pending(canonical_intent(a), a, NOW)
    st = led.state()
    assert st.pending == rupees(500) and st.committed == 0 and st.spent == rupees(500)

def test_failed_does_not_count_toward_spend(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    a = _act(rupees(500)); k = canonical_intent(a)
    led.open_pending(k, a, NOW); led.mark_failed(k, "refused")
    assert led.state().spent == 0

def test_committed_and_pending_both_count(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    a1, a2 = _act(rupees(300), "s1"), _act(rupees(400), "s2")
    k1, k2 = canonical_intent(a1), canonical_intent(a2)
    led.open_pending(k1, a1, NOW); led.mark_committed(k1, {"id": "o1"})
    led.open_pending(k2, a2, NOW)
    assert led.state().spent == rupees(700)

def test_action_count_and_skus_accumulate(tmp_path):
    led = Ledger(tmp_path / "l.jsonl")
    for sku in ("s1", "s2"):
        a = _act(rupees(100), sku)
        k = canonical_intent(a); led.open_pending(k, a, NOW); led.mark_committed(k, {})
    st = led.state()
    assert st.action_count == 2 and st.recent_skus == {"s1", "s2"}

def test_ledger_survives_reload(tmp_path):
    p = tmp_path / "l.jsonl"
    a = _act(rupees(500)); k = canonical_intent(a)
    Ledger(p).open_pending(k, a, NOW)
    assert Ledger(p).get(k).state is EntryState.PENDING
