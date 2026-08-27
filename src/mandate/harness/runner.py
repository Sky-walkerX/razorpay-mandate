"""Run one corpus item against one arm. Fresh gateway, fresh ledger, fresh log.

Containment is measured at the money boundary: what the downstream actually recorded.
The agent's own account of what it did is not evidence.
"""
from datetime import timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from mandate.adapters.direct import DirectClient
from mandate.downstream.fake import FakeDownstream
from mandate.gateway.audit import AuditChainBroken, AuditLog
from mandate.gateway.core import Gateway, Mode
from mandate.gateway.idem import Ledger
from mandate.gateway.resolve import Resolver
from mandate.gateway.state import Verdict
from mandate.harness import oracle
from mandate.harness.agent import ShoppingAgent
from mandate.harness.corpus import CorpusItem
from mandate.money import Paise
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Policy

IST = timezone(timedelta(hours=5, minutes=30))

CURATED = {
    "toor dal": "grocery",
    "basmati rice": "grocery",
    "amul milk": "grocery",
    "atta": "grocery",
    "cooking oil": "grocery",
    "potato chips": "snacks",
    "instant noodles": "snacks",
    "dark chocolate": "snacks",
    "craft lager": "alcohol",
    "red wine": "alcohol",
    "cigarettes": "tobacco",
    "dish soap": "household",
}


class Arm(BaseModel):
    name: str
    mode: Mode
    compromised: bool


ARMS: dict[str, Arm] = {
    "baseline": Arm(name="baseline", mode=Mode.OBSERVE, compromised=False),
    "compromised": Arm(name="compromised", mode=Mode.OBSERVE, compromised=True),
    "enforce": Arm(name="enforce", mode=Mode.ENFORCE, compromised=False),
    "enforce_compromised": Arm(
        name="enforce_compromised", mode=Mode.ENFORCE, compromised=True
    ),
}


class ItemResult(BaseModel):
    item_id: str
    family_id: str
    arm: str
    is_attack: bool
    held_out: bool
    contained: bool
    spent: Paise
    executed_amount: Paise = Paise(0)
    oracle_reason: str = ""
    model: str = "unknown"
    verdicts: list[str] = []
    escalated: bool = False
    error: str | None = None


def _budget_of(policy: Policy) -> int:
    return int(policy.constraints.get(C.BUDGET_TOTAL, {}).get("max", 0))


FLASH_MODELS = ["qwen3.6-flash"]


def run_item(
    item: CorpusItem,
    arm: Arm,
    policy: Policy,
    model_factory,
    tmp_root: Path,
    model_name: str | None = None,
) -> ItemResult:
    root = Path(tmp_root) / arm.name / item.id.replace("#", "_").replace(".", "_")
    root.mkdir(parents=True, exist_ok=True)
    mut = item.mutation
    down = FakeDownstream(amount_multiplier=mut.catalog.amount_multiplier)
    audit = AuditLog(root / "audit.jsonl")
    gw = Gateway(
        policy=policy,
        downstream=down,
        audit=audit,
        mode=arm.mode,
        ledger=Ledger(root / "ledger.jsonl"),
        resolver=Resolver(mut.catalog.merchant_names, CURATED, cache_path=root / "cats.json"),
    )
    now = policy.issued + timedelta(hours=1) + timedelta(seconds=mut.clock_offset_s)
    if mut.clock_offset_s:
        now = policy.expires + timedelta(seconds=mut.clock_offset_s)

    verdicts: list[str] = []
    error, final_model_name = None, "unknown"
    try:
        for _ in range(max(1, mut.repeat)):
            try:
                model = model_factory(
                    mut.catalog,
                    mut.intent,
                    arm.compromised,
                    root / "model_calls.jsonl",
                    model=model_name,
                )
            except TypeError:
                model = model_factory(
                    mut.catalog, mut.intent, arm.compromised, root / "model_calls.jsonl"
                )
            final_model_name = getattr(model, "model", model_name or "scripted")
            agent = ShoppingAgent(
                client=DirectClient(gw), catalog=mut.catalog, model=model, max_steps=5
            )
            trace = agent.run(mut.intent, now=now)
            verdicts += [str(d.verdict) for d in trace.decisions]
    except Exception as e:  # noqa: BLE001  # recorded, never swallowed
        error = f"{type(e).__name__}: {e}"

    spent = sum(int(o["amount"]) for o in down._orders.values())

    contained, reason, executed_amount = True, "", 0
    if error is None:
        try:
            # A corrupt log means we do not know what happened. That is an excluded
            # run, not a containment result, so it becomes an error like any other.
            audit.verify_chain()
            records = audit.records()
            executed_amount = sum(
                int(r.downstream["amount"]) for r in oracle.executed(records)
            )
            if item.is_attack:
                succeeded, reason = oracle.attack_succeeded(mut, records, policy)
                contained = not succeeded
            else:
                # Containment is not a question you can ask of a legitimate purchase.
                # score() judges these on whether the money moved at all.
                reason = "legitimate item; not judged for containment"
        except (AuditChainBroken, oracle.OracleCannotJudge, KeyError) as e:
            error = f"{type(e).__name__}: {e}"
            contained, reason = False, f"could not be judged: {error}"
    if error is not None and not reason:
        contained, reason = False, f"run failed before it could be judged: {error}"

    res = ItemResult(
        item_id=item.id,
        family_id=item.family_id,
        arm=arm.name,
        is_attack=item.is_attack,
        held_out=item.held_out,
        contained=contained,
        spent=Paise(spent),
        executed_amount=Paise(executed_amount),
        oracle_reason=reason,
        model=final_model_name,
        verdicts=verdicts,
        escalated=str(Verdict.UNKNOWN) in verdicts,
        error=error,
    )
    (root / "result.json").write_text(res.model_dump_json(indent=2))
    return res


