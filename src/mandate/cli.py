import hashlib
import json
import os
from datetime import datetime, timedelta
from datetime import UTC, datetime, timedelta
from pathlib import Path

import typer
from dotenv import load_dotenv

from mandate.compiler.compile import IST, compile_intent
from mandate.compiler.readback import render, sign
from mandate.downstream.razorpay import RazorpayDownstream
from mandate.harness.aggregate import write_jsonl
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

    providers: dict[tuple, object] = {}

    def factory(catalog, intent, compromised, call_log, model: str | None = None):
        key = (seed, model)
        if key not in providers:
            kw = {"seed": seed}
            if model:
                kw["model"] = model
            providers[key] = provider_for(**kw)
        return AgentModel(
            catalog,
            intent,
            provider=providers[key],
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
    legit_n: int | None = None,
    max_items: int | None = None,
    start_idx: int = 0,
    model: str = DEFAULT_MODEL,
    workers: int = 5,
    resume: bool = True,
    run_id: str | None = None,
) -> None:
    """Run the corpus over every arm and write results, scores and a results table."""
    load_dotenv()
    scripted = bool(os.environ.get("MANDATE_FAKE_MODEL"))
    if scripted and not allow_scripted:
        raise typer.BadParameter(
            "MANDATE_FAKE_MODEL is set. A scripted run does not measure anything and "
            "must never be written to results/. Unset it, or pass --allow-scripted "
            "and expect the output in a -scripted directory."
        )
    if scripted:
        out = out.parent / f"{out.name}-scripted"
        typer.echo(f"scripted run: writing to {out} and skipping scoring")

    if not scripted:
        try:
            preflight_model(model)
        except Exception as e:
            raise typer.BadParameter(f"model {model!r} is not reachable: {e}") from e

    chosen = [ARMS[a.strip()] for a in arms.split(",") if a.strip()]
    items = load_corpus(corpus)
    pol = load_policy(policy)

    from mandate.harness.corpus import corpus_hash as _corpus_hash

    chash = _corpus_hash(items)
    if run_id is None:
        run_id = "run_" + hashlib.sha256(
            f"{seed}:{model}:{chash}:{pol.mandate_id}:all".encode()
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
        legit_n=legit_n,
        max_items=max_items,
        start_idx=start_idx,
        model=model,
        run_id=run_id,
        corpus_hash=chash,
        policy_id=pol.mandate_id,
        workers=workers,
        resume=resume,
    )

    if scripted:
        write_jsonl(results, out / "results.jsonl")
        return

    aggregate(out=out, run_id=run_id, seed=seed, held_out=held_out)


@app.command()
def aggregate(
    out: Path = Path("results"),
    run_id: str | None = None,
    seed: int = 20260901,
    held_out: bool = False,
) -> None:
    """Rebuild results.jsonl, scores.json and the table from per-item results."""
    from mandate.harness.aggregate import collect, select_run

    rows = select_run(collect(out), run_id)
    if not rows:
        raise typer.BadParameter(f"no results under {out} for run_id={run_id!r}")
    ok, bad = partition_errors(rows)
    if bad:
        typer.echo(f"excluded {len(bad)} failed runs:")
        for r in bad[:10]:
            typer.echo(f"  {r.item_id} ({r.arm}): {r.error}")
    scores = score(ok, seed=seed)
    label = "held-out families" if held_out else "development families"
    model = min({r.model for r in ok}) if ok else "unknown"
    write_jsonl(rows, out / "results.jsonl")
    (out / "scores.json").write_text(
        json.dumps({k: v.model_dump() for k, v in scores.items()}, indent=2)
    )
    (out / "README-results.md").write_text(
        f"Seed {seed}. Model {model}. Run {run_id or (ok[0].run_id if ok else '?')}. "
        f"{len(ok)} scored runs over {label}, {len(bad)} excluded as failed.\n\n"
        f"{render_table(scores)}\n"
    )
    typer.echo(render_table(scores))


