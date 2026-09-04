"""What each clause is called when a person reads it.

Every clause carries two names. The identifier -- `budget.per_transaction` --
is what the signed policy, the audit chain and the ledger use, and it is the
right name in all three: those exist to be reconciled against the document.
The label is what a first-time visitor reads, and it is the only one that
belongs on a refusal banner, an order card or a limits table.

This module is the single source of the second name. It used to live in four
places: `harness/evidence.py`, twice over in `service/server.py`, and a third
copy in the web console's offline fallback. Three were subsets of the first and
one had already drifted -- server.py called the expiry clause `time_window`
while the policy, the audit log and the evidence payload all call it
`time.window`, so that one clause would have surfaced as a bare identifier
while its nine neighbours read as English.

`shape` and `against` belong to the same table because they are the other half
of the same answer -- what the clause is written as, and what it is checked
against -- and splitting them across two modules is how the labels drifted in
the first place.
"""
from typing import Any

# The ten constraint types, in the order the interface reads them out. This order
# is frozen and is NOT the evaluator's order (`ALL_EVALUATORS` checks the
# per-order cap first, and interleaves the rules differently). It is load-bearing
# anyway: a clause's position here is its Part number, which is cited in every
# refusal, printed on the failure cards, baked into `evidence.json` and spoken in
# the pitch video -- "stopped by Part 4" means velocity because velocity is
# fourth in this list. Reordering renumbers all of that at once.
#
# Only the human-readable half lives here: bounds and provenance are read from
# the signed policy so the two can never disagree.
PART_LABELS: list[dict[str, Any]] = [
    {"key": "budget.total", "label": "Total budget", "kind": "limit",
     "shape": "{max: paise}", "against": "everything committed so far"},
    {"key": "budget.per_transaction", "label": "Most per order", "kind": "limit",
     "shape": "{max: paise}", "against": "the amount of this order"},
    {"key": "budget.per_item", "label": "Most per item", "kind": "limit",
     "shape": "{max: paise}", "against": "the dearest line item"},
    {"key": "velocity", "label": "Orders allowed", "kind": "limit",
     "shape": "{max_actions, window}", "against": "orders already committed"},
    {"key": "quantity.max_per_item", "label": "Most of any one item", "kind": "limit",
     "shape": "{max: int}", "against": "the quantity on each line"},
    {"key": "merchant.allow", "label": "Shops you allow", "kind": "rule",
     "shape": "[merchant_id]", "against": "the seller this order resolves to"},
    {"key": "category.deny", "label": "Never buy", "kind": "rule",
     "shape": "[category]", "against": "the category each item resolves to"},
    {"key": "time.window", "label": "Rules expire", "kind": "rule",
     "shape": "{before, after}", "against": "the gateway's clock"},
    {"key": "item.deny_recent", "label": "Repeat orders", "kind": "rule",
     "shape": "{window_days, source}", "against": "your recent order history"},
    {"key": "afa.required", "label": "Ask me first above", "kind": "limit",
     "shape": "{threshold: paise}", "against": "the amount of this order"},
]

# The clauses a refusal can name that are not constraints at all. They reach the
# same banner the budget clauses do -- a visitor who trips one is already having
# the worst moment the interface offers, which is the wrong moment to show them
# a token. `downstream` is what the gateway files a rail failure under.
OTHER_LABELS: dict[str, str] = {
    "authentication": "Your access token",
    "pricebook": "Our price list",
    "idempotency": "Sent twice",
    "downstream": "The payment network",
    "rail.divergence": "Charged more than approved",
    "capture.binding": "Payment did not match the order",
    "capture.replay": "Payment already taken",
    "revocation.token": "Access cut off",
    "revocation.manual": "Access cut off",
}

LABELS: dict[str, str] = {
    **{p["key"]: p["label"] for p in PART_LABELS},
    **OTHER_LABELS,
}


def label_for(clause_id: str | None) -> str:
    """The clause's name for a reader, or the identifier itself if it has none.

    Falling back to the identifier is deliberate. An unregistered clause looks
    wrong on screen and gets fixed; a plausible invented name would read as a
    rule the gateway does not have.
    """
    if not clause_id:
        return ""
    return LABELS.get(clause_id, clause_id)
