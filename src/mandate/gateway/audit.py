"""Append-only, hash-chained decision log with RFC 6962 Merkle tree capabilities."""
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mandate.gateway.action import Action
from mandate.gateway.lattice import combine
from mandate.gateway.merkle import (
    consistency_proof,
    inclusion_proof,
    merkle_tree_hash,
)
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
        self._cached_records: list[AuditRecord] | None = None

    def _load_cache(self) -> list[AuditRecord]:
        if self._cached_records is None:
            if not self.path.exists():
                self._cached_records = []
            else:
                self._cached_records = [
                    AuditRecord(**json.loads(ln))
                    for ln in self.path.read_text().splitlines()
                    if ln.strip()
                ]
        return self._cached_records

    def records(self) -> list[AuditRecord]:
        return list(self._load_cache())

    def append(self, *, ts: datetime, mandate_id: str, policy_hash: str, idem_key: str,
               action: Action, verdict: Verdict, clauses: list[ClauseResult],
               downstream: dict | None) -> AuditRecord:
        existing = self._load_cache()
        seq = len(existing) + 1
        prev = existing[-1].record_hash if existing else GENESIS
        rec_model = AuditRecord(
            seq=seq,
            ts=ts,
            mandate_id=mandate_id,
            policy_hash=policy_hash,
            idem_key=idem_key,
            action=action,
            verdict=verdict,
            clauses=clauses,
            downstream=downstream,
            prev_hash=prev,
            record_hash="",
        )
        body = rec_model.model_dump(mode="json", exclude={"record_hash"})
        h = _hash_body(body)
        rec = rec_model.model_copy(update={"record_hash": h})
        with self.path.open("a") as fh:
            fh.write(rec.model_dump_json() + "\n")
        existing.append(rec)
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

    def leaf_hashes(self) -> list[str]:
        return [r.record_hash for r in self.records()]

    def get_merkle_root(self) -> str:
        leaves = self.leaf_hashes()
        return merkle_tree_hash(leaves)

    def get_inclusion_proof(self, seq: int) -> dict[str, Any]:
        leaves = self.leaf_hashes()
        index = seq - 1
        proof = inclusion_proof(index, leaves)
        return {
            "seq": seq,
            "leaf_record_hash": leaves[index],
            "tree_size": len(leaves),
            "root": merkle_tree_hash(leaves),
            "proof": proof,
        }

    def get_consistency_proof(self, from_count: int, to_count: int) -> dict[str, Any]:
        leaves = self.leaf_hashes()
        proof = consistency_proof(from_count, to_count, leaves)
        return {
            "from_count": from_count,
            "to_count": to_count,
            "from_root": merkle_tree_hash(leaves[:from_count]),
            "to_root": merkle_tree_hash(leaves[:to_count]),
            "proof": proof,
        }
