"""Calibration check for the cluster bootstrap.

Generate clustered binary data with a known true rate, build the interval, and count
how often it covers the truth. Correct 95% intervals cover about 95% of the time.
"""
import numpy as np

from mandate.harness.score import cluster_bootstrap


def simulate_clusters(
    true_rate: float,
    n_clusters: int,
    per_cluster: int,
    icc: float,
    seed: int,
) -> dict[str, list[int]]:
    """Beta-binomial: each cluster draws its own rate around true_rate.

    `icc` controls how much clusters differ. Zero means every cluster behaves the same
    and clustering buys nothing; higher means families diverge, which is the realistic case.
    """
    rng = np.random.default_rng(seed)
    if icc <= 0:
        conc = 1e6
    else:
        conc = max((1.0 - icc) / icc, 1e-6)
    a, b = true_rate * conc, (1 - true_rate) * conc
    out: dict[str, list[int]] = {}
    for c in range(n_clusters):
        p = float(rng.beta(a, b))
        out[f"fam{c}"] = [int(x) for x in rng.binomial(1, p, size=per_cluster)]
    return out


def coverage(
    true_rate: float,
    n_runs: int = 200,
    n_clusters: int = 10,
    per_cluster: int = 12,
    icc: float = 0.3,
    seed: int = 0,
    n_boot: int = 800,
) -> float:
    hits = 0
    for r in range(n_runs):
        d = simulate_clusters(true_rate, n_clusters, per_cluster, icc, seed=seed * 1000 + r)
        ci = cluster_bootstrap(d, n_boot=n_boot, seed=r)
        hits += int(ci.lo <= true_rate <= ci.hi)
    return hits / n_runs
