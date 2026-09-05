"""NL intent to Policy. Runs twice and compares. Off the money path, once per mandate."""
import json
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from mandate.compiler.prompts import COMPILE_PROMPT, COMPILER_VERSION
from mandate.llm import Provider, provider_for
from mandate.policy.canonical import policy_hash
from mandate.policy.models import CompilerInfo, ConstraintId, Policy, Provenance
from mandate.policy.regulatory import REGULATORY_FLOOR

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
    constraints = dict(raw["constraints"])
    provenance = Provenance(**raw["provenance"])
    _apply_regulatory_floor(constraints, provenance)

    return Policy(
        mandate_id=f"mnd_{uuid.uuid4().hex[:12]}",
        principal=principal,
        agent=agent,
        issued=issued,
        expires=expires,
        constraints=constraints,
        provenance=provenance,
        source_text=text,
        compiler=CompilerInfo(model=model, temperature=0.0, version=COMPILER_VERSION),
    )


def _apply_regulatory_floor(constraints: dict, provenance: Provenance) -> None:
    """Add what a regulator requires, whatever the person said or did not say.

    The compiler never emits these clauses, and that is correct: a statutory
    obligation is not something a user states, which is exactly why provenance has a
    third bucket that reads "(required by law)" rather than "(I inferred this, is it
    right?)". But nothing then put them back, so the floor lived in one hand-written
    `policies/policy.yaml` and in no mandate compiled since. Measured on a live
    sandbox session: a visitor mandate authorising Rs 50,000 an order executed
    Rs 18,600 to the rail with `afa.required` reading "constraint not in policy".

    A stricter threshold the user did state survives, because asking to be consulted
    sooner is theirs to choose. A looser one does not, because the floor is not
    theirs to decline. Same direction the word "floor" implies.
    """
    for cid, spec in REGULATORY_FLOOR.items():
        existing = constraints.get(cid) or constraints.get(str(cid))
        if existing and "threshold" in spec and "threshold" in existing:
            merged = dict(existing)
            merged["threshold"] = min(int(existing["threshold"]), int(spec["threshold"]))
            constraints[cid] = merged
        elif not existing:
            constraints[cid] = dict(spec)
        # A clause the user stated that carries no threshold is left alone.

        stated = cid in provenance.stated or str(cid) in [str(c) for c in provenance.stated]
        if not stated and cid not in provenance.regulatory:
            provenance.regulatory.append(ConstraintId(cid))


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
