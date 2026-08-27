"""Append-only, hash-chained decision log. One record per proposed action, any verdict."""
import hashlib
import json
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel

from mandate.gateway.action import Action
from mandate.gateway.lattice import combine
from mandate.gateway.state import ClauseResult, Verdict

GENESIS = "sha256:" + "0" * 64


class AuditChainBroken(Exception):
    """A record was edited or removed after it was written."""


class AuditRecord(BaseModel):
    seq: int
    ts: datetime
    mandate_id: str
    policy_hash: str
    idem_key: str
    action: Action
    verdict: Verdict
    clauses: list[ClauseResult]
    downstream: dict | None = None
    prev_hash: str
    record_hash: str


def _hash_body(body: dict) -> str:
    return "sha256:" + hashlib.sha256(
        json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


def replay_verdict(rec: AuditRecord) -> Verdict:
    """Re-derive the verdict from stored clause results. No re-execution."""
    return combine(rec.clauses)


class AuditLog:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def records(self) -> list[AuditRecord]:
        if not self.path.exists():
            return []
        return [AuditRecord(**json.loads(ln))
                for ln in self.path.read_text().splitlines() if ln.strip()]

    def append(self, *, ts: datetime, mandate_id: str, policy_hash: str, idem_key: str,
               action: Action, verdict: Verdict, clauses: list[ClauseResult],
               downstream: dict | None) -> AuditRecord:
        existing = self.records()
        seq = len(existing) + 1
        prev = existing[-1].record_hash if existing else GENESIS
        body = {"seq": seq, "ts": ts.isoformat(), "mandate_id": mandate_id,
                "policy_hash": policy_hash, "idem_key": idem_key,
                "action": action.model_dump(mode="json"), "verdict": str(verdict),
                "clauses": [c.model_dump(mode="json") for c in clauses],
                "downstream": downstream, "prev_hash": prev}
        rec = AuditRecord(**body, record_hash=_hash_body(body))
        with self.path.open("a") as fh:
            fh.write(rec.model_dump_json() + "\n")
        return rec

    def verify_chain(self) -> None:
        prev = GENESIS
        for i, rec in enumerate(self.records(), start=1):
            if rec.seq != i:
                raise AuditChainBroken(f"expected seq {i}, found {rec.seq}")
            if rec.prev_hash != prev:
                raise AuditChainBroken(f"seq {rec.seq} does not link to its predecessor")
            body = rec.model_dump(mode="json", exclude={"record_hash"})
            if _hash_body(body) != rec.record_hash:
                raise AuditChainBroken(f"seq {rec.seq} content does not match its hash")
            prev = rec.record_hash
