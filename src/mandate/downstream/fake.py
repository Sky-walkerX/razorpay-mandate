"""In-memory downstream with fault injection. Used by every test and the harness."""
import itertools
from typing import Literal

from mandate.money import Paise


class DownstreamTimeout(Exception):
    """We sent the request and never learned the outcome."""


class DownstreamError(Exception):
    """The downstream refused the request."""


class FakeDownstream:
    def __init__(self, amount_multiplier: dict[str, int] | None = None) -> None:
        self._orders: dict[str, dict] = {}
        self._payments: dict[str, dict] = {}
        self._ids = itertools.count(1)
        self._fail_next: Literal["timeout", "error"] | None = None
        self._mult = dict(amount_multiplier or {})

    def fail_next(self, mode: Literal["timeout", "error"]) -> None:
        self._fail_next = mode

    def _maybe_fail_after_write(self) -> None:
        mode, self._fail_next = self._fail_next, None
        if mode == "timeout":
            raise DownstreamTimeout("no response")
        if mode == "error":
            raise DownstreamError("refused")

    def create_order(
        self,
        amount: Paise,
        receipt: str,
        notes: dict,
        skus: list[str] | None = None,
        action=None,
    ) -> dict:
        factor = max((self._mult.get(s, 1) for s in (skus or [])), default=1)
        charged = Paise(int(amount) * factor)
        oid = f"order_{next(self._ids):012d}"
        order = {
            "id": oid,
            "amount": int(charged),
            "currency": "INR",
            "receipt": receipt,
            "notes": notes,
            "status": "created",
        }
        self._orders[oid] = order
        self._maybe_fail_after_write()
        return order

    def void_order(self, order_id: str) -> dict:
        """Cancel an order the gateway decided it should not have placed.

        The status is flipped rather than the record deleted. An order that was
        created and pulled back is a thing that happened, and the audit log has
        to be able to say so.
        """
        o = self._orders.get(order_id)
        if o is None:
            raise DownstreamError(f"unknown order {order_id}")
        o["status"] = "voided"
        return o

    def capture_payment(self, payment_id: str, amount: Paise) -> dict:
        p = {"id": payment_id, "amount": int(amount), "status": "captured"}
        self._payments[payment_id] = p
        self._maybe_fail_after_write()
        return p

    @property
    def orders(self) -> dict[str, dict]:
        return dict(self._orders)

    def fetch_order(self, order_id: str) -> dict:
        return self._orders[order_id]

    def find_orders_by_receipt(self, receipt: str) -> list[dict]:
        return [o for o in self._orders.values() if o["receipt"] == receipt]

