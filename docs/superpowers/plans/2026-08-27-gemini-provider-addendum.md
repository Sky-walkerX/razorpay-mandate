# Gemini Provider Addendum

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Move both LLM callers, the intent compiler and the agent under test, onto `gemini-3.7-flash` behind a provider interface, so the evaluation can actually run.

**Architecture:** A small provider shim exposes one operation, "given a system prompt, a history and a tool list, return the next tool call or None". Two implementations sit behind it: Gemini via the Interactions API, and the existing Anthropic path. The compiler and the agent driver both call the shim, so neither knows which vendor answered.

**Tech Stack:** `google-genai>=2.20` (installed, 2.20.0). Python 3.12, pydantic v2, pytest.

**Spec:** [`../specs/2026-08-27-honest-containment-measurement-design.md`](../specs/2026-08-27-honest-containment-measurement-design.md). This addendum continues [`2026-08-27-honest-containment-measurement.md`](2026-08-27-honest-containment-measurement.md), whose Tasks 1 to 9 are complete and whose Task 10 never ran.

## Why this exists

`.env` carries the literal placeholder `sk-ant-xxxxxxxx` copied from `.env.example`. The Anthropic key has never been set, so `mandate compile` and the agent driver have never executed. Both the original build and the Task 1 to 9 build fell back to a scripted model, which is why all 576 committed result rows are tagged `model=scripted` and why `baseline` and `compromised` are identical to the decimal.

## Verified API facts

Checked against `ai.google.dev` on 2026-08-27 and against the installed SDK, not from memory.

- `gemini-3.7-flash` is the current stable Flash model. Endpoint id is exactly `gemini-3.7-flash`.
- The Interactions API is the recommended path for Gemini 3. `client.interactions.create` in SDK 2.20.0 signs as `create(*, request=None, ..., **body)`, so the documented keyword form passes straight through.
- `system_instruction` is a top-level keyword, not a message role. The compromised arm depends on this.
- `generation_config` accepts `temperature` and `seed`.
- Tools are plain dicts: `{"type": "function", "name", "description", "parameters"}`, where `parameters` is ordinary JSON Schema. The existing `adapters.direct.TOOLS` entries need only `input_schema` renamed to `parameters`.
- A response carries `.steps`; a tool call is a step with `.type == "function_call"`, `.name`, `.arguments`, `.id`.
- Results go back as `{"type": "function_result", "name", "call_id", "result": [{"type": "text", "text": ...}]}`.

## Global constraints

- **Stateless only.** Every call passes `store=False` and the full local history. Never `previous_interaction_id`. Three reasons: the corpus carries prompt-injection payloads that should not be retained server-side; a run must be re-scorable from a local log alone, which is the project's whole replayability claim; and 576 runs against server-side state introduce a failure mode the harness cannot audit.
- **Determinism is requested, not assumed.** `temperature: 0.0` and a per-item `seed` go on every call, and the docs describe `seed` as best-effort. The README says best-effort and points at `model_calls.jsonl` as the actual reproducibility mechanism.
- **The compiler and the agent share a model.** This is a deliberate choice, taken with the tradeoff understood, and it is recorded as a stated limitation rather than left for a reviewer to notice.
- **No test makes a network call.** Every test injects a fake client.
- **Commit after every task.**

---

# Task 11: The provider shim

**Files:**
- Create: `src/mandate/llm.py`
- Modify: `pyproject.toml` (add `google-genai>=2.20`)
- Test: `tests/test_llm.py`

**Interfaces:**
- Produces:
  - `ToolCall = tuple[str, dict]`
  - `class Provider(Protocol): model: str; def next_tool_call(self, system: str, history: list[dict], tools: list[dict]) -> ToolCall | None`
  - `GeminiProvider(model="gemini-3.7-flash", client=None, api_key=None, seed=None)`
  - `AnthropicProvider(model="claude-opus-5", client=None, api_key=None)`
  - `provider_for(name: str | None = None, **kw) -> Provider`, resolving from `MANDATE_LLM_PROVIDER`, else `GEMINI_API_KEY`, else `ANTHROPIC_API_KEY`.
  - `HISTORY`: the neutral history format both providers translate from. A list of dicts, each `{"role": "user"|"assistant"|"tool_result", "text": str}` plus optional `"call_id"` and `"name"` on a tool result.

- [ ] **Step 1: Write the failing test**

Create `tests/test_llm.py`:

