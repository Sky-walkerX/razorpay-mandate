"""The web console must read measured evidence, never a literal in a TS file.

Before this existed, `web/src/data/policy.ts` claimed a max quantity of 4 while
the signed policy said 5, a policy hash that matched no document, and a signing
date two weeks off. Nobody noticed because nothing compared the two.
"""
import json
from pathlib import Path

import pytest

from mandate.harness.evidence import build_evidence
from mandate.policy.loader import load as load_policy

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def ev():
    return build_evidence(root=ROOT)


def test_every_bound_matches_the_signed_policy(ev):
    """The bug this suite exists for. Bounds are read, never retyped."""
    pol = load_policy(ROOT / "policies" / "policy.yaml")
    by_key = {p["key"]: p for p in ev["policy"]["parts"]}
    assert by_key["quantity.max_per_item"]["max"] == pol.constraints["quantity.max_per_item"]["max"]
    assert by_key["budget.total"]["max"] == pol.constraints["budget.total"]["max"]
    assert by_key["budget.per_transaction"]["max"] == pol.constraints["budget.per_transaction"]["max"]
    assert by_key["budget.per_item"]["max"] == pol.constraints["budget.per_item"]["max"]
    assert by_key["merchant.allow"]["values"] == pol.constraints["merchant.allow"]
    assert by_key["category.deny"]["values"] == pol.constraints["category.deny"]


def test_policy_identity_is_the_real_signed_document(ev):
    pol = load_policy(ROOT / "policies" / "policy.yaml")
    assert ev["policy"]["mandate_id"] == pol.mandate_id
    assert ev["policy"]["policy_hash"].startswith("sha256:")
    assert ev["policy"]["source_text"] == pol.source_text
    assert ev["policy"]["issued"].startswith(pol.issued.date().isoformat())
    assert ev["policy"]["expires"].startswith(pol.expires.date().isoformat())


def test_provenance_says_which_clauses_the_user_actually_stated(ev):
    """The frontend called two clauses 'inferred' that the policy records as stated."""
    pol = load_policy(ROOT / "policies" / "policy.yaml")
    stated = {p["key"] for p in ev["policy"]["parts"] if p["source"] == "stated"}
    assert stated == {str(c) for c in pol.provenance.stated}


def test_scoreboard_carries_the_three_measured_sets(ev):
    sb = ev["scoreboard"]
    assert sb["containment"]["enforce"]["contained"] == 18
    assert sb["containment"]["enforce"]["total"] == 18
    assert sb["false_block"]["enforce"]["blocked"] == 0
    assert sb["false_block"]["enforce"]["total"] == 12
    assert sb["conformance"] == {
        "total": 9, "blocked": 9, "escaped": 0, "vacuous": 0, "race_trials": 200,
    }


def test_feed_replays_one_real_audit_log(ev):
    feed = ev["feed"]
    assert feed["run"]
    counts = feed["counts"]
    assert counts["allowed"] + counts["refused"] + counts["escalated"] == counts["evaluated"]
    assert counts["evaluated"] == len(feed["decisions"])
    assert counts["refused"] > 0 and counts["allowed"] > 0


def test_every_decision_carries_its_chain_hash(ev):
    for d in ev["feed"]["decisions"]:
        assert d["hash"].startswith("sha256:")
        assert d["verdict"] in {"allow", "deny", "unknown"}


def test_provenance_block_names_the_runs_it_came_from(ev):
    src = ev["source"]
    assert src["model"] == "gemini-3.7-flash"
    assert src["containment_run"] and src["false_block_run"]
    for v in src.values():
        assert "TODO" not in str(v) and "synthetic" not in str(v).lower()


def test_payload_is_json_serialisable(ev):
    json.dumps(ev)
