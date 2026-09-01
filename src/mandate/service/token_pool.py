"""Pre-minted offline token pool for ephemeral judge sessions.

Holds pre-minted agent bearer tokens bound to the mandate policy.
Tokens are handed out one per session. Revoked tokens are retired permanently
and never return to the pool.

`_retired` is per-process, so it forgets across a restart. The persistent record
is the RevocationList on disk, and `claim_token` consults it through
`is_revoked`. Without that, a token revoked in yesterday's demo is handed to
today's first visitor and every call they make fails authentication.
"""
import json
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from mandate.gateway.tokens import TokenClaims, verify_agent_token


class PoolExhausted(Exception):
    """No available tokens remain in the pool."""


class TokenPool:
    def __init__(
        self,
        tokens: Sequence[str] | None = None,
        is_revoked: Callable[[str], bool] | None = None,
    ) -> None:
        self.is_revoked = is_revoked
        self._available: list[str] = list(tokens or [])
        self._claimed: dict[str, str] = {}
        self._retired: set[str] = set()
        self._lock = threading.Lock()

    @classmethod
    def from_file(cls, path: Path | str) -> "TokenPool":
        p = Path(path)
        if not p.exists():
            return cls([])
        data = json.loads(p.read_text())
        if isinstance(data, list):
            tokens = data
        elif isinstance(data, dict) and "tokens" in data:
            tokens = data["tokens"]
        else:
            tokens = []
        return cls(tokens)

    @classmethod
    def from_tokens(cls, tokens: Sequence[str]) -> "TokenPool":
        return cls(tokens)

    @property
    def available_count(self) -> int:
        with self._lock:
            return len(self._available)

    @property
    def total_count(self) -> int:
        with self._lock:
            return len(self._available) + len(self._claimed)

    def add_tokens(self, tokens: Sequence[str]) -> None:
        with self._lock:
            self._available.extend(tokens)

    def claim_token(self, public_key_hex: str) -> tuple[str, TokenClaims]:
        with self._lock:
            while self._available:
                tok = self._available.pop(0)
                try:
                    claims = verify_agent_token(tok, public_key_hex)
                except Exception:
                    continue  # skip invalid / expired token in pool

                if claims.jti in self._retired:
                    continue  # burned token

                if self.is_revoked is not None and self.is_revoked(claims.jti):
                    self._retired.add(claims.jti)
                    continue  # revoked in an earlier session and still on disk

                self._claimed[claims.jti] = tok
                return tok, claims

            raise PoolExhausted("all tokens in pool are currently in use or exhausted")

    def retire_token(self, jti: str) -> None:
        with self._lock:
            self._retired.add(jti)
            self._claimed.pop(jti, None)

    def release_token(self, jti: str) -> None:
        with self._lock:
            if jti in self._retired:
                return  # revoked tokens are never recycled
            tok = self._claimed.pop(jti, None)
            if tok is not None:
                self._available.append(tok)
