"""NL intent to Policy. Runs twice and compares. Off the money path, once per mandate."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from mandate.compiler.prompts import COMPILE_PROMPT, COMPILER_VERSION
from mandate.llm import Provider, provider_for
from mandate.policy.canonical import policy_hash
from mandate.policy.models import CompilerInfo, Policy, Provenance

IST = timezone(timedelta(hours=5, minutes=30))


class Question(BaseModel):
    phrase: str
    why: str


class CompileResult(BaseModel):
    policy: Policy | None = None
    questions: list[Question] = []
    readings: int = 1
    alternates: list[dict] = []


def _complete_json(provider: Provider, system: str, text: str) -> dict:
    raw = provider.next_text(system, [{"role": "user", "text": text}]).strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1].removeprefix("json").strip()
    return json.loads(raw)


def _to_policy(
    raw: dict,
    text: str,
    principal: str,
    agent: str,
    issued: datetime,
    expires: datetime,
    model: str,
) -> Policy:
    return Policy(
        mandate_id=f"mnd_{uuid.uuid4().hex[:12]}",
        principal=principal,
        agent=agent,
        issued=issued,
        expires=expires,
        constraints=raw["constraints"],
        provenance=Provenance(**raw["provenance"]),
        source_text=text,
        compiler=CompilerInfo(model=model, temperature=0.0, version=COMPILER_VERSION),
    )


def compile_intent(
    text: str,
    principal: str,
    agent: str,
    expires: datetime,
    provider: Provider | None = None,
    client=None,
    issued: datetime | None = None,
) -> CompileResult:
    issued = issued or datetime.now(IST)
    if client is not None:
        first = client.complete_json(COMPILE_PROMPT, text)
        second = client.complete_json(COMPILE_PROMPT, text)
        model_name = getattr(client, "model", "gemini-3.7-flash")
    else:
        prov = provider or provider_for()
        first = _complete_json(prov, COMPILE_PROMPT, text)
        second = _complete_json(prov, COMPILE_PROMPT, text)
        model_name = prov.model

    questions = [Question(**q) for q in first.get("questions", [])]
    if questions:
        return CompileResult(policy=None, questions=questions, readings=1)

    p1 = _to_policy(first, text, principal, agent, issued, expires, model_name)
    p2 = _to_policy(second, text, principal, agent, issued, expires, model_name)
    if policy_hash(p1.model_copy(update={"mandate_id": "fixed"})) != policy_hash(
        p2.model_copy(update={"mandate_id": "fixed"})
    ):
        return CompileResult(
            policy=None,
            readings=2,
            alternates=[first, second],
            questions=[
                Question(
                    phrase=text,
                    why="I read this two different ways; pick one below",
                )
            ],
        )
    return CompileResult(policy=p1, questions=[], readings=2)
