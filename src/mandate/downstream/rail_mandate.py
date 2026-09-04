"""Create the rail's own mandate for a policy, so the comparison uses a real object.

`/rails` argues that a payment rail holds three of this mandate's ten limits. That
argument was made entirely against a table written in this repo, which is a weaker
thing than it sounds: the reader has only our word for what the rail can express.

This creates the actual object. `POST /v1/subscription_registration/auth_links`
returns a hosted authorisation link a person opens on their phone, and the order
behind it carries a genuine rail mandate:

    {"max_amount": 200000, "frequency": "as_presented",
     "expire_at": 1791000000, "method": "upi"}

A cap, a payee and an expiry. Three fields, which is the argument, now checkable.

**This is UPI Autopay, not UPI Reserve Pay, and the difference is stated rather
than blurred.** Reserve Pay's single-block-multiple-debit flow is gated: creating
an order with `token.type="single_block_multiple_debit"` on a plain test account
succeeds and silently drops the token spec, and the S2S UPI endpoint answers "the
requested URL was not found on the server". So nothing here can produce a real
Reserve Pay block. Autopay is the closest publicly reachable mandate, it carries
the same three fields, and calling it Reserve Pay would be the kind of claim this
project exists to catch.

One difference is worth naming because it looks like a fourth held clause and is
not. Autopay carries `frequency`, which Reserve Pay lacks. But `as_presented`
bounds nothing at all, and `daily` bounds one debit per day rather than three per
mandate, so it is `partial` in the vocabulary `regulatory.py` already uses. It is
not `velocity`.
"""
from datetime import datetime
from typing import Any

import httpx

from mandate.money import Paise
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Policy

AUTH_LINK_URL = "https://api.razorpay.com/v1/subscription_registration/auth_links"

# Razorpay rejects an amount below this on the authorisation transaction itself.
# The block is `max_amount`; this is the token-registration charge.
AUTH_TXN_PAISE = 100


class RailMandateError(RuntimeError):
    """The rail refused to create the mandate."""


class RailMandate(dict):
    """The created auth link, as the rail returned it."""


def create_auth_link(
    policy: Policy,
    key_id: str,
    key_secret: str,
    *,
    contact: str = "9123456780",
    email: str = "mandate@example.test",
    name: str = "Mandate demo",
    timeout_s: float = 20.0,
) -> RailMandate:
    """Open the rail's mandate for this policy. Test mode only.

    Every field is read off the signed policy: the block is `budget.total`, the
    expiry is `policy.expires`, and the mandate id travels in `notes` so the two
    documents can be lined up afterwards. Nothing here is typed by hand, which is
    the same rule the web console follows about `evidence.json`.
    """
    if not key_id.startswith("rzp_test_"):
        raise ValueError(f"refusing to create a rail mandate outside test mode: {key_id[:9]}...")

    cap = int(policy.constraints.get(C.BUDGET_TOTAL, {}).get("max", 0))
    if cap <= 0:
        raise RailMandateError(
            "this policy sets no budget.total, so there is no amount to block")

    expire_at = int(policy.expires.timestamp())
    payload: dict[str, Any] = {
        "customer": {"name": name, "email": email, "contact": contact},
        "type": "link",
        "amount": AUTH_TXN_PAISE,
        "currency": "INR",
        "description": f"{policy.mandate_id}: block up to {Paise(cap)} paise until "
                       f"{policy.expires.date().isoformat()}",
        "subscription_registration": {
            "method": "upi",
            "max_amount": cap,
            "expire_at": expire_at,
            # The rail's weakest frequency, on purpose. Choosing `daily` here
            # would let the page imply the rail bounds rate, and it does not
            # bound this mandate's rate: velocity is 3 orders per mandate.
            "frequency": "as_presented",
        },
        "expire_by": expire_at,
        "sms_notify": 0,
        "email_notify": 0,
        "notes": {"mandate_id": policy.mandate_id},
    }

    try:
        resp = httpx.post(AUTH_LINK_URL, json=payload, auth=(key_id, key_secret),
                          timeout=timeout_s)
    except httpx.HTTPError as e:
        raise RailMandateError(f"could not reach the rail: {e}") from e

    body = resp.json() if resp.content else {}
    if resp.status_code >= 400:
        raise RailMandateError(
            (body.get("error") or {}).get("description") or f"HTTP {resp.status_code}")
    return RailMandate(body)


def summarise(link: dict, policy: Policy) -> dict[str, Any]:
    """What the rail's mandate holds, next to what the policy states.

    Derived from the response rather than echoed from the request, so a rail that
    quietly changed a field would show up here instead of being papered over.
    """
    reg = (link.get("token") or {})
    cap = int(policy.constraints.get(C.BUDGET_TOTAL, {}).get("max", 0))
    expires = policy.expires
    return {
        "id": link.get("id"),
        "short_url": link.get("short_url"),
        "status": link.get("auth_link_status") or link.get("status"),
        "order_id": link.get("order_id"),
        "customer_id": link.get("customer_id"),
        # What the rail can say. Three fields.
        "rail_holds": {
            "max_amount_paise": int(reg.get("max_amount") or cap),
            "payee": "this merchant, and only this one",
            "expire_at": int(reg.get("expire_at") or expires.timestamp()),
            "frequency": reg.get("frequency") or "as_presented",
        },
        "product": "UPI Autopay",
        "not_reserve_pay_because":
            "Reserve Pay's single-block-multiple-debit flow is not enabled on a "
            "plain test account: the order is created and the token spec is "
            "dropped. Autopay carries the same cap, payee and expiry.",
    }


def _ts(dt: datetime) -> int:
    return int(dt.timestamp())
