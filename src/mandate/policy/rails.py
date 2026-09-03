"""Project a signed policy down onto the rails, and show what does not survive.

The thesis of this project is one subtraction: a person states more than a payment
rail can hold, and the remainder ends up in a system prompt. That is easy to assert
and better to show, so this renders the same signed policy as an AP2 mandate and as a
UPI Reserve Pay authorisation, and reports which clauses had nowhere to go.

Field names follow the AP2 reference types (`IntentMandate`: `natural_language_description`,
`merchants`, `skus`, `intent_expiry`, `user_cart_confirmation_required`,
`requires_refundability`) and the Payment Mandate constraint types named in the v0.2
spec (`payment.agent_recurrence`, allowed payee, amount range, budget, execution date).

AP2 is richer than a single amount-plus-expiry, and this file is deliberate about
saying so. Overstating the gap would be the same failure this project exists to catch.
"""
from datetime import datetime

from pydantic import BaseModel

from mandate.money import Paise, fmt
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Policy

# Where each clause can live once the policy leaves this system.
#   ap2          a structured AP2 field or Payment Mandate constraint holds it
#   prose        AP2 carries it only inside natural_language_description
#   none         no representation on that rail at all
AP2_CARRIES: dict[C, tuple[str, str]] = {
    C.BUDGET_TOTAL: ("ap2", "Budget constraint, with Agent Recurrence"),
    C.BUDGET_PER_TRANSACTION: ("ap2", "Amount Range constraint"),
    C.MERCHANT_ALLOW: ("ap2", "IntentMandate.merchants, Allowed Payee constraint"),
    C.TIME_WINDOW: ("ap2", "IntentMandate.intent_expiry, Execution Date constraint"),
    C.VELOCITY: ("ap2", "payment.agent_recurrence frequency and max_occurrences"),
    C.BUDGET_PER_ITEM: ("none", "no per-line-item ceiling exists"),
    C.CATEGORY_DENY: ("prose", "only as words in natural_language_description"),
    C.QUANTITY_MAX_PER_ITEM: ("none", "skus is an allowlist, not a quantity bound"),
    C.ITEM_DENY_RECENT: ("none", "no notion of what was bought before"),
    # AP2 has user_cart_confirmation_required, but it is a boolean. "Always
    # confirm" carries; "confirm above Rs 15,000" does not, and the threshold
    # is the constraint. Marking this as held would overstate the rail.
    C.AFA_REQUIRED: ("prose", "user_cart_confirmation_required is a flag, not a threshold"),
}

# UPI Reserve Pay blocks an amount against one merchant until an expiry. That is the
# whole vocabulary, which is the point.
RESERVE_PAY_CARRIES: dict[C, tuple[str, str]] = {
    C.BUDGET_TOTAL: ("rail", "the blocked amount"),
    C.MERCHANT_ALLOW: ("rail", "the payee, and only one of them"),
    C.TIME_WINDOW: ("rail", "the block expiry"),
    C.BUDGET_PER_TRANSACTION: ("none", "no per-debit ceiling inside the block"),
    C.BUDGET_PER_ITEM: ("none", "the rail never sees line items"),
    C.CATEGORY_DENY: ("none", "the rail never sees categories"),
    C.QUANTITY_MAX_PER_ITEM: ("none", "the rail never sees quantities"),
    C.VELOCITY: ("none", "no debit count inside the block"),
    C.ITEM_DENY_RECENT: ("none", "no purchase history"),
    # RBI requires an additional factor above Rs 15,000, but a Reserve Pay block
    # is authorised once at the front. There is no per-debit step-up inside it.
    C.AFA_REQUIRED: ("none", "the block is pre-authorised; no step-up per debit"),
}

HELD = {"ap2", "rail"}


class ClauseFate(BaseModel):
    clause: str
    stated_by_user: bool
    ap2: str
    ap2_note: str
    reserve_pay: str
    reserve_pay_note: str


class RailDiff(BaseModel):
    mandate_id: str
    policy_hash: str
    total_clauses: int
    ap2_held: int
    reserve_pay_held: int
    fates: list[ClauseFate]

    @property
    def ap2_lost(self) -> int:
        return self.total_clauses - self.ap2_held

    @property
    def reserve_pay_lost(self) -> int:
        return self.total_clauses - self.reserve_pay_held


def _expiry(dt: datetime) -> str:
    return dt.isoformat()


def to_ap2_intent_mandate(policy: Policy) -> dict:
    """The IntentMandate an AP2 agent would carry for this policy.

    `natural_language_description` is the user's own words, unchanged. Everything the
    rail cannot hold structurally is still in there as prose, which is exactly the
    problem: prose is not a control, and nothing downstream evaluates it.
    """
    merchants = list(policy.constraints.get(C.MERCHANT_ALLOW, []) or [])
    return {
        "natural_language_description": policy.source_text,
        "merchants": merchants,
        "intent_expiry": _expiry(policy.expires),
        "user_cart_confirmation_required": False,
        "requires_refundability": False,
    }


