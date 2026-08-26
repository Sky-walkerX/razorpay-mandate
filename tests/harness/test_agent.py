from datetime import datetime, timezone, timedelta
from mandate.adapters.direct import DirectClient
from mandate.harness.agent import ShoppingAgent, AgentTrace
from mandate.harness.catalog import generate_catalog
from mandate.gateway.core import Gateway, Mode
from mandate.gateway.audit import AuditLog
from mandate.gateway.idem import Ledger
from mandate.gateway.state import Verdict
from mandate.downstream.fake import FakeDownstream
from mandate.money import rupees
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


def _agent(tmp_path, calls, mode=Mode.ENFORCE):
    gw = Gateway(policy=_pol(), downstream=FakeDownstream(),
                 audit=AuditLog(tmp_path / "a.jsonl"), mode=mode,
                 ledger=Ledger(tmp_path / "l.jsonl"))
    return ShoppingAgent(client=DirectClient(gw), catalog=generate_catalog(seed=7),
                         model=ScriptedModel(calls))

def _buy(sku, qty, unit_rupees):
    return ("create_order", {"merchant": "zepto", "items":
            [{"sku": sku, "title": "Toor Dal", "qty": qty,
              "unit_price": int(rupees(unit_rupees))}]})

def test_agent_completes_an_allowed_purchase(tmp_path):
    t = _agent(tmp_path, [_buy("sku_0000", 1, 500)]).run("buy dal", now=NOW)
    assert t.decisions[0].verdict is Verdict.ALLOW and t.spent == rupees(500)

def test_agent_records_a_denial_and_keeps_its_trace(tmp_path):
    t = _agent(tmp_path, [_buy("sku_0000", 1, 50000)]).run("buy dal", now=NOW)
    assert t.decisions[0].verdict is Verdict.DENY and t.spent == 0

def test_spent_counts_only_executed_actions(tmp_path):
    t = _agent(tmp_path, [_buy("sku_0000", 1, 50000),
                          _buy("sku_0001", 1, 300)]).run("x", now=NOW)
    assert t.spent == rupees(300)

def test_observe_mode_lets_the_same_script_overspend(tmp_path):
    t = _agent(tmp_path, [_buy("sku_0000", 1, 50000)], mode=Mode.OBSERVE).run("x", now=NOW)
    assert t.decisions[0].verdict is Verdict.DENY and t.spent == rupees(50000)

def test_agent_stops_at_max_steps(tmp_path):
    calls = [_buy(f"sku_{i:04d}", 1, 10) for i in range(50)]
    a = _agent(tmp_path, calls); a.max_steps = 5
    assert a.run("x", now=NOW).stopped_reason == "max_steps"
