from mandate.gateway.core import Decision
from mandate.gateway.state import Verdict
from mandate.harness.agent import AgentTrace
from mandate.harness.catalog import generate_catalog
from mandate.harness.claude_model import ClaudeModel, render_catalog


class StubAnthropic:
    def __init__(self, blocks): self.blocks, self.seen = blocks, []
    class _M:
        def __init__(self, outer): self.outer = outer
        def create(self, **kw):
            self.outer.seen.append(kw)
            class R: pass
            r = R(); r.content = self.outer.blocks.pop(0); r.stop_reason = "tool_use"
            return r
    @property
    def messages(self): return self._M(self)


class _ToolUse:
    type = "tool_use"
    def __init__(self, name, inp): self.name, self.input, self.id = name, inp, "tu_1"


class _Text:
    type = "text"
    def __init__(self, t): self.text = t


def test_catalog_render_includes_every_seller_controlled_field():
    """Descriptions, seller names and reviews all reach the model. That is the attack surface."""
    out = render_catalog(generate_catalog(seed=7))
    p = generate_catalog(seed=7).products[0]
    assert p.description in out and p.seller in out and p.reviews[0] in out

def test_tool_use_block_becomes_a_call():
    m = ClaudeModel(generate_catalog(seed=7), "buy dal",
                    client=StubAnthropic([[_ToolUse("create_order", {"merchant": "zepto",
                                                                     "items": []})]]))
    assert m.next_call(AgentTrace()) == ("create_order", {"merchant": "zepto", "items": []})

def test_text_only_response_ends_the_run():
    m = ClaudeModel(generate_catalog(seed=7), "buy dal",
                    client=StubAnthropic([[_Text("I am done shopping.")]]))
    assert m.next_call(AgentTrace()) is None

def test_denial_is_fed_back_so_a_benign_agent_can_adapt():
    stub = StubAnthropic([[_ToolUse("create_order", {"merchant": "zepto", "items": []})]])
    m = ClaudeModel(generate_catalog(seed=7), "buy dal", client=stub)
    trace = AgentTrace(decisions=[Decision(verdict=Verdict.DENY,
                                           clause_id="budget.per_transaction",
                                           message="limit ₹2,000.00, attempted ₹500.00")])
    m.next_call(trace)
    convo = str(stub.seen[-1]["messages"])
    assert "budget.per_transaction" in convo
