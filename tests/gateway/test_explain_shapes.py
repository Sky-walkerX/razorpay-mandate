"""The two sentences a refusal can be, pinned.

`_explain` writes the message a visitor reads on `/try`, `/store` and the live
agent panel. It is the right wording for an audit log -- observed against bound
-- and the wrong wording for a person, so `humanise()` in `web/src/lib/plain.ts`
rewrites both shapes into sentences.

That rewriter matches on the exact format string. If `_explain` changes and this
does not go red, the web silently falls back to printing the log line, which is
the state this work was undoing. So the shapes are pinned here, next to the code
that emits them, and the failure message names the file that has to change with
them.
"""
import re

import pytest

from mandate.gateway.core import _explain
from mandate.gateway.state import ClauseResult, Verdict
from mandate.policy.models import ConstraintId as C

WEB_REWRITER = "web/src/lib/plain.ts"

MONEY = re.compile(r"^[a-z_.]+: limit ₹[\d,.]+, attempted ₹[\d,.]+$")
ORDERS = re.compile(r"^[a-z_.]+: limit \d+ orders, attempted \d+$")
PER_ITEM = re.compile(r"^[a-z_.]+: limit \d+ per item, attempted \d+$")


def _clause(cid, observed, limit):
    return ClauseResult(id=cid, result=Verdict.DENY, observed=observed, limit=limit)


@pytest.mark.parametrize("cid", [
    C.BUDGET_TOTAL, C.BUDGET_PER_TRANSACTION, C.BUDGET_PER_ITEM, C.AFA_REQUIRED,
])
def test_a_money_refusal_keeps_the_shape_the_web_rewrites(cid):
    msg = _explain(_clause(cid, 712500, 100000))
    assert MONEY.match(msg), f"{msg!r} no longer matches; update humanise() in {WEB_REWRITER}"


def test_a_velocity_refusal_keeps_the_shape_the_web_rewrites():
    msg = _explain(_clause(C.VELOCITY, 4, 3))
    assert ORDERS.match(msg), f"{msg!r} no longer matches; update humanise() in {WEB_REWRITER}"


def test_a_quantity_refusal_keeps_the_shape_the_web_rewrites():
    msg = _explain(_clause(C.QUANTITY_MAX_PER_ITEM, 6, 5))
    assert PER_ITEM.match(msg), f"{msg!r} no longer matches; update humanise() in {WEB_REWRITER}"


def test_the_clause_id_is_still_the_first_thing_in_the_logged_message():
    """The web strips this prefix; the audit record keeps it.

    Both halves matter. A log line that does not name its clause cannot be
    reconciled against the signed policy, and a banner that leads with one
    cannot be read by a visitor.
    """
    msg = _explain(_clause(C.BUDGET_PER_TRANSACTION, 712500, 100000))
    assert msg.startswith("budget.per_transaction: ")
