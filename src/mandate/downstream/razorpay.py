"""Razorpay REST client. Test mode only, asserted at construction."""
import razorpay

from mandate.downstream.fake import DownstreamError, DownstreamTimeout
from mandate.money import Paise


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
                                         "receipt": receipt, "notes": notes})
        except razorpay.errors.ServerError as e:
            raise DownstreamTimeout(str(e)) from e
        except razorpay.errors.BadRequestError as e:
            raise DownstreamError(str(e)) from e

    def capture_payment(self, payment_id: str, amount: Paise) -> dict:
        return self._c.payment.capture(payment_id, int(amount))

    def fetch_order(self, order_id: str) -> dict:
        return self._c.order.fetch(order_id)

    def find_orders_by_receipt(self, receipt: str) -> list[dict]:
        page = self._c.order.all({"count": 100})
        return [o for o in page.get("items", []) if o.get("receipt") == receipt]
