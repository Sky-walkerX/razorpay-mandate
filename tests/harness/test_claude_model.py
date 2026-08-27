import json
from pathlib import Path

import pytest

from mandate.gateway.core import Decision
from mandate.gateway.state import Verdict
from mandate.harness.agent import AgentTrace
from mandate.harness.catalog import generate_catalog
from mandate.harness.claude_model import MODEL, ClaudeModel, render_catalog


class StubAnthropic:
    def __init__(self, blocks):
        self.blocks, self.seen = blocks, []

    class _M:
        def __init__(self, outer):
            self.outer = outer

        def create(self, **kw):
            self.outer.seen.append(kw)

            class R:
                pass

            r = R()
            r.content = self.outer.blocks.pop(0)
            r.stop_reason = "tool_use"
            return r

    @property
    def messages(self):
        return self._M(self)


class _ToolUse:
    type = "tool_use"

    def __init__(self, name, inp):
        self.name, self.input, self.id = name, inp, "tu_1"


class _Text:
    type = "text"

    def __init__(self, t):
        self.text = t


class _FakeClient:
    """Records kwargs so we can assert what was sent to the API."""

    def __init__(self, blocks):
        self.calls = []
        self.messages = self
        self._blocks = blocks

    def create(self, **kw):
        self.calls.append(kw)
        return _FakeResp(self._blocks)


class _FakeResp:
    def __init__(self, blocks):
        self.content = blocks


def _trace():
    return AgentTrace()


def test_catalog_render_includes_every_seller_controlled_field():
    """Descriptions, seller names and reviews all reach the model. That is the attack surface."""
    out = render_catalog(generate_catalog(seed=7))
    p = generate_catalog(seed=7).products[0]
    assert p.description in out and p.seller in out and p.reviews[0] in out


def test_tool_use_block_becomes_a_call():
    m = ClaudeModel(
        generate_catalog(seed=7),
        "buy dal",
        client=StubAnthropic([[_ToolUse("create_order", {"merchant": "zepto", "items": []})]]),
    )
    assert m.next_call(AgentTrace()) == ("create_order", {"merchant": "zepto", "items": []})


def test_text_only_response_ends_the_run():
    m = ClaudeModel(
        generate_catalog(seed=7),
        "buy dal",
        client=StubAnthropic([[_Text("I am done shopping.")]]),
    )
    assert m.next_call(AgentTrace()) is None


def test_denial_is_fed_back_so_a_benign_agent_can_adapt():
    stub = StubAnthropic([[_ToolUse("create_order", {"merchant": "zepto", "items": []})]])
    m = ClaudeModel(generate_catalog(seed=7), "buy dal", client=stub)
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
    convo = str(stub.seen[-1]["messages"])
    assert "budget.per_transaction" in convo


def test_driver_does_not_send_temperature():
    client = _FakeClient([_ToolUse("create_order", {"merchant": "zepto", "items": []})])
    m = ClaudeModel(generate_catalog(seed=1), "buy dal", client=client)
    m.next_call(_trace())
    assert "temperature" not in client.calls[0]
    assert client.calls[0]["model"] == MODEL


def test_driver_logs_every_call(tmp_path: Path):
    log = tmp_path / "model_calls.jsonl"
    client = _FakeClient([_ToolUse("create_order", {"merchant": "zepto", "items": []})])
    m = ClaudeModel(generate_catalog(seed=1), "buy dal", client=client, call_log=log)
    m.next_call(_trace())
    rows = [json.loads(ln) for ln in log.read_text().splitlines() if ln.strip()]
    assert len(rows) == 1
    assert rows[0]["tool_use"] == {
        "name": "create_order",
        "input": {"merchant": "zepto", "items": []},
    }


def test_a_transient_failure_is_retried(monkeypatch):
    monkeypatch.setattr("mandate.harness.claude_model.time.sleep", lambda _s: None)
    calls = {"n": 0}

    class _Flaky(_FakeClient):
        def create(self, **kw):
            calls["n"] += 1
            if calls["n"] < 3:
                raise RuntimeError("rate_limit_error: slow down")
            return super().create(**kw)

    client = _Flaky([_ToolUse("create_order", {"merchant": "zepto", "items": []})])
    m = ClaudeModel(generate_catalog(seed=1), "buy dal", client=client)
    assert m.next_call(_trace()) is not None
    assert calls["n"] == 3


def test_a_programming_error_is_not_retried(monkeypatch):
    monkeypatch.setattr("mandate.harness.claude_model.time.sleep", lambda _s: None)
    calls = {"n": 0}

    class _Broken(_FakeClient):
        def create(self, **kw):
            calls["n"] += 1
            raise TypeError("unexpected keyword argument 'temperature'")

    client = _Broken([])
    m = ClaudeModel(generate_catalog(seed=1), "buy dal", client=client)
    with pytest.raises(TypeError):
        m.next_call(_trace())
    assert calls["n"] == 1, "a TypeError is a bug, not a transient failure"
