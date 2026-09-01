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

    def find_orders_by_receipt(self, receipt: str) -> list[dict]:
        # Truncated the same way it was written, or reconciliation never matches.
        wanted = _receipt(receipt)
        page = self._c.order.all({"count": 100})
        return [o for o in page.get("items", []) if o.get("receipt") == wanted]