```python
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


def test_gemini_sends_system_instruction_as_a_top_level_field():
    c = _FakeGemini([_Step("function_call", name="create_order",
                           arguments={"merchant": "zepto"}, id="call_1")])
    p = GeminiProvider(client=c, seed=7)
    p.next_tool_call("BE A SHOPPER", [{"role": "user", "text": "buy dal"}], TOOLS)
    body = c.calls[0]
    assert body["system_instruction"] == "BE A SHOPPER"
    assert body["model"] == "gemini-3.7-flash"


def test_gemini_never_stores_state_server_side():
    """The corpus carries injection payloads and a run must replay from a local log."""
    c = _FakeGemini([_Step("function_call", name="create_order",
                           arguments={}, id="call_1")])
    GeminiProvider(client=c).next_tool_call("s", [{"role": "user", "text": "x"}], TOOLS)
    assert c.calls[0]["store"] is False
    assert "previous_interaction_id" not in c.calls[0]


def test_gemini_requests_temperature_zero_and_the_seed():
    c = _FakeGemini([_Step("function_call", name="create_order", arguments={}, id="c")])
    GeminiProvider(client=c, seed=99).next_tool_call(
        "s", [{"role": "user", "text": "x"}], TOOLS)
    cfg = c.calls[0]["generation_config"]
    assert cfg["temperature"] == 0.0
    assert cfg["seed"] == 99


def test_gemini_translates_input_schema_to_parameters():
    c = _FakeGemini([_Step("function_call", name="create_order", arguments={}, id="c")])
    GeminiProvider(client=c).next_tool_call("s", [{"role": "user", "text": "x"}], TOOLS)
    tool = c.calls[0]["tools"][0]
    assert tool["type"] == "function"
    assert tool["name"] == "create_order"
    assert tool["parameters"] == TOOLS[0]["input_schema"]
    assert "input_schema" not in tool


def test_gemini_returns_the_tool_call():
    c = _FakeGemini([_Step("function_call", name="create_order",
                           arguments={"merchant": "zepto"}, id="call_1")])
    got = GeminiProvider(client=c).next_tool_call(
        "s", [{"role": "user", "text": "x"}], TOOLS)
    assert got == ("create_order", {"merchant": "zepto"})


def test_gemini_returns_none_when_the_model_stops():
    c = _FakeGemini([_Step("model_output", content=[])])
    assert GeminiProvider(client=c).next_tool_call(
        "s", [{"role": "user", "text": "x"}], TOOLS) is None


def test_gemini_renders_a_tool_result_in_the_function_result_shape():
    c = _FakeGemini([_Step("function_call", name="create_order", arguments={}, id="c2")])
    GeminiProvider(client=c).next_tool_call("s", [
        {"role": "user", "text": "buy dal"},
        {"role": "tool_result", "text": "REFUSED by category.deny",
         "call_id": "call_1", "name": "create_order"},
    ], TOOLS)
    fr = [m for m in c.calls[0]["input"] if m.get("type") == "function_result"]
    assert len(fr) == 1
    assert fr[0]["call_id"] == "call_1"
    assert fr[0]["result"][0]["text"] == "REFUSED by category.deny"


def test_provider_for_prefers_the_explicit_name(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "a")
    assert isinstance(provider_for("anthropic"), AnthropicProvider)
    assert isinstance(provider_for("gemini"), GeminiProvider)


def test_provider_for_picks_gemini_when_only_that_key_is_set(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert isinstance(provider_for(), GeminiProvider)


def test_provider_for_rejects_a_placeholder_key(monkeypatch):
    """The exact failure that produced 576 scripted rows."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-xxxxxxxx")
    with pytest.raises(RuntimeError, match="placeholder"):
        provider_for()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/pytest tests/test_llm.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'mandate.llm'`.

- [ ] **Step 3: Implement**

Create `src/mandate/llm.py`:

