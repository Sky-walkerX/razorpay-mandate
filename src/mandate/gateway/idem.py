"""Idempotency ledger. Three states, and PENDING is the dangerous one.

A timeout means we sent the request and never learned the outcome. Re-executing
double charges; blocking forever is unusable. So PENDING is held and reconciled.
"""
import json
from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel

from mandate.gateway.action import Action
from mandate.gateway.state import AccumulatedState
from mandate.money import Paise


class EntryState(StrEnum):
    PENDING = "PENDING"
    COMMITTED = "COMMITTED"
    FAILED = "FAILED"


class LedgerEntry(BaseModel):
    idem_key: str
    state: EntryState
    amount: Paise
    skus: list[str]
    downstream: dict | None = None
    reason: str = ""
    created_at: datetime


import threading


class Ledger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _entries(self) -> dict[str, LedgerEntry]:
        out: dict[str, LedgerEntry] = {}
        if self.path.exists():
            for ln in self.path.read_text().splitlines():
                if ln.strip():
                    e = LedgerEntry(**json.loads(ln))
                    out[e.idem_key] = e          # last write wins
                    try:
                        e = LedgerEntry(**json.loads(ln))
                        out[e.idem_key] = e          # last write wins
                    except json.JSONDecodeError:
                        continue
        return out

    def _write(self, e: LedgerEntry) -> LedgerEntry:
        with self.path.open("a") as fh:
            fh.write(e.model_dump_json() + "\n")
        return e

    def get(self, idem_key: str) -> LedgerEntry | None:
        return self._entries().get(idem_key)
        with self._lock:
            return self._entries().get(idem_key)

    def open_pending(self, idem_key: str, action: Action, now: datetime) -> LedgerEntry:
        return self._write(LedgerEntry(
            idem_key=idem_key, state=EntryState.PENDING, amount=action.amount,
            skus=[i.sku for i in action.items], created_at=now))
        with self._lock:
            return self._write(LedgerEntry(
                idem_key=idem_key, state=EntryState.PENDING, amount=action.amount,
                skus=[i.sku for i in action.items], created_at=now))

    def _transition(self, idem_key: str, state: EntryState, **kw) -> LedgerEntry:
        cur = self.get(idem_key)
        cur = self._entries().get(idem_key)
        if cur is None:
            raise KeyError(f"no ledger entry for {idem_key}")
        return self._write(cur.model_copy(update={"state": state, **kw}))

    def mark_committed(self, idem_key: str, downstream: dict | None) -> LedgerEntry:
        return self._transition(idem_key, EntryState.COMMITTED, downstream=downstream)
        with self._lock:
            return self._transition(idem_key, EntryState.COMMITTED, downstream=downstream)

    def mark_failed(self, idem_key: str, reason: str) -> LedgerEntry:
        return self._transition(idem_key, EntryState.FAILED, reason=reason)
        with self._lock:
            return self._transition(idem_key, EntryState.FAILED, reason=reason)

    def pending(self) -> list[LedgerEntry]:
        return [e for e in self._entries().values() if e.state is EntryState.PENDING]
        with self._lock:
            return [e for e in self._entries().values() if e.state is EntryState.PENDING]

    def state(self) -> AccumulatedState:
        es = list(self._entries().values())
        committed = sum(int(e.amount) for e in es if e.state is EntryState.COMMITTED)
        pending = sum(int(e.amount) for e in es if e.state is EntryState.PENDING)
        live = [e for e in es if e.state is not EntryState.FAILED]
        return AccumulatedState(
            committed=Paise(committed), pending=Paise(pending),
            action_count=len(live),
            recent_skus={s for e in live for s in e.skus},
            actions_in_window=len(live))
        with self._lock:
            es = list(self._entries().values())
            committed = sum(int(e.amount) for e in es if e.state is EntryState.COMMITTED)
            pending = sum(int(e.amount) for e in es if e.state is EntryState.PENDING)
            live = [e for e in es if e.state is not EntryState.FAILED]
            return AccumulatedState(
                committed=Paise(committed), pending=Paise(pending),
                action_count=len(live),
                recent_skus={s for e in live for s in e.skus},
                actions_in_window=len(live))

