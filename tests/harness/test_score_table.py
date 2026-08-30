"""An absent measurement must not print as `nan%` or as a perfect score."""
from mandate.harness.score import ArmScore, Interval, render_table


def _arm(**kw):
    base = {"arm": "baseline", "n_attacks": 18, "containment": 0.556,
            "containment_ci": Interval(lo=0.0, hi=0.833), "n_legit": 0,
            "false_block": float("nan"),
            "false_block_ci": Interval(lo=float("nan"), hi=float("nan")),
            "per_family": {}}
    base.update(kw)
    return ArmScore(**base)


def test_a_rate_with_no_items_renders_as_not_applicable():
    out = render_table({"baseline": _arm()})
    assert "n/a (no items)" in out
    assert "nan" not in out.lower()


def test_it_never_prints_zero_for_an_unmeasured_rate():
    """0.0% would claim a perfect false-block score that was never measured."""
    out = render_table({"baseline": _arm()})
    row = next(ln for ln in out.splitlines() if ln.startswith("| baseline"))
    assert "0.0%" not in row.split("|")[-2]


def test_a_measured_rate_still_renders_normally():
    out = render_table({"enforce": _arm(arm="enforce", n_legit=12, false_block=0.0,
                                        false_block_ci=Interval(lo=0.0, hi=0.0))})
    assert "0.0% [0.0%, 0.0%]" in out