```python
"""One interface over two vendors, so nothing above it knows who answered.

Calls are stateless on purpose. The corpus carries prompt-injection payloads that
should not be retained server-side, and a run has to be re-scorable from a local
log alone. Both rule out previous_interaction_id.
"""
import os
from typing import Protocol

GEMINI_MODEL = "gemini-3.7-flash"
ANTHROPIC_MODEL = "claude-opus-5"

ToolCall = tuple[str, dict]


def _is_placeholder(key: str) -> bool:
    """Catches the .env.example value that produced 576 scripted result rows."""
    body = key.removeprefix("sk-ant-").removeprefix("rzp_test_")
    return not body or set(body.lower()) <= set("x")


class Provider(Protocol):
    model: str

    def next_tool_call(
        self, system: str, history: list[dict], tools: list[dict]
    ) -> ToolCall | None: ...


class GeminiProvider:
    def __init__(self, model: str = GEMINI_MODEL, client=None,
                 api_key: str | None = None, seed: int | None = None) -> None:
        if client is None:
            from google import genai
            client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self.client, self.model, self.seed = client, model, seed

    @staticmethod
    def _tools(tools: list[dict]) -> list[dict]:
        return [{"type": "function", "name": t["name"],
                 "description": t.get("description", ""),
                 "parameters": t["input_schema"]} for t in tools]

    @staticmethod
    def _input(history: list[dict]) -> list[dict]:
        out = []
        for m in history:
            if m["role"] == "tool_result":
                out.append({"type": "function_result", "name": m.get("name", ""),
                            "call_id": m.get("call_id", ""),
                            "result": [{"type": "text", "text": m["text"]}]})
            else:
                kind = "user_input" if m["role"] == "user" else "model_output"
                out.append({"type": kind,
                            "content": [{"type": "text", "text": m["text"]}]})
        return out

    def next_tool_call(self, system, history, tools):
        cfg = {"temperature": 0.0}
        if self.seed is not None:
            cfg["seed"] = self.seed
        r = self.client.interactions.create(
            model=self.model, system_instruction=system,
            input=self._input(history), tools=self._tools(tools),
            generation_config=cfg, store=False)
        for step in r.steps:
            if getattr(step, "type", None) == "function_call":
                args = step.arguments
                if isinstance(args, str):
                    import json
                    args = json.loads(args or "{}")
                return step.name, dict(args or {}), step.id
        return None


class AnthropicProvider:
    def __init__(self, model: str = ANTHROPIC_MODEL, client=None,
                 api_key: str | None = None) -> None:
        if client is None:
            import anthropic
            client = anthropic.Anthropic(
                api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self.client, self.model = client, model

    def next_tool_call(self, system, history, tools):
        msgs = [{"role": "assistant" if m["role"] == "assistant" else "user",
                 "content": m["text"]} for m in history]
        r = self.client.messages.create(
            model=self.model, max_tokens=2000, system=system,
            tools=tools, messages=msgs)
        for block in r.content:
            if getattr(block, "type", None) == "tool_use":
                return block.name, dict(block.input), block.id
        return None


def provider_for(name: str | None = None, **kw) -> Provider:
    name = name or os.environ.get("MANDATE_LLM_PROVIDER")
    if name == "gemini":
        return GeminiProvider(**kw)
    if name == "anthropic":
        return AnthropicProvider(**{k: v for k, v in kw.items() if k != "seed"})
    for env, cls in (("GEMINI_API_KEY", GeminiProvider),
                     ("ANTHROPIC_API_KEY", AnthropicProvider)):
        key = os.environ.get(env)
        if not key:
            continue
        if _is_placeholder(key):
            raise RuntimeError(
                f"{env} is a placeholder value copied from .env.example. Set a real "
                "key. A placeholder here is what caused every result row to be "
                "scripted rather than measured.")
        return cls(**(kw if cls is GeminiProvider
                      else {k: v for k, v in kw.items() if k != "seed"}))
    raise RuntimeError("no LLM key set; expected GEMINI_API_KEY or ANTHROPIC_API_KEY")
```

Note `next_tool_call` returns a three-tuple `(name, args, call_id)`. The `call_id` is needed to
build the `function_result` on the next turn. Update the `ToolCall` alias and the tests'
expected values to match: `ToolCall = tuple[str, dict, str]`.

- [ ] **Step 4: Add the dependency**

In `pyproject.toml`, add `"google-genai>=2.20"` to `dependencies`.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/pytest tests/test_llm.py -v && .venv/bin/pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/mandate/llm.py tests/test_llm.py pyproject.toml
git commit -m "feat: provider shim over Gemini and Anthropic

