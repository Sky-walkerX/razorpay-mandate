"""Which of the ten limits could read anything, for a given action.

A raw call carries an amount and nothing else. `budget.per_item` has no line
items to compare, `category.deny` has no categories, `quantity.max_per_item` has
no quantities, `merchant.allow` has no payee and `item.deny_recent` has no
history. Every one of those evaluators already returns ALLOW in that case, which
is correct for the lattice and misleading on a screen: ten clauses painted green
on five evaluations is the VACUOUS bug at a different layer, and this project has
already shipped that bug twice.

So the verdict is unchanged and the *reporting* gains a distinction. Nothing here
feeds `combine`, and `lattice.py` is untouched.

This is derived from the resolved action rather than stored. `AuditRecord`'s
`record_hash` covers every field, so a new field would change the hash of every
record already written and break every existing chain.
"""
from mandate.gateway.action import ResolvedAction
from mandate.policy.models import ConstraintId as C

# Clauses that need line items or a payee to mean anything. A basket has both, so
# on a basket this set is empty.
_NEEDS_LINE_ITEMS = frozenset({
    C.BUDGET_PER_ITEM,
    C.CATEGORY_DENY,
    C.QUANTITY_MAX_PER_ITEM,
    C.ITEM_DENY_RECENT,
})

# The payee. A raw call operates on the merchant's own Razorpay account, so there
# is no counterparty for `merchant.allow` to check.
_NEEDS_PAYEE = frozenset({C.MERCHANT_ALLOW})


def inapplicable_clauses(action: ResolvedAction) -> set[C]:
    """The clauses that had nothing to read for this action."""
    if action.items:
        return set()
    return set(_NEEDS_LINE_ITEMS | _NEEDS_PAYEE)


def applicability_for_raw(policy) -> dict[str, int | list[str]]:
    """The same count for a raw call, without needing the action.

    A raw proposal always resolves to an action with no line items, so its
    applicability is a property of the policy alone. Exposed so the proxy does
    not have to reach into the gateway's private resolution to report it.
    """
    present = set(policy.constraints)
    skipped = sorted(str(c) for c in (_NEEDS_LINE_ITEMS | _NEEDS_PAYEE) & present)
    return {
        "evaluated": len(present) - len(skipped),
        "not_applicable": len(skipped),
        "not_applicable_ids": skipped,
    }


def applicability(action: ResolvedAction, policy) -> dict[str, int | list[str]]:
    """A count a screen can render without recomputing the rule.

    Counted against the policy's own constraints, so a mandate that leaves a
    clause unset does not have it reported as skipped by this action.
    """
    present = set(policy.constraints)
    skipped = sorted(str(c) for c in inapplicable_clauses(action) & present)
    return {
        "evaluated": len(present) - len(skipped),
        "not_applicable": len(skipped),
        "not_applicable_ids": skipped,
    }
