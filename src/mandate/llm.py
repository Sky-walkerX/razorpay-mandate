"""One interface over multiple LLM providers (DashScope/Qwen, Gemini, Anthropic, Ollama),
so nothing above it knows who answered.

Calls are stateless on purpose. The corpus carries prompt-injection payloads that
should not be retained server-side, and a run has to be re-scorable from a local
log alone. Both rule out previous_interaction_id.
"""
import json
import os
from typing import Protocol

import httpx

DASHSCOPE_MODEL = "qwen3.7-flash"
DASHSCOPE_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
GEMINI_MODEL = "gemini-3.7-flash"
ANTHROPIC_MODEL = "claude-opus-5"
OLLAMA_MODEL = "qwen3.5:4b"
OLLAMA_HOST = "http://localhost:11434"

# (tool name, arguments, call id, raw provider steps).
#
# The call id builds the next turn's function_result. The raw steps exist because
# Gemini 3 emits a `thought` step carrying a signature that must be echoed back
# verbatim; reconstructing only the function_call gets the next turn rejected with
# 400 invalid_request. They are opaque here on purpose: this layer does not know
# or care what is inside them.
ToolCall = tuple[str, dict, str, list[dict]]


def _is_placeholder(key: str) -> bool:
    """Catches placeholder keys copied from examples."""
    body = key.removeprefix("sk-ant-").removeprefix("rzp_test_").removeprefix("sk-")
    return not body or set(body.lower()) <= set("x")


def _gemini_keys() -> list[str]:
    """GEMINI_API_KEY plus any GEMINI_API_KEY_2, _3, ... that are set."""
    keys = [k for k in [os.environ.get("GEMINI_API_KEY")] if k]
    i = 2
    while (k := os.environ.get(f"GEMINI_API_KEY_{i}")):
        keys.append(k)
        i += 1
    if not keys:
        raise RuntimeError("no GEMINI_API_KEY set")
    return keys


def _default_gemini_client(api_key: str):
    from google import genai
    return genai.Client(api_key=api_key)


class Provider(Protocol):
    model: str

    def next_tool_call(
        self, system: str, history: list[dict], tools: list[dict]
    ) -> ToolCall | None: ...

    def next_text(self, system: str, history: list[dict]) -> str: ...


class DashScopeProvider:
    """Qwen via DashScope OpenAI-compatible API (e.g. qwen3.5-flash)."""

    def __init__(
        self,
        model: str = DASHSCOPE_MODEL,
        api_key: str | None = None,
        base_url: str | None = None,
        seed: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
        if not self.api_key:
            raise RuntimeError("no DASHSCOPE_API_KEY set")
        self.base_url = (base_url or os.environ.get("DASHSCOPE_BASE_URL") or DASHSCOPE_BASE_URL).rstrip("/")
        self.seed = seed
        self.client = client or httpx.Client(timeout=60.0)

    @staticmethod
    def _tools(tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    @staticmethod
    def _messages(system: str, history: list[dict]) -> list[dict]:
        msgs = [{"role": "system", "content": system}]
        for m in history:
            role = m["role"]
            if role == "tool_result":
                msgs.append(
                    {
                        "role": "tool",
                        "content": m["text"],
                        "tool_call_id": m.get("call_id", ""),
                    }
                )
            elif role == "assistant_call":
                msgs.append(
                    {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": m.get("call_id", "call_0"),
                                "type": "function",
                                "function": {
                                    "name": m["name"],
                                    "arguments": json.dumps(m.get("args") or {}),
                                },
                            }
                        ],
                    }
                )
            elif role == "assistant_raw":
                calls = []
                for s in m.get("steps", []):
                    if s.get("type") == "function_call":
                        args = s.get("arguments", {})
                        args_str = json.dumps(args) if isinstance(args, dict) else str(args)
                        calls.append(
                            {
                                "id": s.get("id", "call_0"),
                                "type": "function",
                                "function": {
                                    "name": s.get("name", ""),
                                    "arguments": args_str,
                                },
                            }
                        )
                if calls:
                    msgs.append({"role": "assistant", "content": None, "tool_calls": calls})
                else:
                    msgs.append({"role": "assistant", "content": m.get("text", "")})
            else:
                msgs.append(
                    {
                        "role": "assistant" if role == "assistant" else "user",
                        "content": m["text"],
                    }
                )
        return msgs

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def next_tool_call(self, system, history, tools):
        payload = {
            "model": self.model,
            "messages": self._messages(system, history),
            "tools": self._tools(tools),
            "temperature": 0.0,
        }
        if self.seed is not None:
            payload["seed"] = self.seed
        url = f"{self.base_url}/chat/completions"
        res = self.client.post(url, headers=self._headers(), json=payload)
        res.raise_for_status()
        data = res.json()
        choices = data.get("choices", [{}])
        if not choices:
            return None
        msg = choices[0].get("message", {})
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            tc = tool_calls[0]
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args_str = fn.get("arguments", "{}")
            args = json.loads(args_str) if isinstance(args_str, str) else args_str
            call_id = tc.get("id") or f"call_{abs(hash(name)) % 1000000}"
            raw = [
                {
                    "type": "function_call",
                    "name": name,
                    "arguments": args,
                    "id": call_id,
                }
            ]
            return name, dict(args or {}), call_id, raw
        return None

    def next_text(self, system, history):
        payload = {
            "model": self.model,
            "messages": self._messages(system, history),
            "temperature": 0.0,
        }
        if self.seed is not None:
            payload["seed"] = self.seed
        url = f"{self.base_url}/chat/completions"
        res = self.client.post(url, headers=self._headers(), json=payload)
        res.raise_for_status()
        data = res.json()
        choices = data.get("choices", [{}])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "").strip()


