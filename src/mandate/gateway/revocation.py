"""Revocation list management for agent tokens and mandates.

The human revokes an agent token mid-flight via `mandate revoke <jti>`.
The Gateway verifies the jti is not in the revocation list on every call.
"""
import json
import threading
from datetime import UTC, datetime
from pathlib import Path


class RevocationList:
    def __init__(self, path: Path | str = Path("revocations.jsonl")) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self._cache: set[str] = set()
        self._last_mtime: float = 0.0
        self._reload_if_changed()

    def _reload_if_changed(self) -> None:
        if not self.path.exists():
            return
        mtime = self.path.stat().st_mtime
        if mtime > self._last_mtime:
            new_revoked = set()
            for line in self.path.read_text().splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    if "target" in rec:
                        new_revoked.add(rec["target"])
                except json.JSONDecodeError:
                    continue
            self._cache = new_revoked
            self._last_mtime = mtime

    def is_revoked(self, target: str) -> bool:
        with self._lock:
            self._reload_if_changed()
            return target in self._cache

    def revoke(self, target: str, reason: str = "manual_revocation") -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            entry = {
                "target": target,
                "reason": reason,
                "revoked_at": datetime.now(UTC).isoformat(),
            }
            with self.path.open("a") as fh:
                fh.write(json.dumps(entry) + "\n")
            self._cache.add(target)
            if self.path.exists():
                self._last_mtime = self.path.stat().st_mtime
