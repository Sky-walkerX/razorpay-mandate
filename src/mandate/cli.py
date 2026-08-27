import hashlib
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import typer
from dotenv import load_dotenv

from mandate.compiler.compile import IST, compile_intent
from mandate.compiler.readback import render, sign
from mandate.downstream.razorpay import RazorpayDownstream
from mandate.harness.corpus import HELD_OUT, build_corpus, corpus_hash, load_corpus, save_corpus
from mandate.harness.runner import ARMS, DEFAULT_MODEL, run_corpus
from mandate.harness.score import partition_errors, render_table, score
from mandate.money import fmt, rupees
from mandate.policy.loader import load as load_policy

app = typer.Typer(no_args_is_help=True)


@app.command()
def check() -> None:
    """Prove end-to-end wiring: create one test-mode order and read it back."""
    load_dotenv()
    d = RazorpayDownstream(os.environ["RAZORPAY_KEY_ID"], os.environ["RAZORPAY_KEY_SECRET"])
    amount = rupees(1)
    order = d.create_order(amount, receipt="mandate_check_001", notes={"src": "mandate check"})
    typer.echo(f"created {order['id']} for {fmt(amount)}")
    back = d.fetch_order(order["id"])
    assert back["id"] == order["id"], "order did not read back"
    typer.echo(f"read back {back['id']} status={back['status']}")
    typer.echo("wiring OK")


corpus_app = typer.Typer()
app.add_typer(corpus_app, name="corpus")


@corpus_app.command("build")
def corpus_build(seed: int = 20260901, out: Path = Path("corpus/corpus.json")) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    items = build_corpus(seed=seed)
    save_corpus(items, out)
    attacks = sum(i.is_attack for i in items)
    typer.echo(f"{len(items)} items ({attacks} attacks, {len(items)-attacks} legitimate)")
    typer.echo(f"held out: {sorted(HELD_OUT)}")
    typer.echo(corpus_hash(items))


@app.command()
def compile(text: str, hours: int = 8, out: Path = Path("policies/policy.yaml")) -> None:
    """Compile an intent, show the read-back, and write the signed policy on approval."""
    load_dotenv()
    res = compile_intent(
        text,
        principal="user_local",
        agent="agt_shopper",
        expires=datetime.now(IST) + timedelta(hours=hours),
    )
    if res.policy is None:
        typer.echo("I could not compile this into a policy:\n")
        for q in res.questions:
            typer.echo(f'  "{q.phrase}" -> {q.why}')
        raise typer.Exit(code=1)
    typer.echo(render(res.policy))
    if not typer.confirm("\nSign this?"):
        raise typer.Exit(code=1)
    out.parent.mkdir(parents=True, exist_ok=True)
    typer.echo(f"signed -> {sign(res.policy, out)}")


def _model_factory(seed: int):
    if os.environ.get("MANDATE_FAKE_MODEL"):
        import random

        class _Scripted:
            """Buys the cheapest grocery item in whatever catalog it is handed.

            It reads the catalog on purpose. The previous stub hardcoded one sku
            and one merchant, which is why every attack scored as contained.
            """

            model = "scripted"

            def __init__(self, catalog, rng):
                self.catalog, self.rng, self.done = catalog, rng, False

            def next_call(self, _trace):
                if self.done:
                    return None
                self.done = True
                p = min(
                    (x for x in self.catalog.products if x.category == "grocery"),
                    key=lambda x: int(x.unit_price),
                )
                return (
                    "create_order",
                    {
                        "merchant": p.merchant,
                        "items": [
                            {
                                "sku": p.sku,
                                "title": p.title,
                                "qty": 1,
                                "unit_price": int(p.unit_price),
                            }
                        ],
                    },
                )

        return lambda catalog, intent, compromised, call_log: _Scripted(
            catalog, random.Random(seed)
        )

    from mandate.harness.agent_model import AgentModel
    from mandate.llm import provider_for

    def factory(catalog, intent, compromised, call_log, model: str | None = None):
        kw = {"seed": seed}
        if model:
            kw["model"] = model
        return AgentModel(
            catalog,
            intent,
            provider=provider_for(**kw),
            compromised=compromised,
            call_log=call_log,
        )

    return factory


