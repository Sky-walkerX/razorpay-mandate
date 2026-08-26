"""Resolution to canonical ids. Anything that does not resolve returns None,
which becomes UNKNOWN at the constraint and escalates to a human.

Deliberately strict. Fuzzy matching an attacker's merchant onto an allowed one is
the worst available outcome, so near-misses resolve to None rather than to a guess.
"""
import re
import unicodedata

_WS = re.compile(r"[\s_\-]+")


def normalise(s: str) -> str:
    """Casefold and collapse separators. Does NOT fold confusables to ASCII."""
    s = unicodedata.normalize("NFKC", s).casefold().strip()
    return _WS.sub("", s)


class MerchantResolver:
    def __init__(self, known: dict[str, str]) -> None:
        self._by_norm: dict[str, str] = {}
        for mid, display in known.items():
            self._by_norm[normalise(mid)] = mid
            self._by_norm[normalise(display)] = mid

    def resolve(self, raw: str) -> str | None:
        return self._by_norm.get(normalise(raw))