class OllamaProvider:
    """Local LLM runner via Ollama API (e.g. qwen3.5:4b)."""

    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        host: str | None = None,
        seed: int | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or OLLAMA_HOST).rstrip("/")
        self.seed = seed
        self.client = client or httpx.Client(timeout=120.0)

    @staticmethod
    def _tools(tools: list[dict]) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]

    @staticmethod
    def _messages(system: str, history: list[dict]) -> list[dict]:
        msgs = [{"role": "system", "content": system}]
        for m in history:
            role = m["role"]
            if role == "tool_result":
                msgs.append(
                    {
                        "role": "tool",
                        "content": m["text"],
                        "name": m.get("name", ""),
                        "tool_call_id": m.get("call_id", ""),
                    }
                )
            elif role == "assistant_call":
                msgs.append(
                    {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": m.get("call_id", "call_0"),
                                "function": {
                                    "name": m["name"],
                                    "arguments": dict(m.get("args") or {}),
                                },
                            }
                        ],
                    }
                )
            elif role == "assistant_raw":
                calls = []
                for s in m.get("steps", []):
                    if s.get("type") == "function_call":
                        calls.append(
                            {
                                "id": s.get("id", "call_0"),
                                "function": {
                                    "name": s.get("name", ""),
                                    "arguments": s.get("arguments", {}),
                                },
                            }
                        )
                if calls:
                    msgs.append({"role": "assistant", "content": "", "tool_calls": calls})
                else:
                    msgs.append({"role": "assistant", "content": m.get("text", "")})
            else:
                msgs.append(
                    {
                        "role": "assistant" if role == "assistant" else "user",
                        "content": m["text"],
                    }
                )
        return msgs

    def _options(self) -> dict:
        opts = {"temperature": 0.0}
        if self.seed is not None:
            opts["seed"] = self.seed
        return opts

    def next_tool_call(self, system, history, tools):
        payload = {
            "model": self.model,
            "messages": self._messages(system, history),
            "tools": self._tools(tools),
            "stream": False,
            "options": self._options(),
        }
        res = self.client.post(f"{self.host}/api/chat", json=payload)
        res.raise_for_status()
        data = res.json()
        msg = data.get("message", {})
        tool_calls = msg.get("tool_calls", [])
        if tool_calls:
            tc = tool_calls[0]
            fn = tc.get("function", {})
            name = fn.get("name", "")
            args = fn.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args or "{}")
            call_id = tc.get("id") or f"call_{abs(hash(name)) % 1000000}"
            raw = [
                {
                    "type": "function_call",
                    "name": name,
                    "arguments": args,
                    "id": call_id,
                }
            ]
            return name, dict(args or {}), call_id, raw
        return None

    def next_text(self, system, history):
        payload = {
            "model": self.model,
            "messages": self._messages(system, history),
            "stream": False,
            "format": "json",
            "options": self._options(),
        }
        res = self.client.post(f"{self.host}/api/chat", json=payload)
        res.raise_for_status()
        data = res.json()
        return data.get("message", {}).get("content", "").strip()


