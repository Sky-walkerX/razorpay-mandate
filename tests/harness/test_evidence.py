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
    conf = sb["conformance"]
    assert {k: v for k, v in conf.items() if k != "attacks"} == {
        "total": 17, "blocked": 17, "escaped": 0, "vacuous": 0, "race_trials": 200,
    }

    # The per-attack rows a screen names the attacks from. Checked against the
    # totals beside them rather than listed, so the two cannot drift: a suite
    # that grows an attack without the totals moving is the failure worth
    # catching, and it is the same shape as a witness that never fired.
    attacks = conf["attacks"]
    assert len(attacks) == conf["total"]
    assert sum(a["outcome"] == "BLOCKED" for a in attacks) == conf["blocked"]
    assert sum(a["outcome"] == "ESCAPED" for a in attacks) == conf["escaped"]
    assert sum(a["outcome"] == "VACUOUS" for a in attacks) == conf["vacuous"]
    # Every witness executed, which is what stops a BLOCKED row being vacuous.
    assert all(a["witness_executed"] for a in attacks)
    assert not any(a["hardened_executed"] for a in attacks)


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


def test_the_rails_table_is_computed_by_rails_not_typed_into_the_payload(ev):
    """`rails.diff` is the only authority on what survives a rail. The console
    renders this block, so if it could drift from the module the page would be
    asserting a compliance fact nothing computes."""
    from mandate.policy import rails
    from mandate.policy.canonical import policy_hash

    pol = load_policy(ROOT / "policies" / "policy.yaml")
    d = rails.diff(pol, policy_hash=policy_hash(pol))
    got = ev["alignment"]["rails"]

    assert got["total_clauses"] == d.total_clauses == len(pol.constraints)
    assert got["ap2_held"] == d.ap2_held
    assert got["ap2_lost"] == d.ap2_lost
    assert got["reserve_pay_held"] == d.reserve_pay_held
    assert got["reserve_pay_lost"] == d.reserve_pay_lost
    assert [f["clause"] for f in got["fates"]] == [f.clause for f in d.fates]
    for f, want in zip(got["fates"], d.fates, strict=True):
        assert (f["ap2"], f["reserve_pay"]) == (want.ap2, want.reserve_pay)


def test_every_clause_the_policy_carries_appears_in_the_rails_table(ev):
    """A clause missing from the table would read as one with nothing to lose."""
    pol = load_policy(ROOT / "policies" / "policy.yaml")
    assert {f["clause"] for f in ev["alignment"]["rails"]["fates"]} == set(pol.constraints)


def test_the_regulatory_posture_is_computed_by_its_module(ev):
    from mandate.policy import regulatory

    pol = load_policy(ROOT / "policies" / "policy.yaml")
    want = regulatory.posture(pol)
    got = ev["alignment"]["regulatory"]
    assert got["held"] == want.held
    assert got["gaps"] == want.gaps
    assert got["partial"] == want.partial
    assert got["out_of_scope"] == want.out_of_scope
    assert [r["key"] for r in got["requirements"]] == [r.key for r in want.requirements]


def test_the_reserve_pay_projection_drops_the_merchants_it_cannot_hold(ev):
    """A Reserve Pay block names one payee. The mandate allows three, so two have
    nowhere to go, and the payload reports them rather than collapsing the list
    quietly to its first element."""
    pol = load_policy(ROOT / "policies" / "policy.yaml")
    allowed = pol.constraints["merchant.allow"]
    rp = ev["alignment"]["reserve_pay"]
    assert rp["payee"] == allowed[0]
    assert rp["payee_overflow"] == allowed[1:]
    assert len(rp["payee_overflow"]) == len(allowed) - 1


def test_the_ap2_export_carries_the_users_own_words(ev):
    """`natural_language_description` is where every clause AP2 cannot hold ends up.
    That it is prose and not a control is the point the page makes, so it has to
    really be the source text."""
    pol = load_policy(ROOT / "policies" / "policy.yaml")
    assert ev["alignment"]["ap2_export"]["intent_mandate"][
        "natural_language_description"] == pol.source_text


def test_evidence_carries_the_log_public_key_so_the_page_can_pin_it(ev):
    """The verifier must not fetch the key from the server that signed the head.

    A page that asked the gateway for the key it verifies the gateway's signature
    against is checking a signature against a key its adversary chose. Pinning the
    key at build time is what makes the client-side proof mean anything, and it is
    why a production key that differs from the committed one fails loudly.
    """
    log = ev["log"]
    assert set(log) == {"public_key"}
    key = log["public_key"]
    # Absent is allowed and is reported as absent. Present must be a real
    # Ed25519 public key, not an empty string standing in for one.
    if key is not None:
        assert len(key) == 64 and int(key, 16) >= 0
