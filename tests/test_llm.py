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
        self._body = {"type": type_, **kw}
        for k, v in kw.items():
            setattr(self, k, v)

    def model_dump(self):
        return dict(self._body)


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
    assert body["model"] == "gemini-3.6-flash"


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
    name, args, call_id, _raw = GeminiProvider(client=c).next_tool_call(
        "s", [{"role": "user", "text": "x"}], TOOLS)
    assert (name, args, call_id) == ("create_order", {"merchant": "zepto"}, "call_9")


def test_gemini_parses_string_arguments():
    """Streaming and some responses hand back arguments as a JSON string."""
    c = _FakeGemini([_fc(arguments='{"merchant": "blinkit"}')])
    _, args, _, _ = GeminiProvider(client=c).next_tool_call(
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
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MANDATE_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert isinstance(provider_for(), GeminiProvider)


def test_provider_for_rejects_a_placeholder_key(monkeypatch):
    """The exact failure that produced 576 scripted rows."""
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("MANDATE_LLM_PROVIDER", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxxxxxxx")
    with pytest.raises(RuntimeError, match="placeholder"):
        provider_for()


def test_provider_for_falls_back_to_ollama_when_no_key_is_set(monkeypatch):
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("MANDATE_LLM_PROVIDER", raising=False)
    from mandate.llm import OllamaProvider

    p = provider_for()
    assert isinstance(p, OllamaProvider)
    assert p.model == "qwen3.5:4b"


def test_gemini_echoes_the_models_function_call_back_into_history():
    """Stateless mode requires the real function_call step, not synthesised text.

    A function_result whose call_id has no matching function_call in the input
    is rejected with 400 invalid_request.
    """
    c = _FakeGemini([_fc(id="c2")])
    GeminiProvider(client=c).next_tool_call("s", [
        {"role": "user", "text": "buy dal"},
        {"role": "assistant_call", "name": "create_order",
         "args": {"merchant": "zepto"}, "call_id": "call_1"},
        {"role": "tool_result", "text": "REFUSED by category.deny",
         "call_id": "call_1", "name": "create_order"},
    ], TOOLS)
    sent = c.calls[0]["input"]
    call_steps = [m for m in sent if m.get("type") == "function_call"]
    assert len(call_steps) == 1
    assert call_steps[0]["id"] == "call_1"
    assert call_steps[0]["name"] == "create_order"
    assert call_steps[0]["arguments"] == {"merchant": "zepto"}
    # and it must precede the result that references it
    assert sent.index(call_steps[0]) < next(
        i for i, m in enumerate(sent) if m.get("type") == "function_result")


def test_anthropic_renders_an_assistant_call_as_text():
    """The neutral history has to survive translation to a vendor without steps."""
    class _Blk:
        def __init__(self):
            self.type = "tool_use"
            self.name = "create_order"
            self.input = {"merchant": "zepto"}
            self.id = "t1"

    class _Resp:
        def __init__(self):
            self.content = [_Blk()]

    class _C:
        def __init__(self):
            self.calls = []
            self.messages = self

        def create(self, **kw):
            self.calls.append(kw)
            return _Resp()

    c = _C()
    AnthropicProvider(client=c).next_tool_call("s", [
        {"role": "user", "text": "buy dal"},
        {"role": "assistant_call", "name": "create_order",
         "args": {"merchant": "zepto"}, "call_id": "call_1"},
    ], TOOLS)
    roles = [m["role"] for m in c.calls[0]["messages"]]
    assert roles == ["user", "assistant"]
    assert "create_order" in c.calls[0]["messages"][1]["content"]


def test_gemini_returns_the_raw_steps_for_verbatim_echo():
    """Gemini 3 emits a thought step with a signature that must round-trip.

    Reconstructing only the function_call drops it and the next turn is
    rejected with 400 invalid_request. Verified against the live API.
    """
    c = _FakeGemini([_Step("thought", signature="SIG"), _fc(id="c1")])
    got = GeminiProvider(client=c).next_tool_call(
        "s", [{"role": "user", "text": "x"}], TOOLS)
    assert got is not None
    _, _, call_id, raw = got
    assert call_id == "c1"
    assert [s["type"] for s in raw] == ["thought", "function_call"]
    assert raw[0]["signature"] == "SIG"


def test_gemini_splices_raw_steps_back_in_verbatim():
    c = _FakeGemini([_fc(id="c2")])
    GeminiProvider(client=c).next_tool_call("s", [
        {"role": "user", "text": "buy dal"},
        {"role": "assistant_raw", "steps": [
            {"type": "thought", "signature": "SIG"},
            {"type": "function_call", "id": "c1", "name": "create_order",
             "arguments": {"merchant": "zepto"}}]},
        {"role": "tool_result", "text": "OK", "call_id": "c1", "name": "create_order"},
    ], TOOLS)
    sent = c.calls[0]["input"]
    assert sent[1] == {"type": "thought", "signature": "SIG"}
    assert sent[2]["type"] == "function_call" and sent[2]["id"] == "c1"
    assert sent[3]["type"] == "function_result"


def test_anthropic_ignores_opaque_gemini_steps():
    """A history recorded against one vendor must not crash the other."""
    class _Blk:
        def __init__(self):
            self.type, self.name, self.input, self.id = (
                "tool_use", "create_order", {}, "t1")

    class _Resp:
        def __init__(self):
            self.content = [_Blk()]

    class _C:
        def __init__(self):
            self.calls = []
            self.messages = self

        def create(self, **kw):
            self.calls.append(kw)
            return _Resp()

    c = _C()
    AnthropicProvider(client=c).next_tool_call("s", [
        {"role": "user", "text": "buy dal"},
        {"role": "assistant_raw", "steps": [{"type": "thought", "signature": "SIG"}]},
    ], TOOLS)
    assert [m["role"] for m in c.calls[0]["messages"]] == ["user"]


def test_gemini_rotates_across_keys():
    """Two free-tier keys double the quota, and the sweep needs every request."""
    made = []

    def factory(api_key):
        made.append(api_key)
        return _FakeGemini([_fc()])

    p = GeminiProvider(api_keys=["k1", "k2"], client_factory=factory)
    for _ in range(4):
        p.next_tool_call("s", [{"role": "user", "text": "x"}], TOOLS)
    assert made == ["k1", "k2"]          # one client built per key, then reused
    assert p._used == ["k1", "k2", "k1", "k2"]


class _FakeHttpxResponse:
    def __init__(self, json_data, status_code=200):
        self._json = json_data
        self.status_code = status_code

    def json(self):
        return self._json

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeHttpxClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json=None, **kw):
        self.calls.append({"url": url, "json": json, **kw})
        return self.responses.pop(0)


def test_ollama_provider_sends_tool_schema_and_messages():
    resp = _FakeHttpxResponse({
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call_123",
                    "function": {
                        "name": "create_order",
                        "arguments": {"merchant": "zepto"}
                    }
                }
            ]
        }
    })
    client = _FakeHttpxClient([resp])
    from mandate.llm import OllamaProvider

    p = OllamaProvider(model="qwen3.5:9b", seed=42, client=client)
    res = p.next_tool_call("You are a shopper", [{"role": "user", "text": "buy milk"}], TOOLS)
    assert res == ("create_order", {"merchant": "zepto"}, "call_123", [
        {"type": "function_call", "name": "create_order", "arguments": {"merchant": "zepto"}, "id": "call_123"}
    ])
    payload = client.calls[0]["json"]
    assert payload["model"] == "qwen3.5:9b"
    assert payload["options"]["seed"] == 42
    assert payload["options"]["temperature"] == 0.0
    assert payload["tools"][0]["function"]["name"] == "create_order"


