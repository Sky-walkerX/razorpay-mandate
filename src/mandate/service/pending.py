"""Out-of-band human approval queue for AFA-flagged actions.

When an action exceeds the AFA threshold (RBI 2026 e-mandate limit), the gateway
holds the verdict at UNKNOWN (afa.required). A pending approval token (`ref`) is
generated for the principal/human out-of-band loop.

CRITICAL SECURITY INVARIANT:
The `ref` token MUST NEVER be returned to the agent in any response. The agent
receives only verdict: UNKNOWN and clause: afa.required. The approval URL or ref
is visible only to the principal via authenticated channel / mobile UI.
"""
import secrets
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class PendingItem:
    ref: str
    mandate_id: str
    intent: str
    merchant: str
    amount: int
    items: list[dict[str, Any]]
    threshold: int
    created_at: datetime
    expires_at: datetime
    status: str = "pending"  # "pending" | "approved" | "rejected" | "expired"

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["expires_at"] = self.expires_at.isoformat()
        return d


class PendingApprovals:
    def __init__(self, default_ttl_seconds: int = 600) -> None:
        self.default_ttl = timedelta(seconds=default_ttl_seconds)
        self._lock = threading.Lock()
        self._items: dict[str, PendingItem] = {}
        self._by_intent: dict[str, str] = {}

    def open(
        self,
        intent: str,
        mandate_id: str,
        merchant: str,
        amount: int,
        items: list[dict[str, Any]],
        threshold: int,
        ttl: timedelta | None = None,
        now: datetime | None = None,
    ) -> str:
        """Create or return an existing pending approval for an intent."""
        now_dt = now or datetime.now(UTC)
        ttl_delta = ttl or self.default_ttl

        with self._lock:
            # If an existing pending item exists for this intent and is not expired, return its ref
            existing_ref = self._by_intent.get(intent)
            if existing_ref:
                item = self._items.get(existing_ref)
                if item and item.status == "pending" and item.expires_at > now_dt:
                    return item.ref

            ref = secrets.token_urlsafe(32)
            item = PendingItem(
                ref=ref,
                mandate_id=mandate_id,
                intent=intent,
                merchant=merchant,
                amount=amount,
                items=items,
                threshold=threshold,
                created_at=now_dt,
                expires_at=now_dt + ttl_delta,
                status="pending",
            )
            self._items[ref] = item
            self._by_intent[intent] = ref
            return ref

    def get(self, ref: str, now: datetime | None = None) -> PendingItem | None:
        now_dt = now or datetime.now(UTC)
        with self._lock:
            item = self._items.get(ref)
            if not item:
                return None
            if item.status == "pending" and item.expires_at <= now_dt:
                item.status = "expired"
            return item

    def get_by_intent(self, intent: str, now: datetime | None = None) -> PendingItem | None:
        with self._lock:
            ref = self._by_intent.get(intent)
            if not ref:
                return None
            return self.get(ref, now)

    def list_for_principal(self, now: datetime | None = None) -> list[PendingItem]:
        now_dt = now or datetime.now(UTC)
        with self._lock:
            results: list[PendingItem] = []
            for item in self._items.values():
                if item.status == "pending" and item.expires_at <= now_dt:
                    item.status = "expired"
                results.append(item)
            return sorted(results, key=lambda x: x.created_at, reverse=True)

    def resolve(
        self,
        ref: str,
        decision: str,  # "approve" | "reject"
        now: datetime | None = None,
    ) -> PendingItem | None:
        now_dt = now or datetime.now(UTC)
        with self._lock:
            item = self._items.get(ref)
            if not item:
                return None
            if item.status == "pending" and item.expires_at <= now_dt:
                item.status = "expired"
                return item
            if item.status != "pending":
                return item

            if decision == "approve":
                item.status = "approved"
            elif decision == "reject":
                item.status = "rejected"
            return item
