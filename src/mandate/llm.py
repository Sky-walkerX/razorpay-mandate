"""One interface over multiple LLM providers (DashScope/Qwen, Gemini, Anthropic, Ollama),
so nothing above it knows who answered.

Calls are stateless on purpose. The corpus carries prompt-injection payloads that
should not be retained server-side, and a run has to be re-scorable from a local
log alone. Both rule out previous_interaction_id.
"""
import json
import os
import re
import sys
import threading
import time
from typing import Protocol

import httpx

DASHSCOPE_MODEL = "qwen3.8-flash"
DASHSCOPE_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
GEMINI_MODEL = "gemini-3.6-flash"
ANTHROPIC_MODEL = "claude-opus-5"
OLLAMA_MODEL = "qwen3.5:4b"
OLLAMA_HOST = "http://localhost:11434"
OLLAMA_NUM_CTX = 16384

# Free-tier Gemini allows 20 generate_content requests per DAY per key, measured
# 2026-08-28: one key 429s on its third call inside a minute, and the delay the
# body names (8-37s) does not clear it. So the sleep here is not what gets a free
# run finished, quota spread across keys is. It earns its place two other ways:
# it absorbs a genuine per-minute burst, and it is what a paid key needs, where
# the caps really are per minute. Rounds stay low because sleeping through a
# daily cap only delays an inevitable failure.
GEMINI_QUOTA_ROUNDS = 3
GEMINI_MAX_RETRY_SLEEP = 60.0
GEMINI_RETRY_FALLBACK = 30.0

# Gemini words the delay two ways depending on which layer rejects the call.
_RETRY_AFTER_RE = re.compile(
    r"""(?:retry\s+in|retryDelay['"]?\s*[:=]\s*['"]?)\s*([0-9]+(?:\.[0-9]+)?)\s*s""",
    re.IGNORECASE)


def _retry_after(msg: str) -> float | None:
    """Seconds the API asked us to wait, or None if it did not say."""
    m = _RETRY_AFTER_RE.search(msg)
    return float(m.group(1)) if m else None


def _is_quota_error(msg: str) -> bool:
    return ("429" in msg or "RESOURCE_EXHAUSTED" in msg
            or "quota" in msg.lower() or "too_many_requests" in msg)

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


def _vertex_target() -> tuple[str, str] | None:
    """Project and location for Vertex, or None to use the API-key pool.

    Vertex authenticates with application-default credentials and bills the
    project, so it is not subject to the 20-requests-per-day free-tier cap that
    makes a sweep on the key pool impossible for anything but the lite models.
    Newer models are published only to `global`; regional endpoints 404.
    """
    project = os.environ.get("GEMINI_VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        return None
    location = (os.environ.get("GEMINI_VERTEX_LOCATION")
                or os.environ.get("GOOGLE_CLOUD_LOCATION")
                or "global")
    return project, location


# The SDK sets no request timeout by default. Measured 2026-08-29: a 5-worker sweep
# stalled with all five sockets ESTABLISHED to Google and no bytes for 17 minutes, so
# the retry helper never got an exception to retry. A hung call has to become a failed
# call before anything upstream can recover from it.
VERTEX_TIMEOUT_MS = 120_000


def _default_vertex_client(project: str, location: str):
    from google import genai
    from google.genai import types
    return genai.Client(vertexai=True, project=project, location=location,
                        http_options=types.HttpOptions(timeout=VERTEX_TIMEOUT_MS))


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
        num_ctx: int = OLLAMA_NUM_CTX,
        think: bool = False,
    ) -> None:
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or OLLAMA_HOST).rstrip("/")
        self.seed = seed
        # Ollama defaults num_ctx to 4096. The catalog alone is ~2.9k tokens, so the
        # default truncates the window and the model never reaches the tool call.
        self.num_ctx = int(os.environ.get("OLLAMA_NUM_CTX") or num_ctx)
        # qwen3 spends its whole budget reasoning otherwise: 35.0s with thinking on
        # versus 6.6s with it off, same tool call either way.
        self.think = think
        self.client = client or httpx.Client(timeout=600.0)

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
        opts = {"temperature": 0.0, "num_ctx": self.num_ctx}
        if self.seed is not None:
            opts["seed"] = self.seed
        return opts

    def next_tool_call(self, system, history, tools):
        payload = {
            "model": self.model,
            "messages": self._messages(system, history),
            "tools": self._tools(tools),
            "stream": False,
            "think": self.think,
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
            "think": self.think,
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
                 api_keys: list[str] | None = None, client_factory=None,
                 sleep=None, quota_rounds: int = GEMINI_QUOTA_ROUNDS) -> None:
        self.model, self.seed = model, seed
        self.quota_rounds = quota_rounds
        self.quota_waits = 0
        self._sleep = sleep or time.sleep
        self._used: list[str] = []
        self._lock = threading.Lock()
        if client is not None:
            self._clients = [(None, client)]
        else:
            keys = api_keys or ([api_key] if api_key else _gemini_keys())
            factory = client_factory or _default_gemini_client
            self._clients = [(k, factory(k)) for k in keys]
        self._i = 0

    def _next_client(self):
        """Round-robin across keys. Free-tier quota is per key, so spreading
        several hundred requests across five of them is the cheap half of
        surviving a sweep. `_create` waits out the window when all five are
        empty at once, which round-robin alone cannot do."""
        with self._lock:
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
        last_exc = None
        rounds = max(1, self.quota_rounds)
        for round_i in range(rounds):
            # Rotating is free, so spend every key before spending any wall clock.
            for _ in range(max(1, len(self._clients))):
                try:
                    return self._next_client().interactions.create(**body)
                except Exception as e:
                    if not _is_quota_error(str(e)):
                        raise
                    last_exc = e
            if round_i < rounds - 1:
                delay = min(_retry_after(str(last_exc)) or GEMINI_RETRY_FALLBACK,
                            GEMINI_MAX_RETRY_SLEEP)
                # A sweep that quietly sleeps looks identical to a sweep that hung.
                self.quota_waits += 1
                print(f"[gemini] all {len(self._clients)} keys out of quota, "
                      f"waiting {delay:.0f}s (round {round_i + 1}/{rounds})",
                      file=sys.stderr, flush=True)
                self._sleep(delay)
        if last_exc:
            raise last_exc

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