def run_corpus(
    items: list[CorpusItem],
    arms: list[Arm],
    policy: Policy,
    model_factory,
    out_dir: Path,
    exclude_held_out: bool = True,
    held_out_only: bool = False,
    per_family: int | None = None,
    max_items: int | None = None,
    start_idx: int = 0,
) -> list[ItemResult]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    chosen = [
        i
        for i in items
        if (i.held_out if held_out_only else (not i.held_out or not exclude_held_out))
    ]
    if per_family is not None:
        from collections import defaultdict

        by_fam = defaultdict(list)
        for it in chosen:
            if len(by_fam[it.family_id]) < per_family:
                by_fam[it.family_id].append(it)
        chosen = [it for fam_items in by_fam.values() for it in fam_items]

    if start_idx > 0:
        chosen = chosen[start_idx:]
    if max_items is not None:
        chosen = chosen[:max_items]

    total = len(arms) * len(chosen)
    results = []
    chunk_size = max(1, (len(chosen) + len(FLASH_MODELS) - 1) // len(FLASH_MODELS))

    from rich.progress import (
        BarColumn,
        Progress,
        TaskProgressColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
    )

    with Progress(
        TextColumn("[bold cyan]{task.fields[current]}/{task.total}[/bold cyan]"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        TextColumn("{task.description}"),
    ) as progress:
        task = progress.add_task("[yellow]Evaluating[/yellow]", total=total, current=0)
        for arm in arms:
            for it_idx, it in enumerate(chosen):
                idx = len(results) + 1
                q = min(len(FLASH_MODELS) - 1, it_idx // chunk_size)
                import os

                model_for_item = os.environ.get("MANDATE_MODEL") or FLASH_MODELS[q]
                progress.update(
                    task,
                    current=idx,
                    description=f"[bold green]{arm.name}[/bold green] | [magenta]{model_for_item}[/magenta] | [cyan]{it.id}[/cyan]",
                )
                res = run_item(
                    it, arm, policy, model_factory, out_dir, model_name=model_for_item
                )
                results.append(res)
                progress.advance(task)
                status_icon = "🛡️ Contained" if res.contained else "⚠️ Violated"
                print(
                    f"[{idx}/{total} ({idx*100//total}%)] ({arm.name} | {model_for_item}) {it.id} -> {status_icon} (spent: {res.spent})",
                    flush=True,
                )

    (out_dir / "results.jsonl").write_text(
        "\n".join(r.model_dump_json() for r in results) + "\n"
    )
    return results
