"""Per-session ephemeral gateway isolation.

Each session is identified by the bearer token's `jti` and owns an isolated
directory `/tmp/sessions/<jti>/` containing its own `audit.jsonl` and `ledger.jsonl`.
Every session shares the same signed policy, catalog, pricebook, downstream,
and revocation list.
"""
import shutil
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mandate.downstream.fake import FakeDownstream
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway, Mode
from mandate.gateway.idem import Ledger
from mandate.gateway.pricebook import PriceBook
from mandate.gateway.revocation import RevocationList
from mandate.gateway.tokens import TokenClaims
from mandate.policy.models import Policy
from mandate.policy.rails import project_to_reserve_pay


@dataclass
class Session:
    jti: str
    token: str
    mandate_id: str
    created_at: datetime
    last_active: datetime
    dir_path: Path
    gateway: Gateway
    audit: AuditLog
    ledger: Ledger
    mode: Mode = Mode.ENFORCE
    # The same proposal answered as UPI Reserve Pay would answer it. A real
    # Gateway on a projected policy, with its own rail, ledger and chain, so its
    # spend is never confused for the mandate's and the block drains honestly.
    #
    # One per payee, because a Reserve Pay block names one payee and a user who
    # shops at three shops opens three blocks. Modelling a single block against
    # `payees[0]` made every refusal land on the payee, which said nothing about
    # the rail's vocabulary and was the whole point of the comparison. Built
    # lazily by `SessionManager.shadow_for`.
    shadows: dict[str, Gateway] = field(default_factory=dict)


class SessionManager:
    def __init__(
        self,
        policy: Policy,
        pricebook: PriceBook,
        downstream,
        capability_secret: str,
        issuer_public_key: str,
        revocations: RevocationList,
        base_dir: Path | str = Path("/tmp/sessions"),
        max_sessions: int = 100,
        idle_timeout_seconds: int = 1800,
    ) -> None:
        self.policy = policy
        self.pricebook = pricebook
        self.downstream = downstream
        self.capability_secret = capability_secret
        self.issuer_public_key = issuer_public_key
        self.revocations = revocations
        self.base_dir = Path(base_dir)
        self.max_sessions = max_sessions
        self.idle_timeout = timedelta(seconds=idle_timeout_seconds)
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        token: str,
        claims: TokenClaims,
        mode: Mode = Mode.ENFORCE,
        pricebook: PriceBook | None = None,
        policy: Policy | None = None,
    ) -> Session:
        """Build a session. `mode` is a parameter so the console can run an
        unenforced control arm beside the enforced one; `pricebook` so a run
        against a hostile catalog resolves prices from that catalog rather than
        the default one, which would fail closed on every unknown SKU; `policy`
        so a judge's freshly compiled sandbox mandate is enforced by this same
        gateway rather than by a second code path built to look like it.

        A sandbox policy is unsigned and carries the reserved sandbox mandate id.
        Nothing is relaxed to accommodate it: `Gateway._verify_token` still
        requires the bearer token to be bound to whatever policy this session
        serves, which is why sandbox tokens are minted offline against that
        reserved id. See `mandate.service.sandbox`."""
        with self._lock:
            self._evict_idle_locked()

            session_dir = self.base_dir / claims.jti
            if session_dir.exists():
                shutil.rmtree(session_dir, ignore_errors=True)
            session_dir.mkdir(parents=True, exist_ok=True)

            audit = AuditLog(session_dir / "audit.jsonl")
            ledger = Ledger(session_dir / "ledger.jsonl")

            gw = Gateway(
                policy=policy if policy is not None else self.policy,
                downstream=self.downstream,
                audit=audit,
                mode=mode,
                ledger=ledger,
                pricebook=pricebook if pricebook is not None else self.pricebook,
                capability_secret=self.capability_secret,
                issuer_public_key=self.issuer_public_key,
                revocations=self.revocations,
            )

            now = datetime.now(UTC)
            session = Session(
                jti=claims.jti,
                token=token,
                mandate_id=gw.policy.mandate_id,
                created_at=now,
                last_active=now,
                dir_path=session_dir,
                gateway=gw,
                audit=audit,
                ledger=ledger,
                mode=mode,
            )
            self._sessions[claims.jti] = session
            return session

    def shadow_for(self, session: Session, payee: str | None) -> Gateway:
        """The Reserve Pay block this payee would have been shopped under.

        One block per payee, cached for the life of the session so its own total
        drains across successive orders exactly as a real block would. A block
        opened for a shop the user never allowed is not modelled: an unknown
        payee falls back to the first allowed one, which is `project_to_reserve_pay`'s
        own rule rather than a second opinion about it.
        """
        key = (payee or "").strip().lower()
        with self._lock:
            existing = session.shadows.get(key)
            if existing is not None:
                return existing

            shadow_dir = session.dir_path / "shadow" / (key or "_default")
            shadow_dir.mkdir(parents=True, exist_ok=True)
            shadow = Gateway(
                policy=project_to_reserve_pay(session.gateway.policy, payee=key),
                # Its own rail. The shadow's orders are a projection, not money
                # this mandate authorised, and must not reach the real one.
                downstream=FakeDownstream(),
                audit=AuditLog(shadow_dir / "audit.jsonl"),
                mode=Mode.ENFORCE,
                ledger=Ledger(shadow_dir / "ledger.jsonl"),
                pricebook=session.gateway.pricebook,
                capability_secret=self.capability_secret,
                issuer_public_key=self.issuer_public_key,
                revocations=self.revocations,
            )
            session.shadows[key] = shadow
            return shadow

    def get_session(self, jti: str) -> Session | None:
        with self._lock:
            session = self._sessions.get(jti)
            if session:
                session.last_active = datetime.now(UTC)
            return session

    def has_session(self, jti: str) -> bool:
        with self._lock:
            return jti in self._sessions

    def evict_session(self, jti: str) -> None:
        with self._lock:
            self._evict_session_locked(jti)

    def _evict_session_locked(self, jti: str) -> None:
        session = self._sessions.pop(jti, None)
        if session and session.dir_path.exists():
            try:
                shutil.rmtree(session.dir_path, ignore_errors=True)
            except Exception:
                pass

    def _evict_idle_locked(self) -> None:
        now = datetime.now(UTC)
        idle_jtis = [
            jti for jti, sess in self._sessions.items()
            if now - sess.last_active > self.idle_timeout
        ]
        for jti in idle_jtis:
            self._evict_session_locked(jti)

        while len(self._sessions) >= self.max_sessions:
            oldest_jti = min(self._sessions.keys(), key=lambda k: self._sessions[k].last_active)
            self._evict_session_locked(oldest_jti)