def test_ollama_provider_returns_none_when_no_tool_calls():
    resp = _FakeHttpxResponse({"message": {"role": "assistant", "content": "Done!"}})
    client = _FakeHttpxClient([resp])
    from mandate.llm import OllamaProvider

    p = OllamaProvider(model="qwen3.5:9b", client=client)
    res = p.next_tool_call("s", [{"role": "user", "text": "x"}], TOOLS)
    assert res is None


def test_ollama_provider_next_text():
    resp = _FakeHttpxResponse({"message": {"role": "assistant", "content": '{"budget.total": 200000}'}})
    client = _FakeHttpxClient([resp])
    from mandate.llm import OllamaProvider

    p = OllamaProvider(model="qwen3.5:9b", client=client)
    text = p.next_text("s", [{"role": "user", "text": "x"}])
    assert text == '{"budget.total": 200000}'


def test_provider_for_picks_ollama(monkeypatch):
    monkeypatch.setenv("MANDATE_LLM_PROVIDER", "ollama")
    from mandate.llm import OllamaProvider
    p = provider_for()
    assert isinstance(p, OllamaProvider)
    assert p.model == "qwen3.5:4b"


def test_dashscope_provider_sends_openai_format():
    resp = _FakeHttpxResponse({
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "call_ds_1",
                            "type": "function",
                            "function": {
                                "name": "create_order",
                                "arguments": '{"merchant": "zepto"}'
                            }
                        }
                    ]
                }
            }
        ]
    })
    client = _FakeHttpxClient([resp])
    from mandate.llm import DashScopeProvider

    p = DashScopeProvider(api_key="ds-key-123", model="qwen3.5-flash", seed=7, client=client)
    res = p.next_tool_call("You are a shopper", [{"role": "user", "text": "buy milk"}], TOOLS)
    assert res == ("create_order", {"merchant": "zepto"}, "call_ds_1", [
        {"type": "function_call", "name": "create_order", "arguments": {"merchant": "zepto"}, "id": "call_ds_1"}
    ])
    call = client.calls[0]
    assert call["url"] == "https://dashscope-intl.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert call["json"]["model"] == "qwen3.5-flash"
    assert call["json"]["seed"] == 7


