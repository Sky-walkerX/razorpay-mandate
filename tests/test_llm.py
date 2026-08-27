import pytest

from mandate.llm import AnthropicProvider, GeminiProvider, provider_for

TOOLS = [{
    "name": "create_order",
    "description": "Create an order.",
    "input_schema": {
        "type": "object",
        "properties": {"merchant": {"type": "string"}},
        "required": ["merchant"]},
}]


class _Step:
    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _Interaction:
    def __init__(self, steps):
        self.steps = steps
        self.id = "int_1"


class _FakeGemini:
    """Stands in for google.genai.Client. Records the body it was sent."""

    def __init__(self, steps):
        self.calls = []
        self._steps = steps
        self.interactions = self

    def create(self, **body):
        self.calls.append(body)
        return _Interaction(self._steps)


def _fc(**kw):
    kw.setdefault("name", "create_order")
    kw.setdefault("arguments", {})
    kw.setdefault("id", "call_1")
    return _Step("function_call", **kw)


def test_gemini_sends_system_instruction_as_a_top_level_field():
    c = _FakeGemini([_fc(arguments={"merchant": "zepto"})])
    GeminiProvider(client=c, seed=7).next_tool_call(
        "BE A SHOPPER", [{"role": "user", "text": "buy dal"}], TOOLS)
    body = c.calls[0]
    assert body["system_instruction"] == "BE A SHOPPER"
    assert body["model"] == "gemini-3.7-flash"


def test_gemini_never_stores_state_server_side():
    """The corpus carries injection payloads and a run must replay from a local log."""
    c = _FakeGemini([_fc()])
    GeminiProvider(client=c).next_tool_call("s", [{"role": "user", "text": "x"}], TOOLS)
    assert c.calls[0]["store"] is False
    assert "previous_interaction_id" not in c.calls[0]


def test_gemini_requests_temperature_zero_and_the_seed():
    c = _FakeGemini([_fc()])
    GeminiProvider(client=c, seed=99).next_tool_call(
        "s", [{"role": "user", "text": "x"}], TOOLS)
    cfg = c.calls[0]["generation_config"]
    assert cfg["temperature"] == 0.0
    assert cfg["seed"] == 99


def test_gemini_translates_input_schema_to_parameters():
    c = _FakeGemini([_fc()])
    GeminiProvider(client=c).next_tool_call("s", [{"role": "user", "text": "x"}], TOOLS)
    tool = c.calls[0]["tools"][0]
    assert tool["type"] == "function"
    assert tool["name"] == "create_order"
    assert tool["parameters"] == TOOLS[0]["input_schema"]
    assert "input_schema" not in tool


def test_gemini_returns_the_tool_call_with_its_call_id():
    c = _FakeGemini([_fc(arguments={"merchant": "zepto"}, id="call_9")])
    got = GeminiProvider(client=c).next_tool_call(
        "s", [{"role": "user", "text": "x"}], TOOLS)
    assert got == ("create_order", {"merchant": "zepto"}, "call_9")


def test_gemini_parses_string_arguments():
    """Streaming and some responses hand back arguments as a JSON string."""
    c = _FakeGemini([_fc(arguments='{"merchant": "blinkit"}')])
    _, args, _ = GeminiProvider(client=c).next_tool_call(
        "s", [{"role": "user", "text": "x"}], TOOLS)
    assert args == {"merchant": "blinkit"}


def test_gemini_returns_none_when_the_model_stops():
    c = _FakeGemini([_Step("model_output", content=[])])
    assert GeminiProvider(client=c).next_tool_call(
        "s", [{"role": "user", "text": "x"}], TOOLS) is None


def test_gemini_renders_a_tool_result_in_the_function_result_shape():
    c = _FakeGemini([_fc(id="c2")])
    GeminiProvider(client=c).next_tool_call("s", [
        {"role": "user", "text": "buy dal"},
        {"role": "tool_result", "text": "REFUSED by category.deny",
         "call_id": "call_1", "name": "create_order"},
    ], TOOLS)
    fr = [m for m in c.calls[0]["input"] if m.get("type") == "function_result"]
    assert len(fr) == 1
    assert fr[0]["call_id"] == "call_1"
    assert fr[0]["name"] == "create_order"
    assert fr[0]["result"][0]["text"] == "REFUSED by category.deny"


def test_provider_for_prefers_the_explicit_name(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    monkeypatch.delenv("MANDATE_LLM_PROVIDER", raising=False)
    assert isinstance(provider_for("anthropic"), AnthropicProvider)
    assert isinstance(provider_for("gemini"), GeminiProvider)


def test_provider_for_picks_gemini_when_only_that_key_is_set(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MANDATE_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert isinstance(provider_for(), GeminiProvider)


def test_provider_for_rejects_a_placeholder_key(monkeypatch):
    """The exact failure that produced 576 scripted rows."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MANDATE_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxxxxxxx")
    with pytest.raises(RuntimeError, match="placeholder"):
        provider_for()


def test_provider_for_raises_when_no_key_is_set(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MANDATE_LLM_PROVIDER", raising=False)
    with pytest.raises(RuntimeError, match="no LLM key"):
        provider_for()
