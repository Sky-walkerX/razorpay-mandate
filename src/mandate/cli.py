import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import typer
from dotenv import load_dotenv

from mandate.compiler.compile import IST, compile_intent
from mandate.compiler.readback import render, sign
from mandate.downstream.razorpay import RazorpayDownstream
from mandate.gateway.core import Mode
from mandate.harness.corpus import HELD_OUT, build_corpus, corpus_hash, load_corpus, save_corpus
from mandate.harness.runner import run_corpus
from mandate.harness.score import render_table, score
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
    res = compile_intent(text, principal="user_local", agent="agt_shopper",
                         expires=datetime.now(IST) + timedelta(hours=hours))
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
    if os.environ.get("MANDATE_SCRIPTED"):
        class _Scripted:
            def __init__(self, calls):
                self.calls = list(calls)
                self.i = 0

            def next_call(self, _trace):
                if self.i >= len(self.calls):
                    return None
                c = self.calls[self.i]
                self.i += 1
                return c

        return lambda catalog, intent: _Scripted([
            (
                "create_order",
                {
                    "merchant": "zepto",
                    "items": [
                        {
                            "sku": "sku_0000",
                            "title": "Toor Dal",
                            "qty": 1,
                            "unit_price": int(rupees(300)),
                        }
                    ],
                },
            )
        ])
    from mandate.harness.claude_model import ClaudeModel
    return lambda catalog, intent: ClaudeModel(catalog, intent)


@app.command()
def evaluate(
    seed: int = 20260901,
    corpus: Path = Path("corpus/corpus.json"),
    policy: Path = Path("policies/policy.yaml"),
    out: Path = Path("results"),
    held_out: bool = False,
) -> None:
    """Run both arms over the corpus and write results, scores and a results table."""
    load_dotenv()
    items, pol = load_corpus(corpus), load_policy(policy)
    results = run_corpus(
        items,
        arms=[Mode.ENFORCE, Mode.OBSERVE],
        policy=pol,
        model_factory=_model_factory(seed),
        out_dir=out,
        exclude_held_out=not held_out,
        held_out_only=held_out,
    )
    scores = score(results, seed=seed)
    out.mkdir(parents=True, exist_ok=True)
    (out / "scores.json").write_text(
        json.dumps({k: v.model_dump() for k, v in scores.items()}, indent=2)
    )
    label = "held-out families" if held_out else "development families"
    (out / "README-results.md").write_text(
        f"Seed {seed}. {len(results)} runs over {label}.\n\n{render_table(scores)}\n"
    )
    typer.echo(render_table(scores))