def test_provider_for_picks_dashscope(monkeypatch):
    monkeypatch.setenv("DASHSCOPE_API_KEY", "ds-real-key-123")
    monkeypatch.delenv("MANDATE_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    from mandate.llm import DashScopeProvider
    p = provider_for()
    assert isinstance(p, DashScopeProvider)
    assert p.model == "qwen3.8-flash"


QUOTA_MSG = (
    "Error code: 429 - {'error': {'message': 'You exceeded your current quota, "
    "please check your plan and billing details. * Quota exceeded for metric: "
    "generativelanguage.googleapis.com/generate_content_free_tier_requests, "
    "limit: 20, model: gemini-3.6-flash\\nPlease retry in 37.428340482s.', "
    "'code': 'too_many_requests'}}"
)


class _FlakyGemini:
    """Raises the queued exceptions, then answers. One entry consumed per call."""

    def __init__(self, script, steps=None):
        self.calls = []
        self._script = list(script)
        self._steps = steps if steps is not None else [_fc()]
        self.interactions = self

    def create(self, **body):
        self.calls.append(body)
        if self._script:
            exc = self._script.pop(0)
            if exc is not None:
                raise exc
        return _Interaction(self._steps)


def _quota_provider(scripts, sleeps, **kw):
    """One flaky client per key, sharing a recording sleep."""
    clients = {}

    def factory(api_key):
        clients[api_key] = _FlakyGemini(scripts[api_key])
        return clients[api_key]

    p = GeminiProvider(api_keys=list(scripts), client_factory=factory,
                       sleep=sleeps.append, **kw)
    return p, clients


def test_gemini_reads_the_delay_the_api_asks_for():
    from mandate.llm import _retry_after

    assert _retry_after(QUOTA_MSG) == pytest.approx(37.428340482)
    assert _retry_after("429 RESOURCE_EXHAUSTED 'retryDelay': '12s'") == 12.0
    assert _retry_after("400 invalid_request") is None


def test_gemini_rotates_to_the_next_key_before_it_sleeps():
    """A second key with quota left is free. Sleeping first would waste 37s."""
    sleeps = []
    p, clients = _quota_provider(
        {"k1": [RuntimeError(QUOTA_MSG)], "k2": []}, sleeps)

    name, _, _, _ = p.next_tool_call("s", [{"role": "user", "text": "x"}], TOOLS)

    assert name == "create_order"
    assert sleeps == []
    assert len(clients["k1"].calls) == 1 and len(clients["k2"].calls) == 1


def test_gemini_sleeps_the_asked_delay_once_every_key_is_out():
    """The 37s in the error body is a per-minute window. Waiting it out clears it."""
    sleeps = []
    p, clients = _quota_provider(
        {"k1": [RuntimeError(QUOTA_MSG)], "k2": [RuntimeError(QUOTA_MSG)]}, sleeps)

    name, _, _, _ = p.next_tool_call("s", [{"role": "user", "text": "x"}], TOOLS)

    assert name == "create_order"
    assert sleeps == [pytest.approx(37.428340482)]
    assert len(clients["k1"].calls) == 2      # tried again after the wait


def test_gemini_gives_up_after_the_retry_budget():
    """A daily cap never clears. The run must die rather than sleep forever."""
    sleeps = []
    always = [RuntimeError(QUOTA_MSG)] * 50
    p, _ = _quota_provider({"k1": list(always), "k2": list(always)}, sleeps,
                           quota_rounds=3)

    with pytest.raises(RuntimeError, match="quota"):
        p.next_tool_call("s", [{"role": "user", "text": "x"}], TOOLS)

    assert len(sleeps) == 2                   # slept between rounds, not after the last


def test_gemini_caps_an_absurd_retry_delay():
    sleeps = []
    p, _ = _quota_provider(
        {"k1": [RuntimeError("429 quota. Please retry in 8600s.")]},
        sleeps, quota_rounds=2)
    p.next_tool_call("s", [{"role": "user", "text": "x"}], TOOLS)

    assert sleeps == [60.0]


def test_gemini_does_not_sleep_on_a_non_quota_error():
    sleeps = []
    p, _ = _quota_provider({"k1": [RuntimeError("400 invalid_request")]}, sleeps)

    with pytest.raises(RuntimeError, match="invalid_request"):
        p.next_tool_call("s", [{"role": "user", "text": "x"}], TOOLS)

    assert sleeps == []
