"""Guards on the compliance table, which is the easiest thing in the repo to lie in.

Nobody checks a compliance claim against running code, which is exactly why one
gets written optimistically. These tests make the optimistic version fail: a status
has to be one of four words, a gap cannot quietly become "out of scope", and an
out_of_scope row has to name whose obligation it is instead of ours.
"""
from pathlib import Path

import pytest

from mandate.policy import regulatory
from mandate.policy.loader import load as load_policy
from mandate.policy.models import ConstraintId as C

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def pol():
    return load_policy(ROOT / "policies" / "policy.yaml")


def test_every_status_is_one_of_the_four_words():
    """Statuses are a closed vocabulary. A fifth one would be a hedge."""
    for r in regulatory.RBI_REQUIREMENTS:
        assert r.status in regulatory.STATUSES, f"{r.key} has status {r.status!r}"


def test_every_requirement_cites_a_source_that_exists():
    for r in regulatory.RBI_REQUIREMENTS:
        assert r.source in regulatory.CITATIONS, f"{r.key} cites unknown {r.source!r}"


def test_out_of_scope_rows_say_whose_obligation_it_is():
    """The failure mode this file exists for: filing our own gap as somebody else's.

    An out_of_scope row is a claim that the obligation was never ours, so it has to
    name the party it does land on. A gap, by contrast, is ours and unmet.
    """
    parties = ("issuer", "bank", "cardholder", "customer")
    for r in regulatory.RBI_REQUIREMENTS:
        if r.status == "out_of_scope":
            assert any(p in r.mechanism.lower() for p in parties), (
                f"{r.key} is out_of_scope but names no other party"
            )


def test_the_admitted_gap_is_still_admitted():
    """Pre-debit notification is not implemented. If someone implements it, this
    test should be changed deliberately and with the mechanism named, not because
    the table started reading better."""
    gaps = {r.key for r in regulatory.RBI_REQUIREMENTS if r.status == "gap"}
    assert gaps == {"pre_debit_notification"}


def test_the_afa_requirement_points_at_a_constraint_the_policy_carries(pol):
    """The one row claiming "held" through a clause has to name a clause that is
    signed into the policy and evaluated, not one that merely exists in the enum."""
    afa = next(r for r in regulatory.RBI_REQUIREMENTS if r.key == "afa_above_threshold")
    assert afa.clause == str(C.AFA_REQUIRED)
    assert afa.clause in pol.constraints


def test_the_afa_threshold_on_the_page_is_the_threshold_in_the_policy(pol):
    """RBI's figure is ₹15,000 and the prose says so, so the signed clause must
    agree. A page quoting a threshold the gateway does not enforce is the whole
    problem restated."""
    afa = next(r for r in regulatory.RBI_REQUIREMENTS if r.key == "afa_above_threshold")
    threshold = int(pol.constraints[str(C.AFA_REQUIRED)]["threshold"])
    assert threshold == 1_500_000, "policy threshold is not ₹15,000"
    assert "15,000" in afa.requirement


def test_no_clause_is_mapped_onto_the_unpublished_protocol():
    """UAP is announced and unpublished. A clause-by-clause mapping onto a spec
    nobody has read would be invention, and inventing a compliance mapping is worse
    than admitting there is nothing yet to map to."""
    assert "not published" in regulatory.UAP_POSTURE
    assert regulatory.CITATIONS["npci_uap"]["issued"] == "announced, not published"


def test_the_posture_counts_are_derived_not_typed(pol):
    p = regulatory.posture(pol)
    assert p.held == sum(1 for r in p.requirements if r.status == "held")
    assert p.partial == sum(1 for r in p.requirements if r.status == "partial")
    assert p.gaps == sum(1 for r in p.requirements if r.status == "gap")
    assert p.out_of_scope == sum(1 for r in p.requirements if r.status == "out_of_scope")
    assert p.held + p.partial + p.gaps + p.out_of_scope == len(p.requirements)
