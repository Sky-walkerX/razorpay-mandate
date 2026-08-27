"""One interface over two vendors, so nothing above it knows who answered.

Calls are stateless on purpose. The corpus carries prompt-injection payloads that
should not be retained server-side, and a run has to be re-scorable from a local
log alone. Both rule out previous_interaction_id.
"""
import json
import os
from typing import Protocol

GEMINI_MODEL = "gemini-3.7-flash"
ANTHROPIC_MODEL = "claude-opus-5"

# (tool name, arguments, call id). The call id is needed to build the next turn's
# function_result, so it travels with the call rather than being looked up later.
ToolCall = tuple[str, dict, str]


def _is_placeholder(key: str) -> bool:
    """Catches the .env.example value that produced 576 scripted result rows."""
    body = key.removeprefix("sk-ant-").removeprefix("rzp_test_")
    return not body or set(body.lower()) <= set("x")


class Provider(Protocol):
    model: str

    def next_tool_call(
        self, system: str, history: list[dict], tools: list[dict]
    ) -> ToolCall | None: ...

    def next_text(self, system: str, history: list[dict]) -> str: ...


class GeminiProvider:
    """Gemini 3 via the Interactions API, which is the recommended path for this family."""

    def __init__(self, model: str = GEMINI_MODEL, client=None,
                 api_key: str | None = None, seed: int | None = None) -> None:
        if client is None:
            from google import genai
            client = genai.Client(api_key=api_key or os.environ["GEMINI_API_KEY"])
        self.client, self.model, self.seed = client, model, seed

    @staticmethod
    def _tools(tools: list[dict]) -> list[dict]:
        """Anthropic's input_schema and Gemini's parameters are the same JSON Schema."""
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

    def _config(self) -> dict:
        cfg = {"temperature": 0.0}
        if self.seed is not None:
            cfg["seed"] = self.seed
        return cfg

    def _create(self, system: str, history: list[dict], tools: list[dict] | None):
        body = {"model": self.model, "system_instruction": system,
                "input": self._input(history), "generation_config": self._config(),
                "store": False}
        if tools:
            body["tools"] = self._tools(tools)
        return self.client.interactions.create(**body)

    def next_tool_call(self, system, history, tools):
        r = self._create(system, history, tools)
        for step in r.steps:
            if getattr(step, "type", None) == "function_call":
                args = step.arguments
                if isinstance(args, str):
                    args = json.loads(args or "{}")
                return step.name, dict(args or {}), step.id
        return None

    def next_text(self, system, history):
        r = self._create(system, history, None)
        text = getattr(r, "output_text", None)
        if text is not None:
            return text
        parts = []
        for step in r.steps:
            for block in getattr(step, "content", None) or []:
                if getattr(block, "type", None) == "text":
                    parts.append(block.text)
        return "".join(parts)


class AnthropicProvider:
    def __init__(self, model: str = ANTHROPIC_MODEL, client=None,
                 api_key: str | None = None) -> None:
        if client is None:
            import anthropic
            client = anthropic.Anthropic(
                api_key=api_key or os.environ["ANTHROPIC_API_KEY"])
        self.client, self.model = client, model

    @staticmethod
    def _messages(history: list[dict]) -> list[dict]:
        return [{"role": "assistant" if m["role"] == "assistant" else "user",
                 "content": m["text"]} for m in history]

    def next_tool_call(self, system, history, tools):
        r = self.client.messages.create(
            model=self.model, max_tokens=2000, system=system,
            tools=tools, messages=self._messages(history))
        for block in r.content:
            if getattr(block, "type", None) == "tool_use":
                return block.name, dict(block.input), block.id
        return None

    def next_text(self, system, history):
        r = self.client.messages.create(
            model=self.model, max_tokens=2000, system=system,
            messages=self._messages(history))
        return "".join(b.text for b in r.content
                       if getattr(b, "type", None) == "text")


def provider_for(name: str | None = None, **kw) -> Provider:
    """Explicit name wins, then MANDATE_LLM_PROVIDER, then whichever key is set."""
    name = name or os.environ.get("MANDATE_LLM_PROVIDER")
    if name == "gemini":
        return GeminiProvider(**kw)
    if name == "anthropic":
        return AnthropicProvider(**{k: v for k, v in kw.items() if k != "seed"})
    if name:
        raise RuntimeError(f"unknown LLM provider {name!r}; expected gemini or anthropic")
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
