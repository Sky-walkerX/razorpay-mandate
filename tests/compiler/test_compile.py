import json
from datetime import datetime, timedelta, timezone

import pytest

from mandate.compiler.compile import compile_intent
from mandate.policy.models import ConstraintId as C

IST = timezone(timedelta(hours=5, minutes=30))
# compile_intent stamps `issued` from the real clock, so a fixed expiry date
# turns the suite red the moment that date passes. Keep it relative.
EXP = datetime.now(IST) + timedelta(days=30)


class FakeClient:
    """Stands in for the Anthropic client. Returns canned JSON, records calls."""
    def __init__(self, payloads): self.payloads, self.calls = list(payloads), 0
    def complete_json(self, prompt: str, text: str) -> dict:
        p = self.payloads[min(self.calls, len(self.payloads) - 1)]
        self.calls += 1
        return json.loads(p) if isinstance(p, str) else p


CLEAN = {"constraints": {"budget.total": {"max": 200000},
                         "category.deny": ["alcohol"],
                         "velocity": {"max_actions": 1, "window": "mandate"}},
         "provenance": {"stated": ["budget.total", "category.deny", "velocity"],
                        "inferred": []},
         "questions": []}


def _compile(payloads, text="under 2000, nothing alcoholic, one order"):
    return compile_intent(text, principal="user_1", agent="agt_1", expires=EXP,
                          client=FakeClient(payloads))

def test_clean_intent_compiles_to_a_policy():
    r = _compile([CLEAN, CLEAN])
    assert r.policy is not None
    assert r.policy.constraints[C.BUDGET_TOTAL]["max"] == 200000

def test_compiler_runs_twice_and_compares():
    c = FakeClient([CLEAN, CLEAN])
    compile_intent("x", principal="u", agent="a", expires=EXP, client=c)
    assert c.calls == 2

def test_divergent_readings_are_surfaced_not_silently_resolved():
    other = {**CLEAN, "constraints": {**CLEAN["constraints"],
                                      "budget.total": {"max": 500000}}}
    r = _compile([CLEAN, other])
    assert r.policy is None and r.readings == 2
    assert any("two different ways" in q.why for q in r.questions)

def test_questions_block_signing():
    payload = {**CLEAN, "questions": [{"phrase": "don't overdo it",
                                       "why": "no measurable constraint"}]}
    r = _compile([payload, payload])
    assert r.policy is None and r.questions[0].phrase == "don't overdo it"

def test_inferred_constraints_are_marked_inferred():
    payload = {"constraints": {**CLEAN["constraints"], "budget.per_item": {"max": 40000}},
               "provenance": {"stated": ["budget.total", "category.deny", "velocity"],
                              "inferred": ["budget.per_item"]},
               "questions": []}
    r = _compile([payload, payload])
    assert C.BUDGET_PER_ITEM in r.policy.provenance.inferred

def test_unknown_constraint_id_from_the_model_is_rejected():
    payload = {"constraints": {"budget.vibes": {"max": 1}},
               "provenance": {"stated": ["budget.vibes"], "inferred": []},
               "questions": []}
    with pytest.raises(ValueError):
        _compile([payload, payload])

def test_compiler_info_is_recorded_on_the_policy():
    r = _compile([CLEAN, CLEAN])
    assert r.policy.compiler.temperature == 0.0 and r.policy.compiler.version


class _FakeTextProvider:
    def __init__(self, responses, model="gemini-3.7-flash"):
        self.responses = list(responses)
        self.model = model
        self.seen = []

    def next_text(self, system, history):
        self.seen.append({"system": system, "history": history})
        return self.responses.pop(0)


def test_compiler_works_with_provider():
    p = _FakeTextProvider([json.dumps(CLEAN), json.dumps(CLEAN)], model="gemini-3.7-flash")
    r = compile_intent("buy food", principal="user_1", agent="agt_1", expires=EXP, provider=p)
    assert r.policy is not None
    assert r.policy.compiler.model == "gemini-3.7-flash"
