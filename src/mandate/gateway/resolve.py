"""Resolution to canonical ids. Anything that does not resolve returns None,
which becomes UNKNOWN at the constraint and escalates to a human.

Deliberately strict. Fuzzy matching an attacker's merchant onto an allowed one is
the worst available outcome, so near-misses resolve to None rather than to a guess.
"""
import json
import re
import unicodedata
from pathlib import Path

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


class CategoryResolver:
    """Curated map first, then cache, then unknown.

    No model call in the hot path. A miss returns None (UNKNOWN, which escalates)
    and is queued for offline classification. The first encounter with a novel item
    interrupts a human; that is intended, and it is counted in the false-block rate.
    """

    def __init__(self, curated: dict[str, str], cache_path: Path | None = None) -> None:
        self._curated = {normalise(k): v for k, v in curated.items()}
        self._cache_path = Path(cache_path) if cache_path else None
        self._cache: dict[str, str] = {}
        if self._cache_path and self._cache_path.exists():
            self._cache = json.loads(self._cache_path.read_text())
        self._pending: list[tuple[str, str]] = []

    def resolve(self, sku: str, title: str) -> str | None:
        if sku in self._cache:
            return self._cache[sku]
        n = normalise(title)
        for key, cat in self._curated.items():
            if key in n:
                return cat
        if (sku, title) not in self._pending:
            self._pending.append((sku, title))
        return None

    def pending_classification(self) -> list[tuple[str, str]]:
        return list(self._pending)

    def learn(self, sku: str, category: str) -> None:
        self._cache[sku] = category
        self._pending = [(s, t) for (s, t) in self._pending if s != sku]
        if self._cache_path:
            self._cache_path.parent.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(json.dumps(self._cache, indent=2, sort_keys=True))


class Resolver:
    """What Gateway expects: .merchant(raw) and .category(sku, title)."""

    def __init__(self, merchants: dict[str, str], categories: dict[str, str],
                 cache_path: Path | None = None) -> None:
        self._m = MerchantResolver(merchants)
        self._c = CategoryResolver(categories, cache_path)

    def merchant(self, raw: str) -> str | None:
        return self._m.resolve(raw)

    def category(self, sku: str, title: str) -> str | None:
        return self._c.resolve(sku, title)