Stateless calls only: the corpus carries injection payloads and a run has to
replay from a local log. Rejects a placeholder key outright, which is the
failure that made every committed result row scripted."
```

---

# Task 12: The agent driver moves onto the shim

**Files:**
- Create: `src/mandate/harness/agent_model.py` (replaces `claude_model.py`)
- Delete: `src/mandate/harness/claude_model.py`
- Modify: `src/mandate/cli.py` (`_model_factory`)
- Test: `tests/harness/test_agent_model.py` (replaces `test_claude_model.py`)

**Interfaces:**
- Consumes: `provider_for`, `ToolCall`.
- Produces: `AgentModel(catalog, intent, provider, compromised=False, call_log=None)` with `.model` and `.next_call(trace)`.

- [ ] **Step 1: Rename and rewrite the driver**

`AgentModel` keeps the existing `render_catalog`, `SYSTEM` and `SYSTEM_COMPROMISED` text verbatim and the existing retry helper. It replaces the direct `messages.create` call with `self.provider.next_tool_call(self.system, self.history, TOOLS)`, and maintains `self.history` in the neutral format, appending a `tool_result` entry carrying the `call_id` returned by the previous call.

A file named `claude_model.py` driving Gemini is the kind of drift that makes a reviewer distrust everything near it, so the file is renamed rather than kept.

- [ ] **Step 2: Port the existing tests**

`tests/harness/test_claude_model.py` moves to `test_agent_model.py`. Its fake client becomes a fake provider, which is simpler. The two retry tests and the call-log test carry over unchanged in intent.

- [ ] **Step 3: Point the factory at the shim**

In `cli._model_factory`, the real branch becomes:

```python
    from mandate.harness.agent_model import AgentModel
    from mandate.llm import provider_for
    return lambda catalog, intent, compromised, call_log: AgentModel(
        catalog, intent, provider=provider_for(seed=seed),
        compromised=compromised, call_log=call_log)
```

- [ ] **Step 4: Run the suite and commit**

```bash
.venv/bin/pytest -q && .venv/bin/ruff check src tests
git add -A && git commit -m "refactor: agent driver runs on any provider

claude_model.py renamed to agent_model.py; it no longer names a vendor."
```

---

# Task 13: The compiler moves onto the shim, and the policy is compiled for real

**Files:**
- Modify: `src/mandate/compiler/compile.py`
- Modify: `policies/policy.yaml` (regenerated)
- Modify: `README.md`, `SPEC.md`

**Interfaces:**
- Consumes: `provider_for`.
- Produces: a `policies/policy.yaml` whose `compiler:` block describes a model that actually ran.

- [ ] **Step 1: Route the compiler through the shim**

`compile.py` currently calls `self._c.messages.create(model=MODEL, ...)` and hardcodes
`CompilerInfo(model=MODEL, temperature=0.0, ...)`. Both come from the provider instead, so
`compiler.model` records what actually answered.

The compiler asks for structured output rather than a tool call, so it needs a text path on the
provider. Add `next_text(system, history) -> str` to both implementations alongside
`next_tool_call`, rather than forcing the compiler through a tool.

- [ ] **Step 2: Regenerate the policy**

```bash
.venv/bin/mandate compile "Order groceries for the week from Zepto, Blinkit or Instamart. \
Stay under Rs 2000 in total and Rs 1000 per order. No single item over Rs 500, \
and no more than 5 of any one item. Nothing alcoholic. At most 3 orders." \
  --hours 10 --out policies/policy.yaml
```

Then confirm `tests/policy/test_policy_covers_families.py` still passes, and that
`compiler.model` reads `gemini-3.7-flash` with a fresh `issued` timestamp. The current file
claims `claude-opus-5` and `temperature: 0.0` with an `issued` date of 2026-09-01, none of
which can be true, because no compiler has ever run here.

- [ ] **Step 3: Correct the documents**

- `SPEC.md` and `README.md`: the compiler runs on `gemini-3.7-flash` at `temperature: 0.0` with a
  fixed seed. Say that seed is best-effort per Google's own wording, and that the real
  reproducibility mechanism is `model_calls.jsonl`.
- Add to Limitations: the compiler and the agent under test are the same model, so the compiler is
  in some sense grading its own homework. State it rather than let a reviewer find it.
- Add to the argument: the gateway contains an agent built on a different vendor's model from the
  one this project's authors control. That is stronger evidence of model-independence than
  containing an agent from the same family, and it is worth one sentence in the README.

- [ ] **Step 4: Commit**

```bash
git add src/mandate/compiler policies/policy.yaml README.md SPEC.md
git commit -m "feat: compiler runs on the provider shim; policy compiled for real

