from mandate.harness.corpus import build_corpus
from mandate.harness.runner import ARMS, run_corpus, run_item
from mandate.money import rupees
from tests.gateway.test_core import _pol
from tests.harness.test_agent import ScriptedModel, _buy


def _overspend_factory(catalog, intent, compromised=False, call_log=None):
    return ScriptedModel([_buy("sku_0000", 100)])


def _behave_factory(catalog, intent, compromised=False, call_log=None):
    return ScriptedModel([_buy("sku_0000", 1)])


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
    # The gateway prices sku_0000 from its own clean catalog, so the spend is
    # whatever that item really costs, not whatever the agent said it costs.
    assert 0 < r.spent <= rupees(2000) and not r.escalated


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


def test_run_item_stamps_provenance(tmp_path):
    item = next(i for i in build_corpus(seed=5) if i.is_attack)
    r = run_item(
        item,
        arm=ARMS["enforce"],
        policy=_pol(),
        model_factory=_behave_factory,
        tmp_root=tmp_path,
        run_id="run_abc",
        corpus_hash="sha256:deadbeef",
        policy_id="mandate_xyz",
    )
    assert r.run_id == "run_abc"
    assert r.corpus_hash == "sha256:deadbeef"
    assert r.policy_id == "mandate_xyz"


def test_every_row_in_a_run_carries_the_same_model(tmp_path):
    items = [i for i in build_corpus(seed=5, per_family=2, n_legit=2)][:8]
    results = run_corpus(
        items,
        [ARMS["enforce"]],
        _pol(),
        _behave_factory,
        tmp_path,
        model="qwen-flash",
        run_id="run_one",
    )
    assert len({r.model for r in results}) == 1
    assert {r.run_id for r in results} == {"run_one"}


def test_pooled_run_returns_the_same_results_as_a_serial_one(tmp_path):
    items = build_corpus(seed=5, per_family=2, n_legit=2)[:6]
    serial = run_corpus(
        items,
        [ARMS["enforce"]],
        _pol(),
        _behave_factory,
        tmp_path / "a",
        model="m",
        run_id="r",
        workers=1,
    )
    pooled = run_corpus(
        items,
        [ARMS["enforce"]],
        _pol(),
        _behave_factory,
        tmp_path / "b",
        model="m",
        run_id="r",
        workers=4,
    )
    key = lambda rs: sorted((r.item_id, r.arm, r.contained, int(r.spent)) for r in rs)
    assert key(serial) == key(pooled)





def test_a_run_records_which_sku_the_attack_targeted_and_which_it_bought(tmp_path):
    """Without both, auditing a scored set for vacuous containment means replaying
    the mutator from its seed. `price.flip` scored containments on runs whose
    mutation never reached the executed basket, and nothing in the row said so."""
    item = next(
        i for i in build_corpus(seed=5)
        if i.is_attack and i.family_id.startswith(("injection.", "price.flip"))
    )
    r = run_item(
        item,
        arm=ARMS["baseline"],
        policy=_pol(),
        model_factory=_behave_factory,
        tmp_root=tmp_path,
    )
    # The mutator names its victim in the note; the row must carry it.
    assert item.mutation.note in r.mutation_note
    # And what the gateway actually resolved and executed.
    assert r.executed_skus == ["sku_0000"]