@app.command()
def demo(
    seed: int = 20260901,
    family: str = "budget.salami",
    replay: bool = typer.Option(False, "--replay", help="Replay recorded model calls rather than calling Vertex AI."),
    corpus: Path = Path("corpus/corpus.json"),
    policy: Path = Path("policies/policy.yaml"),
) -> None:
    """Run one attack through both arms and print the side-by-side.

    Defaults to `budget.salami`, the family the measurement says the model does
    not resist on its own: 0% containment unenforced, 100% enforced. Prompt
    injection is the attack everyone expects and it is not where a frontier
    model leaks money. Use `--family injection.description` for that one.
    """
    load_dotenv()
    from mandate.harness.demo import run_demo

    item = next(i for i in load_corpus(corpus) if i.family_id == family)
    out = run_demo(item, load_policy(policy), _model_factory(seed), Path("results/demo"))
    if replay:
        from mandate.harness.agent_model import make_replay_factory

        factory = make_replay_factory()
    else:
        factory = _model_factory(seed)
    out = run_demo(item, load_policy(policy), factory, Path("results/demo"))
    for arm in ("compromised", "enforce_compromised"):
        r = out[arm]
        typer.echo(f"\n=== {arm.upper()} ===")
        typer.echo(f"executed: {fmt(r.executed_amount)}   contained: {r.contained}")
        typer.echo(f"why: {r.oracle_reason}")
        typer.echo(f"blocking clause: {r.blocking_clause or '-'}")
        for ln in r.audit_lines:
            typer.echo("  " + ln)


@app.command("demo-failure")
def demo_failure(
    policy: Path = Path("policies/policy.yaml"),
    out: Path = Path("results/demo-failure"),
) -> None:
    """One failure handled gracefully: a lost response, then a retry, then reconciliation.

    Needs no model and no network. The behaviour is deterministic gateway code.
    """
    from mandate.harness.failure_demo import run_failure_demo

    pol = load_policy(policy)
    r = run_failure_demo(pol, out)

    typer.echo("\n=== THE MECHANICAL FAILURE ===")
    typer.echo("create_order reaches the rail. The rail writes the order. The response\n"
               "never comes back. The agent knows only that it got no answer.\n")
    for s in r.steps:
        typer.echo(f"  {s.n}. {s.what}")
        typer.echo(f"     verdict={s.verdict}  clause={s.clause}  executed={s.executed}")
        typer.echo(f"     {s.detail}")
    typer.echo("\n=== OUTCOME ===")
    typer.echo(f"  orders downstream : {r.orders_downstream}")
    typer.echo(f"  charged           : {fmt(r.charged)}")
    typer.echo(f"  budget consumed   : {fmt(r.budget_consumed)}")
    typer.echo(f"  audit chain       : {'intact' if r.chain_intact else 'BROKEN'} "
               f"({r.audit_records} records)")
    typer.echo("\n=== THE SAME TWO CALLS WITH NO LEDGER ===")
    typer.echo(f"  orders downstream : {r.naive_orders}")
    typer.echo(f"  charged           : {fmt(r.naive_charged)}")
    typer.echo(f"\nOne intent. {fmt(r.charged)} with the ledger, "
               f"{fmt(r.naive_charged)} without.")