The committed policy.yaml was hand-written while claiming a compiler produced
it. It is now generated by a model that actually ran."
```

---

# Task 14: The measurement

This is the original plan's Task 10, which never ran. It is unchanged except that it now has a
working model behind it. Follow it step by step from
[`2026-08-27-honest-containment-measurement.md`](2026-08-27-honest-containment-measurement.md#task-10-the-first-honest-run-and-the-documents-that-report-it).

- [ ] **Step 1: Confirm the driver works end to end before spending anything**

```bash
.venv/bin/mandate demo --family injection.description
```

Expected: two panes, real spend on at least one side, a named blocking clause on the enforced
side. If it prints `₹0.00` with an error, stop and fix that first. No number produced after a
failed demo is worth anything.

- [ ] **Step 2 onward: as per Task 10**

Cost probe, four-arm run, read the failures, fix the gateway, held-out run once, rewrite the
documents from the generated files.

---

## Status, 27 Aug

Tasks 11, 12 and 13 are done. Two further bugs were found and fixed while proving the path end to
end, both recorded in `BREAKAGE.md`: Gemini 3 signs its `thought` step and the signature must be
echoed back verbatim, and the retry helper never matched a 429 so every rate limit was fatal.

A single item has run end to end against `gemini-3.7-flash`. The pipeline works.

Task 14 is blocked on API quota. Free-tier limits observed in the error bodies were 5 and 20
requests per window; one item across two arms took over ten minutes, almost entirely 429 backoff.
The sweep is roughly 1,400 calls. More keys are coming; the provider already round-robins across
`GEMINI_API_KEY_2..N`.

---

# Task 15: Everything that does not need quota

Ordered so the repo is submittable even if the sweep never runs.

- [x] **README results section states that nothing has been measured**, rather than carrying a
  scripted table. Done 27 Aug.
- [x] **`BREAKAGE.md` entries** for the placeholder key, the hand-written policy, the thought
  signature and the 429 classification. Done 27 Aug.
- [x] **Repo layout and `.env.example` match reality.** Done 27 Aug.
- [ ] **Public GitHub repo.** `git remote add origin`, push `main`. The submission requires a
  public repo and there is currently no remote at all. Do this early; it is the one deliverable
  with no dependency on anything else.
- [ ] **`make demo` works from a clean checkout** with only `GEMINI_API_KEY` set. Currently true,
  but it has never been run from a fresh clone.
- [ ] **Pitch script and demo sequencing.** The split screen is the magic moment. It needs a
  pre-recorded fallback, because a live run at 5 requests per minute will stall on stage.
- [ ] **Architecture walkthrough.** The panel weights this above the demo. `ARCHITECTURE.md`
  exists and predates the oracle, the four arms and the provider shim; it needs a pass.

# Task 16: A throughput probe before the sweep

Do not start a 1,400-call run without knowing its wall clock.

- [ ] **Step 1: Measure calls per minute against the current key set**

`model_calls.jsonl` now carries a `ts` on every line, so this is arithmetic rather than guesswork:

```bash
find results -name model_calls.jsonl -exec cat {} + \
  | python3 -c "
import sys, json
ts = sorted(json.loads(l)['ts'] for l in sys.stdin if l.strip())
span = (ts[-1] - ts[0]) / 60 or 1
print(f'{len(ts)} calls over {span:.1f} min = {len(ts)/span:.1f} calls/min')"
```

- [ ] **Step 2: Project the sweep and decide the corpus size**

144 items times 4 arms times the measured calls per item. If the projection exceeds about two
hours, drop to `--per-family 4` for the iteration loop and run the full corpus once at the end,
stating the sampling in `results/README-results.md`. Adding `--per-family` to `corpus build` is a
one-line typer option.

# Task 17: The sweep

As per Task 14, unchanged, once quota allows.

## Revised day mapping

| Day | Date | Work |
|---|---|---|
| 1 | Wed 27 Aug | Tasks 11, 12, 13 done. Two Gemini bugs found and fixed. One item run end to end. |
| 2 | Thu 28 Aug | Task 15: public repo, architecture pass, pitch script. No quota needed. |
| 3 | Fri 29 Aug | Task 16 throughput probe, then Task 17 sweep if quota allows |
| 4 | Sat 30 Aug | Read the failures. Fix whatever the gateway actually fails. |
| 5 | Sun 31 Aug | Re-run, per-family breakdown |
| 6 | Mon 01 Sep | Held-out run once, README filled from generated files |
| 7 | Tue 02 Sep | Demo video against a real run |
| 8 | Wed 03 to Fri 04 Sep | Buffer |

Task 15 is deliberately first among the remaining work. It is the only block that has no
dependency on quota, and it makes the repo submittable even in the worst case where the sweep
never runs at all.
