"""Out-of-band human approval for actions above the AFA threshold.

RBI's Digital Payments E-mandate Framework, 2026 (21 April 2026) permits
recurring debits up to Rs 15,000 without an Additional Factor of Authentication
and requires AFA above it. That is the regulation this store exists to satisfy.

The security property that matters is what an approval is keyed on. It is keyed
on the canonical intent hash of the *resolved* action, never on an amount the
agent stated and never on a token the agent holds. So an approval granted for
four specific SKUs at their price-book prices does not authorise a different
basket that happens to cost the same. This is the same binding the capture
capability uses, for the same reason.

The agent cannot reach this store. Approvals arrive on the principal's channel,
which is a different endpoint with different auth. If the agent could grant its
own approval, `afa.required` would be decoration.
"""
import json
import threading
from datetime import UTC, datetime
from pathlib import Path


class ApprovalStore:
    def __init__(self, path: Path | str | None = None) -> None:
        # None means in memory. A real default path would have every test in the
        # suite appending to one file, which is the mistake `create_app` avoids.
        self.path = Path(path) if path is not None else None
        self._lock = threading.Lock()
        self._cache: dict[str, dict] = {}
        self._last_mtime: float = 0.0
        self._reload_if_changed()

    def _reload_if_changed(self) -> None:
        if self.path is None or not self.path.exists():
            return
        mtime = self.path.stat().st_mtime
        if mtime <= self._last_mtime:
            return
        fresh: dict[str, dict] = {}
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "intent" in rec:
                fresh[rec["intent"]] = rec
        self._cache = fresh
        self._last_mtime = mtime

    def is_approved(self, intent: str) -> bool:
        with self._lock:
            self._reload_if_changed()
            return intent in self._cache

    def approve(self, intent: str, approver: str = "principal", factor: str = "otp") -> dict:
        """Record an AFA-validated approval for one exact resolved intent."""
        entry = {
            "intent": intent,
            "approver": approver,
            "factor": factor,
            "approved_at": datetime.now(UTC).isoformat(),
        }
        with self._lock:
            if self.path is not None:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a") as fh:
                    fh.write(json.dumps(entry) + "\n")
                self._last_mtime = self.path.stat().st_mtime
            self._cache[entry["intent"]] = entry
        return entry

    def get(self, intent: str) -> dict | None:
        with self._lock:
            self._reload_if_changed()
            return self._cache.get(intent)
