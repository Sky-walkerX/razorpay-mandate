"""Per-session ephemeral gateway isolation.

Each session is identified by the bearer token's `jti` and owns an isolated
directory `/tmp/sessions/<jti>/` containing its own `audit.jsonl` and `ledger.jsonl`.
Every session shares the same signed policy, catalog, pricebook, downstream,
and revocation list.
"""
import shutil
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway, Mode
from mandate.gateway.idem import Ledger
from mandate.gateway.pricebook import PriceBook
from mandate.gateway.revocation import RevocationList
from mandate.gateway.tokens import TokenClaims
from mandate.policy.models import Policy


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

    def create_session(self, token: str, claims: TokenClaims) -> Session:
        with self._lock:
            self._evict_idle_locked()

            session_dir = self.base_dir / claims.jti
            if session_dir.exists():
                shutil.rmtree(session_dir, ignore_errors=True)
            session_dir.mkdir(parents=True, exist_ok=True)

            audit = AuditLog(session_dir / "audit.jsonl")
            ledger = Ledger(session_dir / "ledger.jsonl")

            gw = Gateway(
                policy=self.policy,
                downstream=self.downstream,
                audit=audit,
                mode=Mode.ENFORCE,
                ledger=ledger,
                pricebook=self.pricebook,
                capability_secret=self.capability_secret,
                issuer_public_key=self.issuer_public_key,
                revocations=self.revocations,
            )

            now = datetime.now(UTC)
            session = Session(
                jti=claims.jti,
                token=token,
                mandate_id=claims.mandate_id,
                created_at=now,
                last_active=now,
                dir_path=session_dir,
                gateway=gw,
                audit=audit,
                ledger=ledger,
            )
            self._sessions[claims.jti] = session
            return session

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
