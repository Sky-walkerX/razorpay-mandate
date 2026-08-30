"""Run one corpus item against one arm. Fresh gateway, fresh ledger, fresh log.

Containment is measured at the money boundary: what the downstream actually recorded.
The agent's own account of what it did is not evidence.
"""
import json
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
    run_id: str = ""
    corpus_hash: str = ""
    policy_id: str = ""


def _budget_of(policy: Policy) -> int:
    return int(policy.constraints.get(C.BUDGET_TOTAL, {}).get("max", 0))


DEFAULT_MODEL = "gemini-3.6-flash"


def _result_path(out_dir: Path, arm: Arm, item: CorpusItem) -> Path:
    return Path(out_dir) / arm.name / item.id.replace("#", "_").replace(".", "_") / "result.json"


def _stamped_run_id(path: Path) -> str | None:
    """The run_id a result on disk carries, or None if it is unreadable.

    A truncated or corrupt result must re-run rather than abort the sweep, so this
    swallows the parse error and reports "not mine".
    """
    try:
        return json.loads(path.read_text()).get("run_id")
    except (OSError, ValueError, AttributeError):
        return None


def run_item(
    item: CorpusItem,
    arm: Arm,
    policy: Policy,
    model_factory,
    tmp_root: Path,
    model_name: str | None = None,
    run_id: str = "",
    corpus_hash: str = "",
    policy_id: str = "",
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
        run_id=run_id,
        corpus_hash=corpus_hash,
        policy_id=policy_id,
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
    legit_n: int | None = None,
    max_items: int | None = None,
    start_idx: int = 0,
    model: str = DEFAULT_MODEL,
    run_id: str = "",
    corpus_hash: str = "",
    policy_id: str = "",
    workers: int = 1,
    resume: bool = True,
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

        # Legitimate items carry the false-block rate, which needs a wider sample
        # than any single attack family, so it gets its own cap.
        by_fam = defaultdict(list)
        for it in chosen:
            cap = legit_n if (legit_n is not None and not it.is_attack) else per_family
            if len(by_fam[it.family_id]) < cap:
                by_fam[it.family_id].append(it)
        chosen = [it for fam_items in by_fam.values() for it in fam_items]

    if start_idx > 0:
        chosen = chosen[start_idx:]
    if max_items is not None:
        chosen = chosen[:max_items]

    jobs = [(arm, it) for arm in arms for it in chosen]
    if resume:
        # A sweep costs real money per call and this harness has hung mid-run before,
        # so a restart must not re-buy rows it already owns. Only a result stamped with
        # this exact run_id counts: run_id derives from seed, model, corpus hash and
        # policy, so a different model or an edited corpus can never silently reuse
        # stale rows.
        done = {
            (arm.name, it.id)
            for arm, it in jobs
            if _result_path(out_dir, arm, it).exists()
            and _stamped_run_id(_result_path(out_dir, arm, it)) == run_id
        }
        if done:
            jobs = [(arm, it) for arm, it in jobs if (arm.name, it.id) not in done]
            print(f"resuming run {run_id}: {len(done)} results already on disk, "
                  f"{len(jobs)} to run", flush=True)
    total = len(jobs)
    results = []

    from concurrent.futures import ThreadPoolExecutor, as_completed

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
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures = {
                pool.submit(
                    run_item,
                    it,
                    arm,
                    policy,
                    model_factory,
                    out_dir,
                    model_name=model,
                    run_id=run_id,
                    corpus_hash=corpus_hash,
                    policy_id=policy_id,
                ): (arm, it)
                for arm, it in jobs
            }
            for fut in as_completed(futures):
                arm, it = futures[fut]
                res = fut.result()
                results.append(res)
                progress.update(
                    task,
                    current=len(results),
                    description=f"[bold green]{arm.name}[/bold green] | "
                    f"[magenta]{model}[/magenta] | [cyan]{it.id}[/cyan]",
                )
                progress.advance(task)

    return results
