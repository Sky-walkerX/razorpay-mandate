import itertools

from mandate.gateway.lattice import combine, evaluate_all, first_blocking
from mandate.gateway.state import ClauseResult, Verdict
from mandate.money import rupees
from tests.gateway.test_constraints_budget import _ctx


def _r(v, cid="x"):
    return ClauseResult(id=cid, result=v)

def test_all_allow_gives_allow():
    assert combine([_r(Verdict.ALLOW), _r(Verdict.ALLOW)]) is Verdict.ALLOW

def test_any_deny_gives_deny():
    assert combine([_r(Verdict.ALLOW), _r(Verdict.DENY)]) is Verdict.DENY

def test_unknown_without_deny_gives_unknown():
    assert combine([_r(Verdict.ALLOW), _r(Verdict.UNKNOWN)]) is Verdict.UNKNOWN

def test_deny_dominates_unknown():
    assert combine([_r(Verdict.UNKNOWN), _r(Verdict.DENY)]) is Verdict.DENY

def test_combination_is_order_independent():
    for perm in itertools.permutations([Verdict.ALLOW, Verdict.UNKNOWN, Verdict.DENY]):
        assert combine([_r(v) for v in perm]) is Verdict.DENY

def test_empty_results_allow():
    assert combine([]) is Verdict.ALLOW

def test_first_blocking_prefers_deny_over_unknown():
    rs = [_r(Verdict.UNKNOWN, "u"), _r(Verdict.DENY, "d")]
    assert first_blocking(rs).id == "d"

def test_evaluate_all_returns_one_result_per_evaluator():
    from mandate.gateway.constraints import ALL_EVALUATORS
    assert len(evaluate_all(_ctx(rupees(10)))) == len(ALL_EVALUATORS)

def test_evaluate_all_is_pure_and_repeatable():
    ctx = _ctx(rupees(10))
    assert [r.model_dump() for r in evaluate_all(ctx)] == \
           [r.model_dump() for r in evaluate_all(ctx)]
