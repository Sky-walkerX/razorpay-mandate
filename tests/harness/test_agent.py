from datetime import datetime, timedelta, timezone

from mandate.adapters.direct import DirectClient
from mandate.downstream.fake import FakeDownstream
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway, Mode
from mandate.gateway.idem import Ledger
from mandate.gateway.pricebook import DictPriceBook
from mandate.gateway.state import Verdict
from mandate.harness.agent import ShoppingAgent
from mandate.harness.catalog import generate_catalog
from mandate.money import Paise, rupees
from tests.gateway.test_core import _pol

IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 9, 1, 12, 0, tzinfo=IST)


class ScriptedModel:
    """Deterministic stand-in for Claude. Emits a fixed sequence of tool calls."""
    def __init__(self, calls): self.calls, self.i = list(calls), 0
    def next_call(self, _trace):
        if self.i >= len(self.calls):
            return None
        c = self.calls[self.i]; self.i += 1
        return c


CATALOG = generate_catalog(seed=7)

# What the catalog actually charges. The agent does not get a say.
DAL = Paise(CATALOG.by_sku("sku_0000").unit_price)      # 8500
RICE = Paise(CATALOG.by_sku("sku_0001").unit_price)     # 17100


def _agent(tmp_path, calls, mode=Mode.ENFORCE):
    gw = Gateway(policy=_pol(), downstream=FakeDownstream(),
                 audit=AuditLog(tmp_path / "a.jsonl"), mode=mode,
                 ledger=Ledger(tmp_path / "l.jsonl"),
                 pricebook=DictPriceBook.from_catalog(CATALOG),
                 capability_secret="test_secret")
    return ShoppingAgent(client=DirectClient(gw), catalog=CATALOG,
                         model=ScriptedModel(calls))

def _buy(sku, qty, unit_rupees=None):
    """The agent names a SKU and a quantity.

    `unit_rupees` is still accepted and still sent on the wire, because a hostile
    agent will send it. It is discarded: the price book is the only price.
    """
    item = {"sku": sku, "qty": qty}
    if unit_rupees is not None:
        item |= {"title": "Toor Dal", "unit_price": int(rupees(unit_rupees))}
    return ("create_order", {"merchant": "zepto", "items": [item]})

def test_agent_completes_an_allowed_purchase(tmp_path):
    t = _agent(tmp_path, [_buy("sku_0000", 1)]).run("buy dal", now=NOW)
    assert t.decisions[0].verdict is Verdict.ALLOW and t.spent == DAL

def test_an_agent_declared_price_is_discarded(tmp_path):
    """The one rule, at the wire. A lie about price changes nothing that is charged."""
    honest = _agent(tmp_path / "a", [_buy("sku_0000", 1)]).run("x", now=NOW)
    liar = _agent(tmp_path / "b", [_buy("sku_0000", 1, 1)]).run("x", now=NOW)
    assert honest.spent == liar.spent == DAL
    assert honest.decisions[0].idem_key == liar.decisions[0].idem_key

def test_agent_records_a_denial_and_keeps_its_trace(tmp_path):
    # Over the Rs 2000 per-transaction cap only by ordering a real quantity.
    t = _agent(tmp_path, [_buy("sku_0000", 30)]).run("buy dal", now=NOW)
    assert t.decisions[0].verdict is Verdict.DENY and t.spent == 0

def test_spent_counts_only_executed_actions(tmp_path):
    t = _agent(tmp_path, [_buy("sku_0000", 30),
                          _buy("sku_0001", 1)]).run("x", now=NOW)
    assert t.spent == RICE

def test_observe_mode_lets_the_same_script_overspend(tmp_path):
    t = _agent(tmp_path, [_buy("sku_0000", 30)], mode=Mode.OBSERVE).run("x", now=NOW)
    assert t.decisions[0].verdict is Verdict.DENY and t.spent == Paise(30 * int(DAL))

def test_agent_stops_at_max_steps(tmp_path):
    calls = [_buy(f"sku_{i:04d}", 1) for i in range(50)]
    a = _agent(tmp_path, calls); a.max_steps = 5
    assert a.run("x", now=NOW).stopped_reason == "max_steps"