class VertexGeminiProvider:
    """Gemini through Vertex, which serves generate_content but not Interactions.

    Vertex authenticates with application-default credentials and bills the
    project, so it escapes the 20-requests-per-day free-tier cap that makes a
    sweep impossible on the API-key pool for anything but the lite models.
    Measured 2026-08-29: `interactions.create` returns 400 "Unsupported model
    interaction" for every model tried, 3.1-lite through 3.7, while
    `generate_content` serves all of them. So this speaks the older shape and
    translates the same neutral history `GeminiProvider` takes.

    Newer models are published only to the `global` endpoint. asia-south1,
    asia-southeast1 and us-central1 all 404 on gemini-3.7-flash.
    """

    def __init__(self, model: str = GEMINI_MODEL, client=None,
                 project: str | None = None, location: str | None = None,
                 seed: int | None = None) -> None:
        self.model, self.seed = model, seed
        if client is not None:
            self.client, self.vertex = client, "injected"
        else:
            target = _vertex_target()
            if project:
                target = (project, location or "global")
            if target is None:
                raise RuntimeError(
                    "no Vertex project set; use GEMINI_VERTEX_PROJECT or GOOGLE_CLOUD_PROJECT")
            project, location = target
            self.client = _default_vertex_client(project, location)
            self.vertex = f"{project}/{location}"

    @staticmethod
    def _tools(tools: list[dict]):
        from google.genai import types
        return [types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name=t["name"],
                description=t.get("description", ""),
                parameters=t["input_schema"],
            ) for t in tools])]

    @staticmethod
    def _contents(history: list[dict]):
        """Neutral history to Vertex contents.

        A function_call and the function_response answering it must both appear,
        or the model re-issues the call it has already made. `assistant_raw`
        replays the model's own parts verbatim, which is what keeps a multi-turn
        agent loop from looping.
        """
        from google.genai import types
        out = []
        for m in history:
            role = m["role"]
            if role == "tool_result":
                out.append(types.Content(role="user", parts=[
                    types.Part.from_function_response(
                        name=m.get("name", ""), response={"result": m["text"]})]))
            elif role == "assistant_raw":
                out.append(types.Content(role="model", parts=[
                    types.Part.model_validate(p) for p in m["steps"]]))
            elif role == "assistant_call":
                out.append(types.Content(role="model", parts=[
                    types.Part.from_function_call(
                        name=m["name"], args=dict(m.get("args") or {}))]))
            else:
                kind = "user" if role == "user" else "model"
                out.append(types.Content(role=kind, parts=[types.Part(text=m["text"])]))
        return out

    def _call(self, system: str, history: list[dict], tools: list[dict] | None):
        from google.genai import types
        cfg: dict = {"temperature": 0.0, "system_instruction": system}
        if self.seed is not None:
            cfg["seed"] = self.seed
        if tools:
            cfg["tools"] = self._tools(tools)
            # The agent under test must be free to stop. Forcing a call would
            # manufacture the very behaviour the harness is trying to measure.
            cfg["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(
                disable=True)
        return self.client.models.generate_content(
            model=self.model,
            contents=self._contents(history),
            config=types.GenerateContentConfig(**cfg))

    def _parts(self, r):
        for cand in getattr(r, "candidates", None) or []:
            yield from getattr(getattr(cand, "content", None), "parts", None) or []

    def next_tool_call(self, system, history, tools):
        r = self._call(system, history, tools)
        parts = list(self._parts(r))
        raw = [p.model_dump(exclude_none=True) for p in parts]
        for i, part in enumerate(parts):
            fc = getattr(part, "function_call", None)
            if fc is not None:
                # Vertex leaves function_call.id unset, but the ledger needs a
                # stable handle to tie the result back to the call.
                call_id = getattr(fc, "id", None) or f"call_{i}"
                return fc.name, dict(fc.args or {}), call_id, raw
        return None

    def next_text(self, system, history):
        r = self._call(system, history, None)
        text = getattr(r, "text", None)
        if text is not None:
            return text
        return "".join(p.text for p in self._parts(r) if getattr(p, "text", None))


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
    if name in ("vertex", "gemini-vertex"):
        return VertexGeminiProvider(**kw)
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
