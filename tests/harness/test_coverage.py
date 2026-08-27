from mandate.harness.coverage import coverage, simulate_clusters


def test_simulation_is_seed_reproducible():
    a = simulate_clusters(0.8, n_clusters=5, per_cluster=10, icc=0.3, seed=4)
    b = simulate_clusters(0.8, n_clusters=5, per_cluster=10, icc=0.3, seed=4)
    assert a == b


def test_simulated_rate_is_near_the_true_rate_in_expectation():
    d = simulate_clusters(0.8, n_clusters=200, per_cluster=20, icc=0.2, seed=1)
    obs = sum(sum(v) for v in d.values()) / sum(len(v) for v in d.values())
    assert 0.74 < obs < 0.86


def test_clustered_interval_covers_the_truth_about_95_percent_of_the_time():
    """If this is much below 0.95 the intervals are too narrow and every reported
    result overstates confidence."""
    c = coverage(true_rate=0.8, n_runs=200, n_clusters=10, per_cluster=12,
                 icc=0.3, seed=11, n_boot=800)
    assert 0.88 <= c <= 1.0
