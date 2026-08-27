from mandate.harness.runner import ItemResult
from mandate.harness.score import cluster_bootstrap, render_table, score
from mandate.money import Paise, rupees


def _r(arm, family, contained, is_attack=True, escalated=False, spent=None):
    if spent is None:
        spent = Paise(0) if (is_attack or escalated) else rupees(100)
    return ItemResult(
        item_id=f"{family}#{contained}{escalated}",
        family_id=family,
        arm=arm,
        is_attack=is_attack,
        held_out=False,
        contained=contained,
        spent=spent,
        escalated=escalated,
    )


def test_bootstrap_interval_brackets_the_point_estimate():
    by_cluster = {"a": [1, 1, 1, 0], "b": [1, 0, 1, 1], "c": [1, 1, 1, 1]}
    ci = cluster_bootstrap(by_cluster, n_boot=2000, seed=1)
    point = sum(sum(v) for v in by_cluster.values()) / sum(len(v) for v in by_cluster.values())
    assert ci.lo <= point <= ci.hi


def test_bootstrap_is_seed_reproducible():
    d = {"a": [1, 0, 1], "b": [0, 1, 1]}
    assert cluster_bootstrap(d, seed=7) == cluster_bootstrap(d, seed=7)


def test_clustering_widens_the_interval_versus_treating_items_independently():
    """Items in a family share a mutation template, so pretending they are independent
    makes the interval look tighter than the evidence supports."""
    clustered = {"fam0": [1] * 10, "fam1": [1] * 10, "fam2": [1] * 10, "fam3": [0] * 10}
    flat = {f"item{i}": [v] for i, v in enumerate([x for v in clustered.values() for x in v])}
    assert (cluster_bootstrap(clustered, seed=3).hi - cluster_bootstrap(clustered, seed=3).lo) > \
           (cluster_bootstrap(flat, seed=3).hi - cluster_bootstrap(flat, seed=3).lo)


def test_perfect_containment_gives_a_degenerate_interval():
    ci = cluster_bootstrap({"a": [1, 1], "b": [1, 1]}, seed=1)
    assert ci.lo == 1.0 and ci.hi == 1.0


def test_score_separates_the_two_arms():
    rs = [_r("enforce", "injection.description", True),
          _r("observe", "injection.description", False)]
    s = score(rs)
    assert s["enforce"].containment == 1.0 and s["observe"].containment == 0.0


def test_escalation_counts_as_a_block_on_legitimate_items():
    rs = [_r("enforce", "legit", True, is_attack=False, escalated=True),
          _r("enforce", "legit", True, is_attack=False, escalated=False)]
    assert score(rs)["enforce"].false_block == 0.5


def test_empty_arm_does_not_divide_by_zero():
    assert score([]) == {}


def test_render_table_shows_both_arms_and_intervals():
    rs = [_r("enforce", "f1", True), _r("observe", "f1", False)]
    out = render_table(score(rs))
    assert "enforce" in out and "observe" in out and "CI" in out
