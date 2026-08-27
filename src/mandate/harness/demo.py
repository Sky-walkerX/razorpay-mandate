"""Same item, same model, both arms. The only difference is one boolean."""
from pathlib import Path

from pydantic import BaseModel

from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Mode
from mandate.harness.corpus import CorpusItem
from mandate.harness.runner import run_item
from mandate.money import Paise
from mandate.policy.models import Policy


class DemoResult(BaseModel):
    arm: str
    spent: Paise
    verdicts: list[str]
    blocking_clause: str | None = None
    audit_lines: list[str] = []


def run_demo(
    item: CorpusItem,
    policy: Policy,
    model_factory,
    tmp_root: Path,
) -> dict[str, DemoResult]:
    out: dict[str, DemoResult] = {}
    for arm in (Mode.ENFORCE, Mode.OBSERVE):
        r = run_item(item, arm, policy, model_factory, Path(tmp_root))
        root = Path(tmp_root) / arm.value / item.id.replace("#", "_").replace(".", "_")
        log = AuditLog(root / "audit.jsonl")
        log.verify_chain()
        blocking = None
        lines = []
        for rec in log.records():
            bad = [c for c in rec.clauses if c.result.value != "ALLOW"]
            if bad and blocking is None:
                blocking = str(bad[0].id)
            lines.append(
                f"seq={rec.seq} verdict={rec.verdict} "
                f"clause={bad[0].id if bad else '-'} hash={rec.record_hash[:14]}"
            )
        out[arm.value] = DemoResult(
            arm=arm.value,
            spent=r.spent,
            verdicts=r.verdicts,
            blocking_clause=blocking,
            audit_lines=lines,
        )
    return out
