from pathlib import Path

import pytest

from mandate.policy.canonical import canonical_yaml, policy_hash
from mandate.policy.loader import PolicyHashMismatch, dump, load
from tests.policy.test_models import _policy


def test_hash_is_stable_across_calls():
    p = _policy()
    assert policy_hash(p) == policy_hash(p)

def test_hash_ignores_key_order_in_constraints():
    from mandate.policy.models import ConstraintId as C
    a = _policy(constraints={C.BUDGET_TOTAL: {"max": 1, "note": "x"}})
    b = _policy(constraints={C.BUDGET_TOTAL: {"note": "x", "max": 1}})
    assert policy_hash(a) == policy_hash(b)

def test_hash_changes_when_a_limit_changes():
    from mandate.policy.models import ConstraintId as C
    a = _policy()
    b = _policy(constraints={C.BUDGET_TOTAL: {"max": 200001}})
    assert policy_hash(a) != policy_hash(b)

def test_canonical_yaml_has_sorted_keys():
    y = canonical_yaml(_policy())
    assert y.index("agent:") < y.index("compiler:") < y.index("constraints:")

def test_round_trip_through_disk(tmp_path: Path):
    p = _policy()
    f = tmp_path / "p.yaml"
    dump(p, f)
    assert policy_hash(load(f)) == policy_hash(p)

def test_tampered_file_is_rejected(tmp_path: Path):
    f = tmp_path / "p.yaml"
    dump(_policy(), f)
    f.write_text(f.read_text().replace("200000", "999999"))
    with pytest.raises(PolicyHashMismatch):
        load(f)
