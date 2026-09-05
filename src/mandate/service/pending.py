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
    jti: str
    mandate_id: str
    intent: str
    merchant: str
    amount: int
    items: list[dict[str, Any]]
    threshold: int
    created_at: datetime
    expires_at: datetime
    status: str = "pending"  # "pending" | "approved" | "rejected" | "expired"

    def to_dict(self, include_ref: bool = False) -> dict[str, Any]:
        """Render for the wire. The ref is withheld unless explicitly asked for.

        The ref is the bearer credential for POST /v1/approve, so it is emitted only
        on the principal's authenticated channel. Defaulting it off means a new
        surface that forgets to think about it leaks nothing.
        """
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["expires_at"] = self.expires_at.isoformat()
        d.pop("jti", None)
        if not include_ref:
            d.pop("ref", None)
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
        jti: str,
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
                jti=jti,
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

    def list_for_principal(
        self, jti: str, now: datetime | None = None
    ) -> list[PendingItem]:
        """Every escalation raised by one session, newest first.

        `jti` is required rather than optional. A principal sees what their own
        agent proposed and nothing else -- on a public deployment an unscoped
        listing would show one visitor another visitor's basket, and hand them a
        ref that approves it.
        """
        now_dt = now or datetime.now(UTC)
        with self._lock:
            results: list[PendingItem] = []
            for item in self._items.values():
                if item.jti != jti:
                    continue
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