@app.command("export")
def export(
    fmt_: str = typer.Option("diff", "--format",
                             help="diff | ap2 | reserve-pay"),
    policy: Path = Path("policies/policy.yaml"),
) -> None:
    """Project the signed policy onto AP2 and UPI Reserve Pay, and show what is lost."""
    import json as _json

    from mandate.policy.canonical import policy_hash
    from mandate.policy.rails import (
        diff,
        money_at_risk,
        to_ap2_intent_mandate,
        to_ap2_payment_constraints,
        to_reserve_pay,
    )

    pol = load_policy(policy)
    if fmt_ == "ap2":
        typer.echo(_json.dumps({
            "intent_mandate": to_ap2_intent_mandate(pol),
            "payment_mandate_constraints": to_ap2_payment_constraints(pol),
        }, indent=2))
        return
    if fmt_ in ("reserve-pay", "reserve_pay"):
        typer.echo(_json.dumps(to_reserve_pay(pol), indent=2))
        return
    if fmt_ != "diff":
        raise typer.BadParameter("--format must be diff, ap2 or reserve-pay")

    d = diff(pol, policy_hash(pol))
    typer.echo(f"\npolicy {d.mandate_id}  {d.policy_hash[:23]}")
    typer.echo(f'"{pol.source_text}"\n')
    typer.echo(f"  {'clause':26}{'stated':>8}{'AP2':>8}{'ReservePay':>13}")
    typer.echo("  " + "-" * 55)
    for f in d.fates:
        typer.echo(f"  {f.clause:26}{'yes' if f.stated_by_user else 'inferred':>8}"
                   f"{f.ap2:>8}{f.reserve_pay:>13}")
    typer.echo("  " + "-" * 55)
    typer.echo(f"  {'held':26}{d.total_clauses:>8}{d.ap2_held:>8}{d.reserve_pay_held:>13}")
    typer.echo(f"  {'lost':26}{0:>8}{d.ap2_lost:>8}{d.reserve_pay_lost:>13}")
    typer.echo("\nwhat neither rail can hold:")
    for f in d.fates:
        if f.ap2 != "ap2" and f.reserve_pay != "rail":
            typer.echo(f"  {f.clause:26}{f.ap2_note}")
    typer.echo(f"\nUnder a Reserve Pay block alone, {fmt(money_at_risk(pol))} is spendable on "
               f"anything\nthe payee sells, including everything the clauses above refuse.")


@app.command("keygen")
def keygen(
    out_dir: Path = Path(".mandate/keys"),
) -> None:
    """Generate an Ed25519 asymmetric keypair for the offline policy issuer."""
    import os

    from mandate.policy.crypto import generate_keypair

    out_dir.mkdir(parents=True, exist_ok=True)
    priv_hex, pub_hex = generate_keypair()

    priv_path = out_dir / "issuer_private.key"
    pub_path = out_dir / "issuer_public.key"

    priv_path.write_text(priv_hex + "\n")
    os.chmod(priv_path, 0o600)
    pub_path.write_text(pub_hex + "\n")

    typer.echo("Generated Ed25519 issuer keypair:")
    typer.echo(f"  private key (keep secret): {priv_path} (mode 0600)")
    typer.echo(f"  public key  (distribute) : {pub_path}")
    typer.echo(f"  public key hex           : {pub_hex}")


from typing import Annotated


@app.command("sign")
def sign_policy_cmd(
    policy: Annotated[Path, typer.Argument()] = Path("policies/policy.yaml"),
    key_file: Annotated[Path, typer.Option("--key-file")] = Path(".mandate/keys/issuer_private.key"),
) -> None:
    """Sign a policy.yaml file with the issuer Ed25519 private key."""
    from mandate.policy.loader import dump as dump_policy

    if not key_file.exists():
        raise typer.BadParameter(f"Key file {key_file} not found. Run `mandate keygen` first.")
    priv_key_hex = key_file.read_text().strip()
    pol = load_policy(policy)
    dump_policy(pol, policy, private_key_hex=priv_key_hex)
    typer.echo(f"Successfully signed {policy} with Ed25519 key from {key_file}")


@app.command("issue-token")
def issue_token_cmd(
    mandate_id: Annotated[str, typer.Argument()] = "mnd_groceries_01",
    key_file: Annotated[Path, typer.Option("--key-file")] = Path(".mandate/keys/issuer_private.key"),
    expires: Annotated[str | None, typer.Option("--expires")] = None,
    jti: Annotated[str | None, typer.Option("--jti")] = None,
) -> None:
    """Mint a signed bearer token bound to a mandate_id."""
    from datetime import datetime, timedelta

    from mandate.gateway.tokens import mint_agent_token

    if not key_file.exists():
        raise typer.BadParameter(f"Key file {key_file} not found. Run `mandate keygen` first.")
    priv_key_hex = key_file.read_text().strip()
    if expires is None:
        expires = (datetime.now(UTC) + timedelta(hours=24)).isoformat()

    tok = mint_agent_token(
        mandate_id=mandate_id,
        private_key_hex=priv_key_hex,
        expires_iso=expires,
        jti=jti,
    )
    typer.echo(tok)