def preflight_model(model: str) -> None:
    """One cheap call, so an unreachable model kills the run in seconds, not hours."""
    from mandate.adapters.direct import TOOLS
    from mandate.llm import provider_for

    provider_for(model=model).next_tool_call(
        "You are a shopping assistant. Use the create_order tool.",
        [{"role": "user", "text": "Buy 1 of sku=A1 'Rice' unit_price=5000 from merchant=BigBasket."}],
        TOOLS,
    )


@app.command()
def evaluate(
    seed: int = 20260901,
    arms: str = "baseline,compromised,enforce,enforce_compromised",
    corpus: Path = Path("corpus/corpus.json"),
    policy: Path = Path("policies/policy.yaml"),
    out: Path = Path("results"),
    held_out: bool = False,
    allow_scripted: bool = False,
    per_family: int | None = None,
    max_items: int | None = None,
    start_idx: int = 0,
    model: str = DEFAULT_MODEL,
) -> None:
    """Run the corpus over every arm and write results, scores and a results table."""
    load_dotenv()
    if os.environ.get("MANDATE_FAKE_MODEL") and not allow_scripted:
        raise typer.BadParameter(
            "MANDATE_FAKE_MODEL is set. A scripted run does not measure anything and "
            "must never be written to results/. Unset it, or pass --allow-scripted "
            "and expect every row tagged model=scripted."
        )

    if not os.environ.get("MANDATE_FAKE_MODEL"):
        try:
            preflight_model(model)
        except Exception as e:  # noqa: BLE001  # a dead model must stop the run here
            raise typer.BadParameter(f"model {model!r} is not reachable: {e}") from e

    chosen = [ARMS[a.strip()] for a in arms.split(",") if a.strip()]
    items = load_corpus(corpus)
    pol = load_policy(policy)

    from mandate.harness.corpus import corpus_hash as _corpus_hash

    chash = _corpus_hash(items)
    run_id = "run_" + hashlib.sha256(
        f"{seed}:{model}:{chash}:{pol.mandate_id}:{arms}".encode()
    ).hexdigest()[:12]
    typer.echo(f"run {run_id} | model {model} | corpus {chash[:19]}")

    results = run_corpus(
        items,
        chosen,
        pol,
        _model_factory(seed),
        out,
        exclude_held_out=not held_out,
        held_out_only=held_out,
        per_family=per_family,
        max_items=max_items,
        start_idx=start_idx,
        model=model,
        run_id=run_id,
        corpus_hash=chash,
        policy_id=pol.mandate_id,
    )

    ok, bad = partition_errors(results)
    if bad:
        typer.echo(f"excluded {len(bad)} failed runs:")
        for r in bad[:10]:
            typer.echo(f"  {r.item_id} ({r.arm}): {r.error}")
    scores = score(ok, seed=seed)
    label = "held-out families" if held_out else "development families"
    out.mkdir(parents=True, exist_ok=True)
    (out / "scores.json").write_text(
        json.dumps({k: v.model_dump() for k, v in scores.items()}, indent=2)
    )
    (out / "README-results.md").write_text(
        f"Seed {seed}. {len(ok)} scored runs over {label}, "
        f"{len(bad)} excluded as failed.\n\n{render_table(scores)}\n"
    )
    typer.echo(render_table(scores))


@app.command()
def demo(
    seed: int = 20260901,
    family: str = "injection.description",
    corpus: Path = Path("corpus/corpus.json"),
    policy: Path = Path("policies/policy.yaml"),
) -> None:
    """Run one attack through both arms and print the side-by-side."""
    load_dotenv()
    from mandate.harness.demo import run_demo

    item = next(i for i in load_corpus(corpus) if i.family_id == family)
    out = run_demo(item, load_policy(policy), _model_factory(seed), Path("results/demo"))
    for arm in ("compromised", "enforce_compromised"):
        r = out[arm]
        typer.echo(f"\n=== {arm.upper()} ===")
        typer.echo(f"executed: {fmt(r.executed_amount)}   contained: {r.contained}")
        typer.echo(f"why: {r.oracle_reason}")
        typer.echo(f"blocking clause: {r.blocking_clause or '-'}")
        for ln in r.audit_lines:
            typer.echo("  " + ln)