def to_ap2_payment_constraints(policy: Policy) -> list[dict]:
    """The Payment Mandate constraints that carry structurally. Five of nine."""
    out: list[dict] = []
    c = policy.constraints
    if (total := c.get(C.BUDGET_TOTAL)):
        out.append({"type": "payment.budget",
                    "amount": {"value": int(total["max"]), "currency": "INR"}})
    if (per_txn := c.get(C.BUDGET_PER_TRANSACTION)):
        out.append({"type": "payment.amount_range",
                    "max": {"value": int(per_txn["max"]), "currency": "INR"}})
    if (merchants := c.get(C.MERCHANT_ALLOW)):
        out.append({"type": "payment.allowed_payee", "payees": list(merchants)})
    if (vel := c.get(C.VELOCITY)) and vel.get("max_actions") is not None:
        out.append({"type": "payment.agent_recurrence",
                    "max_occurrences": int(vel["max_actions"]),
                    "frequency": str(vel.get("window", "mandate")).upper()})
    out.append({"type": "payment.execution_date",
                "not_before": _expiry(policy.issued),
                "not_after": _expiry(policy.expires)})
    return out


def to_reserve_pay(policy: Policy) -> dict:
    """A UPI Reserve Pay block: one amount, one payee, one expiry.

    A Reserve Pay block names a single payee, so an allowlist of three merchants
    cannot be expressed as one block. That is reported, not quietly collapsed.
    """
    merchants = list(policy.constraints.get(C.MERCHANT_ALLOW, []) or [])
    total = policy.constraints.get(C.BUDGET_TOTAL, {}).get("max", 0)
    return {
        "blocked_amount": {"value": int(total), "currency": "INR"},
        "payee": merchants[0] if merchants else None,
        "payee_overflow": merchants[1:],
        "expiry": _expiry(policy.expires),
        "mandate_ref": policy.mandate_id,
    }


def diff(policy: Policy, policy_hash: str = "") -> RailDiff:
    stated = set(policy.provenance.stated)
    fates: list[ClauseFate] = []
    for cid in policy.constraints:
        a_kind, a_note = AP2_CARRIES.get(cid, ("none", "unmapped"))
        r_kind, r_note = RESERVE_PAY_CARRIES.get(cid, ("none", "unmapped"))
        fates.append(ClauseFate(
            clause=str(cid), stated_by_user=cid in stated,
            ap2=a_kind, ap2_note=a_note,
            reserve_pay=r_kind, reserve_pay_note=r_note))
    return RailDiff(
        mandate_id=policy.mandate_id,
        policy_hash=policy_hash,
        total_clauses=len(fates),
        ap2_held=sum(1 for f in fates if f.ap2 in HELD),
        reserve_pay_held=sum(1 for f in fates if f.reserve_pay in HELD),
        fates=fates,
    )


def money_at_risk(policy: Policy) -> Paise:
    """What a rail-only authorisation leaves spendable that the policy would refuse.

    Reserve Pay blocks the total and nothing else, so every rupee under the cap is
    reachable by a purchase this policy would have denied on some other clause.
    """
    return Paise(int(policy.constraints.get(C.BUDGET_TOTAL, {}).get("max", 0)))


__all__ = [
    "AP2_CARRIES",
    "RESERVE_PAY_CARRIES",
    "ClauseFate",
    "RailDiff",
    "diff",
    "fmt",
    "money_at_risk",
    "to_ap2_intent_mandate",
    "to_ap2_payment_constraints",
    "to_reserve_pay",
]


def project_to_reserve_pay(policy: Policy) -> Policy:
    """The same mandate as UPI Reserve Pay would hold it, and nothing more.

    Reserve Pay blocks an amount against one payee until an expiry. Every clause
    whose fate in RESERVE_PAY_CARRIES is not "rail" has nowhere to go, so it is
    dropped rather than quietly enforced by us on the rail's behalf. The payee
    list narrows to one entry for the same reason: a block names a single payee,
    so carrying all three would credit the rail with a capability it lacks.

    The projection reads the table above rather than restating it. Two opinions
    about the rail's vocabulary would let `/rails` and the shadow gateway drift
    apart while each looked correct on its own.

    The mandate id is preserved deliberately: a token bound to this mandate must
    still verify against the projection, since the shadow answers the same
    proposal with the same bearer token.
    """
    can_hold = {cid for cid, (fate, _) in RESERVE_PAY_CARRIES.items() if fate == "rail"}
    kept: dict[C, dict | list] = {
        cid: value for cid, value in policy.constraints.items() if cid in can_hold
    }
    payees = kept.get(C.MERCHANT_ALLOW)
    if isinstance(payees, list) and payees:
        kept[C.MERCHANT_ALLOW] = [payees[0]]
    return policy.model_copy(update={"constraints": kept})
