"""NL intent to Policy. Runs twice and compares. Off the money path, once per mandate."""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from mandate.compiler.prompts import COMPILE_PROMPT, COMPILER_VERSION
from mandate.policy.canonical import policy_hash
from mandate.policy.models import CompilerInfo, Policy, Provenance

MODEL = "claude-opus-5"
IST = timezone(timedelta(hours=5, minutes=30))


class Question(BaseModel):
    phrase: str
    why: str


class CompileResult(BaseModel):
    policy: Policy | None = None
    questions: list[Question] = []
    readings: int = 1
    alternates: list[dict] = []


class AnthropicJSONClient:
    def __init__(self, api_key: str | None = None) -> None:
        import anthropic
        self._c = anthropic.Anthropic(api_key=api_key or os.environ["ANTHROPIC_API_KEY"])

    def complete_json(self, prompt: str, text: str) -> dict:
        msg = self._c.messages.create(
            model=MODEL,
            max_tokens=2000,
            system=prompt,
            messages=[{"role": "user", "content": text}],
        )
        body = msg.content[0].text.strip()
        if body.startswith("```"):
            body = body.split("```")[1].removeprefix("json").strip()
        return json.loads(body)


def _to_policy(raw: dict, text: str, principal: str, agent: str,
               issued: datetime, expires: datetime) -> Policy:
    return Policy(
        mandate_id=f"mnd_{uuid.uuid4().hex[:12]}", principal=principal, agent=agent,
        issued=issued, expires=expires, constraints=raw["constraints"],
        provenance=Provenance(**raw["provenance"]), source_text=text,
        compiler=CompilerInfo(model=MODEL, temperature=0.0, version=COMPILER_VERSION))


def compile_intent(text: str, principal: str, agent: str, expires: datetime,
                   client=None, issued: datetime | None = None) -> CompileResult:
    client = client or AnthropicJSONClient()
    issued = issued or datetime.now(IST)

    first = client.complete_json(COMPILE_PROMPT, text)
    second = client.complete_json(COMPILE_PROMPT, text)

    questions = [Question(**q) for q in first.get("questions", [])]
    if questions:
        return CompileResult(policy=None, questions=questions, readings=1)

    p1 = _to_policy(first, text, principal, agent, issued, expires)
    p2 = _to_policy(second, text, principal, agent, issued, expires)
    if policy_hash(p1.model_copy(update={"mandate_id": "fixed"})) != \
       policy_hash(p2.model_copy(update={"mandate_id": "fixed"})):
        return CompileResult(
            policy=None, readings=2, alternates=[first, second],
            questions=[Question(phrase=text,
                                why="I read this two different ways; pick one below")])
    return CompileResult(policy=p1, questions=[], readings=2)
