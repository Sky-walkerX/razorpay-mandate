"""The third provenance bucket, and the drift that made it necessary.

`compiler.model` in the signed policy once read `qwen3.5:9b`. It got there in a
commit about demo formatting, with byte-identical constraints and no recompile
behind it, and nothing compared the label against what the compiler actually
produces. These tests compare.
"""
from pathlib import Path

import pytest

from mandate.compiler.readback import FLAG, LAW, render
from mandate.policy.loader import load as load_policy
from mandate.policy.models import CompilerInfo, Policy, Provenance
from mandate.policy.models import ConstraintId as C

POLICY = Path("policies/policy.yaml")


@pytest.fixture
def signed():
    return load_policy(POLICY)


def test_the_three_buckets_are_disjoint_and_cover_every_constraint(signed):
    stated, inferred = set(signed.provenance.stated), set(signed.provenance.inferred)
    regulatory = set(signed.provenance.regulatory)
    assert not (stated & inferred) and not (stated & regulatory)
    assert not (inferred & regulatory)
    assert set(signed.constraints) <= (stated | inferred | regulatory)


def test_clauses_no_compiler_run_produces_are_not_filed_as_stated(signed):
    """`time.window` is not emitted by any real compile, so it cannot be 'the user
    said it'. RBI requires every mandate to carry a validity period, which is why
    it is in the policy at all."""
    assert C.TIME_WINDOW in signed.provenance.regulatory
    assert C.TIME_WINDOW not in signed.provenance.stated


def test_the_afa_threshold_is_regulatory_not_inferred(signed):
    assert C.AFA_REQUIRED in signed.provenance.regulatory
    assert C.AFA_REQUIRED not in signed.provenance.inferred


def test_the_recorded_compiler_model_is_one_the_project_actually_runs(signed):
    """A label naming a model nobody ran is how this went wrong the first time."""
    from mandate.llm import GEMINI_MODEL

    assert signed.compiler.model == GEMINI_MODEL


def test_the_read_back_labels_a_regulatory_clause_instead_of_questioning_it():
    cons = {C.BUDGET_TOTAL: {"max": 200000}, C.AFA_REQUIRED: {"threshold": 1500000}}
    p = Policy(
        mandate_id="mnd_t", principal="user_local", agent="agt_shopper",
        issued=load_policy(POLICY).issued, expires=load_policy(POLICY).expires,
        source_text="spend at most Rs 2000", constraints=cons,
        provenance=Provenance(stated=[C.BUDGET_TOTAL], regulatory=[C.AFA_REQUIRED]),
        compiler=CompilerInfo(model="test", temperature=0.0, version="1.0.0"))
    out = render(p)
    afa_line = next(ln for ln in out.splitlines() if "approve anything over" in ln)
    assert LAW in afa_line
    assert FLAG not in afa_line


def test_a_regulatory_clause_is_never_offered_for_confirmation(signed):
    """Asking 'is this right?' about a statutory floor invites a no the gateway
    would have to refuse anyway."""
    for line in render(signed).splitlines():
        if LAW in line:
            assert FLAG not in line
