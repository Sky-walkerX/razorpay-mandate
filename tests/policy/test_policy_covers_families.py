from pathlib import Path

from mandate.harness.families import FAMILIES
from mandate.policy.loader import load as load_policy
from mandate.policy.models import ConstraintId

# Not a constraint: these name mechanisms, not clauses.
NOT_CLAUSES = {"prompt_trust", "idempotency"}


def test_every_family_target_is_a_constraint_the_policy_carries():
    pol = load_policy(Path("policies/policy.yaml"))
    carried = {str(k) for k in pol.constraints}
    missing = {}
    for fid, fam in FAMILIES.items():
        for t in fam.targets:
            if t in NOT_CLAUSES:
                continue
            if t not in carried:
                missing.setdefault(fid, []).append(t)
    assert not missing, f"families targeting absent constraints: {missing}"


def test_per_transaction_binds_more_tightly_than_total():
    """If they are equal the per-transaction clause can never fire on its own."""
    pol = load_policy(Path("policies/policy.yaml"))
    per_txn = pol.constraints[ConstraintId.BUDGET_PER_TRANSACTION]["max"]
    total = pol.constraints[ConstraintId.BUDGET_TOTAL]["max"]
    assert per_txn < total