class GeminiProvider:
    """Gemini 3 via the Interactions API, which is the recommended path for this family."""

    def __init__(self, model: str = GEMINI_MODEL, client=None,
                 api_key: str | None = None, seed: int | None = None,
                 api_keys: list[str] | None = None, client_factory=None) -> None:
        self.model, self.seed = model, seed
        self._used: list[str] = []
        if client is not None:
            self._clients = [(None, client)]
        else:
            keys = api_keys or ([api_key] if api_key else _gemini_keys())
            factory = client_factory or _default_gemini_client
            self._clients = [(k, factory(k)) for k in keys]
        self._i = 0

    def _next_client(self):
        """Round-robin across keys. Free-tier quota is per key, and the sweep
        needs several hundred requests, so spreading them is the difference
        between a run finishing and a run dying on 429."""
        key, client = self._clients[self._i % len(self._clients)]
        self._i += 1
        self._used.append(key)
        return client

    @staticmethod
    def _tools(tools: list[dict]) -> list[dict]:
        """Anthropic's input_schema and Gemini's parameters are the same JSON Schema."""
        return [{"type": "function", "name": t["name"],
                 "description": t.get("description", ""),
                 "parameters": t["input_schema"]} for t in tools]

    @staticmethod
    def _input(history: list[dict]) -> list[dict]:
        """Translate the neutral history into Interactions input steps.

        An assistant_call must round-trip as a real function_call step. Synthesising
        it as model_output text leaves the following function_result pointing at a
        call_id that is not in the input, which the API rejects with 400.
        """
        out = []
        for m in history:
            role = m["role"]
            if role == "tool_result":
                out.append({"type": "function_result", "name": m.get("name", ""),
                            "call_id": m.get("call_id", ""),
                            "result": [{"type": "text", "text": m["text"]}]})
            elif role == "assistant_raw":
                out.extend(m["steps"])
            elif role == "assistant_call":
                out.append({"type": "function_call", "id": m["call_id"],
                            "name": m["name"], "arguments": dict(m.get("args") or {})})
            else:
                kind = "user_input" if role == "user" else "model_output"
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
        return self._next_client().interactions.create(**body)

    def next_tool_call(self, system, history, tools):
        r = self._create(system, history, tools)
        raw = [s.model_dump() for s in r.steps]
        for step in r.steps:
            if getattr(step, "type", None) == "function_call":
                args = step.arguments
                if isinstance(args, str):
                    args = json.loads(args or "{}")
                return step.name, dict(args or {}), step.id, raw
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
        """Anthropic has no step echo, so an assistant_call renders as text."""
        out = []
        for m in history:
            if m["role"] == "assistant_raw":
                continue  # opaque steps from another vendor; nothing to translate
            if m["role"] == "assistant_call":
                out.append({"role": "assistant",
                            "content": f"calling {m['name']} {dict(m.get('args') or {})}"})
            else:
                out.append({"role": "assistant" if m["role"] == "assistant" else "user",
                            "content": m["text"]})
        return out

    def next_tool_call(self, system, history, tools):
        r = self.client.messages.create(
            model=self.model, max_tokens=2000, system=system,
            tools=tools, messages=self._messages(history))
        for block in r.content:
            if getattr(block, "type", None) == "tool_use":
                return block.name, dict(block.input), block.id, []
        return None

    def next_text(self, system, history):
        r = self.client.messages.create(
            model=self.model, max_tokens=2000, system=system,
            messages=self._messages(history))
        return "".join(b.text for b in r.content
                       if getattr(b, "type", None) == "text")


def provider_for(name: str | None = None, **kw) -> Provider:
    """Explicit name wins, then MANDATE_LLM_PROVIDER, then DASHSCOPE/GEMINI/ANTHROPIC keys, then Ollama."""
    name = name or os.environ.get("MANDATE_LLM_PROVIDER")
    if name in ("dashscope", "qwen"):
        return DashScopeProvider(**kw)
    if name in ("ollama", "local"):
        model = kw.pop("model", os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL))
        return OllamaProvider(model=model, **kw)
    if name == "gemini":
        return GeminiProvider(**kw)
    if name == "anthropic":
        return AnthropicProvider(**{k: v for k, v in kw.items() if k != "seed"})
    if name:
        raise RuntimeError(f"unknown LLM provider {name!r}; expected dashscope, gemini, anthropic, or ollama")

    for env, cls in (
        ("DASHSCOPE_API_KEY", DashScopeProvider),
        ("GEMINI_API_KEY", GeminiProvider),
        ("ANTHROPIC_API_KEY", AnthropicProvider),
    ):
        key = os.environ.get(env)
        if not key:
            continue
        if _is_placeholder(key):
            raise RuntimeError(
                f"{env} is a placeholder value. Set a real key or use local Ollama with MANDATE_LLM_PROVIDER=ollama."
            )
        return cls(**(kw if cls in (DashScopeProvider, GeminiProvider)
                      else {k: v for k, v in kw.items() if k != "seed"}))

    if os.environ.get("OLLAMA_MODEL") or os.environ.get("OLLAMA_HOST"):
        model = kw.pop("model", os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL))
        return OllamaProvider(model=model, **kw)

    # Default to local Ollama if no cloud keys are set
    model = kw.pop("model", os.environ.get("OLLAMA_MODEL", OLLAMA_MODEL))
    return OllamaProvider(model=model, **kw)