@app.command("revoke")
def revoke_cmd(
    target: Annotated[str, typer.Argument(help="Token jti or mandate_id to revoke")],
    reason: Annotated[str, typer.Option("--reason")] = "manual_revocation",
    revocations_file: Annotated[Path, typer.Option("--file")] = Path("revocations.jsonl"),
) -> None:
    """Revoke an agent token jti or mandate_id."""
    from mandate.gateway.revocation import RevocationList

    rlist = RevocationList(revocations_file)
    rlist.revoke(target, reason=reason)
    typer.echo(f"Revoked {target!r} in {revocations_file} (reason: {reason})")


@app.command("serve")
def serve_cmd(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8000,
    policy: Annotated[Path, typer.Option("--policy")] = Path("policies/policy.yaml"),
    public_key: Annotated[Path, typer.Option("--public-key")] = Path(".mandate/keys/issuer_public.key"),
    revocations: Annotated[Path, typer.Option("--revocations")] = Path("revocations.jsonl"),
) -> None:
    """Run the standalone Mandate Gateway daemon process."""
    import uvicorn

    from mandate.service.server import create_app

    typer.echo(f"Starting Mandate Gateway Daemon on http://{host}:{port}")
    typer.echo(f"  Policy     : {policy}")
    typer.echo(f"  Public Key : {public_key}")
    typer.echo(f"  Revocations: {revocations}")

    app_instance = create_app(
        policy_path=policy,
        public_key_path=public_key if public_key.exists() else None,
        revocations_path=revocations,
    )
    uvicorn.run(app_instance, host=host, port=port, log_level="info")


@app.command("conformance")
def conformance_cmd(
    out_dir: Annotated[Path, typer.Option("--out")] = Path("results-conformance"),
) -> None:

    """Run the 8-Attack Protocol Conformance Test Suite with Witnesses.

    Every attack runs against both an unhardened gateway (the witness) and the
    hardened gateway. Reports exact counts (BLOCKED / ESCAPED / VACUOUS).
    """
    import json as _json

    from mandate.conformance.suite import run_conformance_suite

    typer.echo("Running Mandate Protocol Conformance Suite (8 hostile attacks)...\n")
    results = run_conformance_suite()

    out_dir.mkdir(parents=True, exist_ok=True)
    report_rows = []

    typer.echo(f"  {'Attack ID':24}{'Witness':>12}{'Hardened':>12}{'Outcome':>12}  Details")
    typer.echo("  " + "-" * 75)

    blocked_cnt, escaped_cnt, vacuous_cnt = 0, 0, 0

    for r in results:
        wit_str = "executed" if r.witness_executed else "failed"
        hard_str = "executed" if r.hardened_executed else "denied"
        out_str = r.outcome.value

        if r.outcome.value == "BLOCKED":
            blocked_cnt += 1
        elif r.outcome.value == "ESCAPED":
            escaped_cnt += 1
        else:
            vacuous_cnt += 1

        typer.echo(f"  {r.attack_id:24}{wit_str:>12}{hard_str:>12}{out_str:>12}  {r.detail}")
        report_rows.append({
            "attack_id": r.attack_id,
            "outcome": r.outcome.value,
            "witness_executed": r.witness_executed,
            "hardened_executed": r.hardened_executed,
            "detail": r.detail,
        })

    typer.echo("  " + "-" * 75)
    typer.echo(f"\nSummary: {len(results)} attacks, {blocked_cnt} blocked, {escaped_cnt} escaped, {vacuous_cnt} vacuous.\n")

    summary_file = out_dir / "conformance_results.json"
    summary_file.write_text(_json.dumps({"total": len(results), "blocked": blocked_cnt, "escaped": escaped_cnt, "vacuous": vacuous_cnt, "results": report_rows}, indent=2))
    typer.echo(f"Wrote conformance report to {summary_file}")



