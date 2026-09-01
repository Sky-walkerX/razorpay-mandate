"""Razorpay REST client. Test mode only, asserted at construction."""
import razorpay

from mandate.downstream.fake import DownstreamError, DownstreamTimeout
from mandate.money import Paise

# Razorpay rejects a receipt longer than this. `canonical_intent()` returns a
# 64-character sha256 digest, so every order placed against the real rail was
# refused with "receipt: the length must be no more than 56" and surfaced as a
# DENY on the `downstream` clause. Nothing caught it because the only Razorpay
# test asserts the key-prefix guard and never places an order.
#
# Truncating is safe. The gateway's idempotency is enforced by its own ledger
# against the full idem key; the receipt is the rail's copy, used for
# reconciliation. 56 hex characters is 224 bits, so two distinct baskets
# colliding here is not a thing that happens.
MAX_RECEIPT_CHARS = 56


def _receipt(idem_key: str) -> str:
    return idem_key[:MAX_RECEIPT_CHARS]


class RazorpayDownstream:
    def __init__(self, key_id: str, key_secret: str) -> None:
        if not key_id.startswith("rzp_test_"):
            raise ValueError(f"refusing to start outside test mode: {key_id[:9]}...")
        self._c = razorpay.Client(auth=(key_id, key_secret))

    def create_order(
        self,
        amount: Paise,
        receipt: str,
        notes: dict,
        skus: list[str] | None = None,
    ) -> dict:
        try:
            return self._c.order.create({"amount": int(amount), "currency": "INR",
                                         "receipt": _receipt(receipt), "notes": notes})
        except razorpay.errors.ServerError as e:
            raise DownstreamTimeout(str(e)) from e
        except razorpay.errors.BadRequestError as e:
            raise DownstreamError(str(e)) from e

    def capture_payment(self, payment_id: str, amount: Paise) -> dict:
        return self._c.payment.capture(payment_id, int(amount))

    def fetch_order(self, order_id: str) -> dict:
        return self._c.order.fetch(order_id)

    def void_order(self, order_id: str) -> dict:
        """Pull back an order the gateway should not have placed.

        Razorpay has no order-cancel endpoint, and it does not need one: an
        order is an invoice, and nothing settles until a payment is captured
        against it. So voiding here means proving no payment is outstanding,
        and refunding one if there is. An order left unpaid expires on its own.

        Not exercised against the live rail. The evaluation runs FakeDownstream,
        and this path needs a real overcharging merchant to trigger.
        """
        try:
            payments = self._c.order.payments(order_id).get("items", [])
        except razorpay.errors.ServerError as e:
            raise DownstreamTimeout(str(e)) from e
        except razorpay.errors.BadRequestError as e:
            raise DownstreamError(str(e)) from e

        live = [p for p in payments if p.get("status") in ("authorized", "captured")]
        for p in live:
            self._c.payment.refund(p["id"])
        return {"id": order_id, "status": "voided", "refunded": len(live)}

    def find_orders_by_receipt(self, receipt: str) -> list[dict]:
        # Truncated the same way it was written, or reconciliation never matches.
        wanted = _receipt(receipt)
        page = self._c.order.all({"count": 100})
        return [o for o in page.get("items", []) if o.get("receipt") == wanted]
