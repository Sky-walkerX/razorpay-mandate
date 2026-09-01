"""The storefront's order history: what the customer sees after the agent shops.

This is a demo store, not a database. It holds the rows a judge needs in order to
see money move and one order fail to, alongside the clause that stopped it. On
Cloud Run it lives on tmpfs and resets when the instance recycles, which is
stated on the page rather than hidden.

The rule that governs this module: a row is built from `AuditRecord.action`, a
ResolvedAction the gateway computed from its own price book. It never reads a
Proposal. If the storefront rendered the agent's number while the rail charged
another, the whole boundary would be decorative.
"""
import json
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from mandate.gateway.audit import AuditRecord
from mandate.gateway.core import Decision
from mandate.gateway.state import Verdict

CLEAN = "clean"
DEFAULT_MAX_ROWS = 500

Status = Literal["EXECUTED", "REFUSED", "UNKNOWN"]
Source = Literal["http", "mcp", "agent"]


class StoreLine(BaseModel):
    sku: str
    title: str
    qty: int
    unit_price_paise: int
    amount_paise: int
    category: str


class StoreOrder(BaseModel):
    type: Literal["order"] = "order"
    order_id: str
    ts: datetime
    week: int
    jti: str
    mandate_id: str
    merchant: str
    items: list[StoreLine] = []
    amount_paise: int
    status: Status
    # `verdict` is kept beside `status` on purpose. In the unenforced control arm
    # a DENY still executes, and a row reading EXECUTED / DENY is the honest
    # rendering of that. Collapsing the two would hide the arm.
    verdict: str
    clause_id: str | None = None
    message: str = ""
    idem_key: str = ""
    downstream_id: str | None = None
    source: Source = "http"


class WeekMarker(BaseModel):
    type: Literal["week"] = "week"
    week: int
    family: str = CLEAN
    ts: datetime


def _title_of(line) -> str:
    """The resolved title, stored now rather than looked up later.

    Hostile catalogs reuse `sku_0000` style ids with different text, so resolving
    a week-one SKU against a week-two catalog would silently render the wrong
    product name next to a real refusal.
    """
    return line.title


class OrderStore:
    """Append-only JSONL plus an in-process index, like `RevocationList`.

    `path=None` keeps everything in memory, and that is the default the service
    uses in tests. A shared on-disk default would have the whole suite appending
    to one file.
    """

    def __init__(self, path: Path | str | None = None,
                 max_rows: int = DEFAULT_MAX_ROWS) -> None:
        self.path = Path(path) if path is not None else None
        self.max_rows = max_rows
        self._lock = threading.Lock()
        self._orders: list[StoreOrder] = []
        # Week one is implicit: a fresh store is already in a week, and nobody
        # should have to call advance_week() to get an order list.
        self._weeks: list[WeekMarker] = [
            WeekMarker(week=1, family=CLEAN, ts=datetime.now(UTC))
        ]
        self._seq = 0
        self._rev = 0
        self._load()

    def _load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("type") == "week":
                self._weeks.append(WeekMarker(**row))
            elif row.get("type") == "order":
                self._orders.append(StoreOrder(**row))
        self._seq = len(self._orders)
        self._trim()

    def _append(self, row: BaseModel) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as fh:
            fh.write(row.model_dump_json() + "\n")

    def _trim(self) -> None:
        """Drop the oldest orders only. Week markers are few and always kept, so
        an old week never loses its label."""
        if len(self._orders) > self.max_rows:
            self._orders = self._orders[-self.max_rows:]

    @property
    def current_week(self) -> int:
        return self._weeks[-1].week

    def week_family(self, week: int | None = None) -> str:
        target = self.current_week if week is None else week
        for marker in self._weeks:
            if marker.week == target:
                return marker.family
        return CLEAN

    def weeks(self) -> list[WeekMarker]:
        with self._lock:
            return list(self._weeks)

    def orders(self, week: int | None = None) -> list[StoreOrder]:
        with self._lock:
            if week is None:
                return list(self._orders)
            return [o for o in self._orders if o.week == week]

    def etag(self) -> str:
        """A revision counter, not a row count. Trimming can leave the count
        unchanged while the contents move."""
        with self._lock:
            return f'W/"{self.current_week}-{self._rev}"'

    def advance_week(self, family: str | None = None) -> WeekMarker:
        """Start the next week. A week is a new mandate instance under the same
        signed policy, not a new policy, so nothing here touches the gateway."""
        with self._lock:
            marker = WeekMarker(week=self.current_week + 1,
                                family=family or CLEAN, ts=datetime.now(UTC))
            self._weeks.append(marker)
            self._rev += 1
            self._append(marker)
            return marker

    def record(self, *, decision: Decision, audit_record: AuditRecord | None,
               jti: str, mandate_id: str, source: Source = "http",
               week: int | None = None) -> StoreOrder:
        """Add one row for a gateway decision.

        `audit_record` is None on the early returns in `Gateway.propose`, which
        deny on `authentication` or `pricebook` before writing anything. Those
        rows carry no line items and are still shown, because a refusal a judge
        cannot see is a refusal that did not happen as far as they know.
        """
        action = audit_record.action if audit_record is not None else None

        if decision.executed:
            status: Status = "EXECUTED"
        elif decision.verdict is Verdict.DENY:
            status = "REFUSED"
        else:
            status = "UNKNOWN"

        downstream = decision.downstream or {}

        with self._lock:
            self._seq += 1
            row = StoreOrder(
                order_id=f"ord_{self._seq:06d}",
                ts=audit_record.ts if audit_record is not None else datetime.now(UTC),
                week=self.current_week if week is None else week,
                jti=jti,
                mandate_id=mandate_id,
                merchant=action.merchant if action is not None else "",
                items=[
                    StoreLine(sku=line.sku, title=_title_of(line), qty=line.qty,
                              unit_price_paise=int(line.unit_price),
                              amount_paise=int(line.amount),
                              category=line.category)
                    for line in (action.items if action is not None else [])
                ],
                amount_paise=int(action.amount) if action is not None else 0,
                status=status,
                verdict=decision.verdict.value,
                clause_id=decision.clause_id,
                message=decision.message,
                idem_key=decision.idem_key,
                downstream_id=downstream.get("id"),
                source=source,
            )
            self._orders.append(row)
            self._rev += 1
            self._append(row)
            self._trim()
            return row
