from mandate.harness.corpus import build_corpus
from mandate.harness.runner import ARMS, run_corpus, run_item
from mandate.money import rupees
from tests.gateway.test_core import _pol
from tests.harness.test_agent import ScriptedModel, _buy


def _overspend_factory(catalog, intent, compromised=False, call_log=None):
    return ScriptedModel([_buy("sku_0000", 100, 50000)])


def _behave_factory(catalog, intent, compromised=False, call_log=None):
    return ScriptedModel([_buy("sku_0000", 1, 300)])


def test_enforce_arm_contains_an_overspending_agent(tmp_path):
    item = next(i for i in build_corpus(seed=5) if i.is_attack)
    r = run_item(
        item,
        arm=ARMS["enforce"],
        policy=_pol(),
        model_factory=_overspend_factory,
        tmp_root=tmp_path,
    )
    assert r.contained and r.spent == 0


def test_observe_arm_does_not_contain_the_same_agent(tmp_path):
    item = next(i for i in build_corpus(seed=5) if i.is_attack)
    r = run_item(
        item,
        arm=ARMS["baseline"],
        policy=_pol(),
        model_factory=_overspend_factory,
        tmp_root=tmp_path,
    )
    assert not r.contained and r.spent > 0


def test_legitimate_item_is_not_blocked_in_enforce(tmp_path):
    item = next(i for i in build_corpus(seed=5) if not i.is_attack)
    r = run_item(
        item,
        arm=ARMS["enforce"],
        policy=_pol(),
        model_factory=_behave_factory,
        tmp_root=tmp_path,
    )
    assert r.spent == rupees(300) and not r.escalated


def test_repeat_is_honoured_for_retry_families(tmp_path):
    item = next(i for i in build_corpus(seed=5) if i.family_id == "retry.storm")
    r = run_item(
        item,
        arm=ARMS["enforce"],
        policy=_pol(),
        model_factory=_behave_factory,
        tmp_root=tmp_path,
    )
    assert len(r.verdicts) >= item.mutation.repeat


def test_run_corpus_excludes_held_out_by_default(tmp_path):
    items = build_corpus(seed=5)
    rs = run_corpus(
        items,
        arms=[ARMS["enforce"]],
        policy=_pol(),
        model_factory=_behave_factory,
        out_dir=tmp_path,
    )
    assert not any(r.held_out for r in rs)


def test_run_corpus_can_be_asked_for_held_out_only(tmp_path):
    items = build_corpus(seed=5)
    rs = run_corpus(
        items,
        arms=[ARMS["enforce"]],
        policy=_pol(),
        model_factory=_behave_factory,
        out_dir=tmp_path,
        exclude_held_out=False,
        held_out_only=True,
    )
    assert rs and all(r.held_out for r in rs)


def test_an_agent_error_is_recorded_not_swallowed(tmp_path):
    def boom(catalog, intent, compromised=False, call_log=None):
        class M:
            def next_call(self, t):
                raise RuntimeError("model exploded")

        return M()

    item = next(i for i in build_corpus(seed=5) if i.is_attack)
    r = run_item(
        item, arm=ARMS["enforce"], policy=_pol(), model_factory=boom, tmp_root=tmp_path
    )
    assert r.error and "model exploded" in r.error
