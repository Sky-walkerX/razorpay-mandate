import json
from pathlib import Path

import pytest

from mandate.gateway.core import Decision
from mandate.gateway.state import Verdict
from mandate.harness.agent import AgentTrace
from mandate.harness.agent_model import AgentModel, render_catalog
from mandate.harness.catalog import generate_catalog


class _FakeProvider:
    def __init__(self, responses, model="fake-model"):
        self.responses = list(responses)
        self.model = model
        self.seen = []

    def next_tool_call(self, system, history, tools):
        self.seen.append({"system": system, "history": list(history), "tools": tools})
        if not self.responses:
            return None
        return self.responses.pop(0)


def _trace():
    return AgentTrace()


def test_catalog_render_includes_every_seller_controlled_field():
    """Descriptions, seller names and reviews all reach the model. That is the attack surface."""
    out = render_catalog(generate_catalog(seed=7))
    p = generate_catalog(seed=7).products[0]
    assert p.description in out and p.seller in out and p.reviews[0] in out


def test_tool_use_block_becomes_a_call():
    prov = _FakeProvider([("create_order", {"merchant": "zepto", "items": []}, "call_1")])
    m = AgentModel(generate_catalog(seed=7), "buy dal", provider=prov)
    assert m.next_call(AgentTrace()) == ("create_order", {"merchant": "zepto", "items": []})


def test_text_only_response_ends_the_run():
    prov = _FakeProvider([])
    m = AgentModel(generate_catalog(seed=7), "buy dal", provider=prov)
    assert m.next_call(AgentTrace()) is None


def test_denial_is_fed_back_so_a_benign_agent_can_adapt():
    prov = _FakeProvider([("create_order", {"merchant": "zepto", "items": []}, "call_1")])
    m = AgentModel(generate_catalog(seed=7), "buy dal", provider=prov)
    trace = AgentTrace(
        decisions=[
            Decision(
                verdict=Verdict.DENY,
                clause_id="budget.per_transaction",
                message="limit ₹2,000.00, attempted ₹500.00",
            )
        ]
    )
    m.next_call(trace)
    history_str = str(prov.seen[-1]["history"])
    assert "budget.per_transaction" in history_str


def test_driver_logs_every_call(tmp_path: Path):
    log = tmp_path / "model_calls.jsonl"
    prov = _FakeProvider([("create_order", {"merchant": "zepto", "items": []}, "call_1")])
    m = AgentModel(generate_catalog(seed=1), "buy dal", provider=prov, call_log=log)
    m.next_call(_trace())
    rows = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["tool_use"] == {
        "name": "create_order",
        "input": {"merchant": "zepto", "items": []},
    }


def test_a_transient_failure_is_retried(monkeypatch):
    monkeypatch.setattr("mandate.harness.agent_model.time.sleep", lambda _s: None)
    calls = {"n": 0}

    class _FlakyProvider(_FakeProvider):
        def next_tool_call(self, system, history, tools):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("rate_limit_error: slow down")
            return super().next_tool_call(system, history, tools)

    prov = _FlakyProvider([("create_order", {"merchant": "zepto", "items": []}, "call_1")])
    m = AgentModel(generate_catalog(seed=1), "buy dal", provider=prov)
    assert m.next_call(_trace()) is not None
    assert calls["n"] == 3


def test_a_programming_error_is_not_retried(monkeypatch):
    monkeypatch.setattr("mandate.harness.agent_model.time.sleep", lambda _s: None)
    calls = {"n": 0}

    class _BrokenProvider(_FakeProvider):
        def next_tool_call(self, system, history, tools):
            calls["n"] += 1
            raise TypeError("unexpected keyword argument")

    prov = _BrokenProvider([])
    m = AgentModel(generate_catalog(seed=1), "buy dal", provider=prov)
    with pytest.raises(TypeError):
        m.next_call(_trace())
    assert calls["n"] == 1, "a TypeError is a bug, not a transient failure"
