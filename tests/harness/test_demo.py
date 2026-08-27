from mandate.harness.corpus import build_corpus
from mandate.harness.demo import run_demo
from mandate.money import rupees
from tests.gateway.test_core import _pol
from tests.harness.test_agent import ScriptedModel, _buy


def _greedy(catalog, intent, compromised=False, call_log=None):
    return ScriptedModel([_buy("sku_0000", 1, 50000)])


def test_demo_runs_both_arms_on_the_same_item(tmp_path):
    item = next(i for i in build_corpus(seed=5) if i.family_id == "injection.description")
    out = run_demo(item, _pol(), _greedy, tmp_path)
    assert set(out) == {"enforce_compromised", "compromised"}


def test_observe_arm_spends_and_enforce_arm_does_not(tmp_path):
    item = next(i for i in build_corpus(seed=5) if i.family_id == "injection.description")
    out = run_demo(item, _pol(), _greedy, tmp_path)
    assert out["compromised"].spent == rupees(50000) and out["enforce_compromised"].spent == 0


def test_enforce_arm_names_the_blocking_clause(tmp_path):
    item = next(i for i in build_corpus(seed=5) if i.family_id == "injection.description")
    assert (
        run_demo(item, _pol(), _greedy, tmp_path)["enforce_compromised"].blocking_clause
        == "budget.per_transaction"
    )


def test_demo_is_reproducible(tmp_path):
    item = next(i for i in build_corpus(seed=5) if i.family_id == "injection.description")
    a = run_demo(item, _pol(), _greedy, tmp_path / "a")
    b = run_demo(item, _pol(), _greedy, tmp_path / "b")
    assert a["enforce_compromised"].verdicts == b["enforce_compromised"].verdicts
