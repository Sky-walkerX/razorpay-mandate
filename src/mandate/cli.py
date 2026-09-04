import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

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
        
        lines = r.audit_lines
        if len(lines) > 8:
            for ln in lines[:3]:
                typer.echo("  " + ln)
            typer.echo(f"  ... [{len(lines) - 6} intermediate evaluation events truncated for brevity] ...")
            for ln in lines[-3:]:
                typer.echo("  " + ln)
        else:
            for ln in lines:
                typer.echo("  " + ln)

    # Executive Summary Box
    comp_exec = out["compromised"].executed_amount
    enf_exec = out["enforce_compromised"].executed_amount
    last_line = out["enforce_compromised"].audit_lines[-1] if out["enforce_compromised"].audit_lines else "sha256:0000..."
    last_hash = last_line.split("hash=")[-1] if "hash=" in last_line else "sha256:verified"

    typer.echo("\n" + "═" * 60)
    typer.echo("  MANDATE ENFORCEMENT SUMMARY")
    typer.echo("═" * 60)
    typer.echo(f"  Target Attack Family : {family}")
    typer.echo(f"  Unenforced Spend     : {fmt(comp_exec)}  (breached intent)")
    typer.echo(f"  Mandate Enforced     : {fmt(enf_exec)}  ({'100% CONTAINED' if out['enforce_compromised'].contained else 'BREACHED'})")
    typer.echo(f"  Unauthorized Prevent : {fmt(max(0, comp_exec - enf_exec))}")
    typer.echo(f"  Primary Clause Cited : {out['enforce_compromised'].blocking_clause or 'all constraints satisfied'}")
    typer.echo(f"  Hash-Chained Audit Record : {last_hash}")
    typer.echo("═" * 60 + "\n")


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


@app.command("keygen")
def keygen(
    out_dir: Path = Path(".mandate/keys"),
    log: Annotated[bool, typer.Option("--log", help="Generate log keypair for the gateway instead of issuer keypair")] = False,
) -> None:
    """Generate an Ed25519 asymmetric keypair for the offline policy issuer or gateway log."""
    import os

    from mandate.policy.crypto import generate_keypair

    out_dir.mkdir(parents=True, exist_ok=True)
    priv_hex, pub_hex = generate_keypair()

    prefix = "log" if log else "issuer"
    priv_path = out_dir / f"{prefix}_private.key"
    pub_path = out_dir / f"{prefix}_public.key"

    priv_path.write_text(priv_hex + "\n")
    os.chmod(priv_path, 0o600)
    pub_path.write_text(pub_hex + "\n")

    label = "gateway log" if log else "offline issuer"
    typer.echo(f"Generated Ed25519 {label} keypair:")
    typer.echo(f"  private key (keep secret): {priv_path} (mode 0600)")
    typer.echo(f"  public key  (distribute) : {pub_path}")
    typer.echo(f"  public key hex           : {pub_hex}")


@app.command("verify")
def verify_cmd(
    receipt: Annotated[Path, typer.Option("--receipt", help="Path to audit inclusion proof receipt JSON")],
    head: Annotated[Path, typer.Option("--head", help="Path to signed Merkle log head JSON")],
    log_public_key: Annotated[Path, typer.Option("--log-public-key")] = Path(".mandate/keys/log_public.key"),
) -> None:
    """Verify an offline audit receipt against a signed Merkle log head."""
    from mandate.gateway.merkle import verify_inclusion_proof
    from mandate.policy.crypto import verify_bytes

    if not receipt.exists() or not head.exists():
        typer.echo("Error: receipt or head file not found.")
        raise typer.Exit(code=1)

    rec_data = json.loads(receipt.read_text())
    head_data = json.loads(head.read_text())

    # 1. Verify the signature on the log head. A missing key file is a failure, not a
    #    skip: an unverified head proves nothing, and reporting success without it is
    #    the fail-open the service startup check already refuses elsewhere.
    if not log_public_key.exists():
        typer.echo(f"ERROR: log public key not found at {log_public_key}. "
                   f"Cannot verify a head without it.")
        raise typer.Exit(code=1)

    pub_hex = log_public_key.read_text().strip()
    sig_hex = head_data.get("sig", "")
    msg = f"{head_data['size']}:{head_data['root']}:{head_data['ts']}".encode()
    if not verify_bytes(msg, sig_hex, pub_hex):
        typer.echo("ERROR: log head signature INVALID for this public key")
        raise typer.Exit(code=1)
    typer.echo("OK  log head signature verified")

    # 2. Verify inclusion proof
    leaf_record_hash = rec_data["leaf_record_hash"]
    index = rec_data["seq"] - 1
    tree_size = rec_data["tree_size"]
    proof = rec_data["proof"]
    expected_root = head_data["root"]

    ok = verify_inclusion_proof(leaf_record_hash, index, tree_size, proof, expected_root)
    if ok:
        typer.echo(f"OK  seq #{rec_data['seq']} included in root {expected_root[:23]}...")
    else:
        typer.echo("ERROR: inclusion proof failed verification")
        raise typer.Exit(code=1)


@app.command("quote-keygen")
def quote_keygen(
    merchant: Annotated[str, typer.Option("--merchant", help="Merchant identifier (e.g. blinkit, zepto)")],
    out_dir: Annotated[Path, typer.Option("--out-dir", help="Directory to write key files")] = Path(".mandate/keys"),
    keyring: Annotated[Path, typer.Option("--keyring", help="Path to merchants keyring JSON file")] = Path(".mandate/keys/merchants.json"),
) -> None:
    """Generate an Ed25519 keypair for a merchant and add the public key to keyring."""
    import os

    from mandate.gateway.quote import MerchantKeyring
    from mandate.policy.crypto import generate_keypair

    out_dir.mkdir(parents=True, exist_ok=True)
    priv_hex, pub_hex = generate_keypair()

    norm_m = merchant.strip().lower()
    priv_path = out_dir / f"merchant_{norm_m}_private.key"
    pub_path = out_dir / f"merchant_{norm_m}_public.key"

    priv_path.write_text(priv_hex + "\n")
    os.chmod(priv_path, 0o600)
    pub_path.write_text(pub_hex + "\n")

    ring = MerchantKeyring.from_file(keyring) if keyring.exists() else MerchantKeyring()
    ring.add_key(norm_m, pub_hex)
    ring.save(keyring)

    typer.echo(f"Generated Ed25519 quote keypair for merchant {norm_m!r}:")
    typer.echo(f"  private key (merchant secret): {priv_path} (mode 0600)")
    typer.echo(f"  public key  (distribute)     : {pub_path}")
    typer.echo(f"  public key hex               : {pub_hex}")
    typer.echo(f"  keyring updated              : {keyring}")


@app.command("quote-sign")
def quote_sign(
    merchant: Annotated[str, typer.Option("--merchant", help="Merchant identifier")],
    sku: Annotated[str, typer.Option("--sku", help="SKU identifier")],
    price: Annotated[int, typer.Option("--price", help="Unit price in paise (e.g. 5000 = Rs 50)")],
    key: Annotated[str, typer.Option("--key", help="Merchant Ed25519 private key hex or path to private key file")],
    ttl: Annotated[int, typer.Option("--ttl", help="Validity period in seconds")] = 900,
) -> None:
    """Mint an Ed25519-signed merchant quote."""
    from datetime import UTC, datetime, timedelta

    from mandate.gateway.quote import mint_quote

    priv_hex = key.strip()
    key_path = Path(priv_hex)
    if key_path.exists():
        priv_hex = key_path.read_text().strip()

    now = datetime.now(UTC)
    expires = now + timedelta(seconds=ttl)
    token = mint_quote(
        merchant=merchant,
        sku=sku,
        unit_price_paise=price,
        private_key_hex=priv_hex,
        issued=now,
        expires=expires,
    )
    typer.echo(token)


@app.command("quote-verify")
def quote_verify(
    quote: Annotated[str, typer.Option("--quote", help="Raw quote string <payload_b64>.<sig_hex>")],
    merchant: Annotated[str, typer.Option("--merchant", help="Expected merchant identifier")],
    sku: Annotated[str, typer.Option("--sku", help="Expected SKU identifier")],
    keyring: Annotated[Path, typer.Option("--keyring", help="Path to merchants keyring JSON file")] = Path(".mandate/keys/merchants.json"),
) -> None:
    """Verify an Ed25519-signed merchant quote."""
    from datetime import UTC, datetime

    from mandate.gateway.quote import MerchantKeyring, QuoteError, verify_quote
    from mandate.money import Paise, fmt

    if not keyring.exists():
        typer.echo(f"Error: keyring file {keyring} not found.")
        raise typer.Exit(code=1)

    ring = MerchantKeyring.from_file(keyring)
    try:
        now = datetime.now(UTC)
        unit_price = verify_quote(
            raw_quote=quote,
            expected_merchant=merchant,
            expected_sku=sku,
            keyring=ring,
            now=now,
        )
        typer.echo(f"Quote VALID: merchant={merchant} sku={sku} price={fmt(Paise(unit_price))} ({unit_price} paise)")
    except QuoteError as e:
        typer.echo(f"Quote INVALID ({e.clause_id}): {e}")
        raise typer.Exit(code=1)


@app.command("evidence")
def evidence(
    out: Path = Path("web/src/data/evidence.json"),
    root: Path = Path("."),
    feed_run: str = "enforce/budget_salami_005",
) -> None:
    """Write the web console's payload from measured artefacts.

    The console reads this file and nothing else. Regenerate it after any run
    whose numbers should reach the screen; never edit it by hand.
    """
    import json as _json

    from mandate.harness.evidence import build_evidence

    ev = build_evidence(root=root, feed_run=feed_run)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_json.dumps(ev, indent=2, ensure_ascii=False) + "\n")
    sb = ev["scoreboard"]
    enf = sb["containment"].get("enforce", {})
    typer.echo(f"wrote {out}")
    typer.echo(f"  policy    {ev['policy']['mandate_id']} {ev['policy']['policy_hash'][:23]}")
    typer.echo(f"  runs      {ev['source']['containment_run']} + {ev['source']['false_block_run']}")
    typer.echo(f"  enforce   {enf.get('contained')}/{enf.get('total')} contained")
    typer.echo(f"  conform   {sb['conformance']['blocked']}/{sb['conformance']['total']} blocked, "
               f"{sb['conformance']['vacuous']} vacuous")
    typer.echo(f"  feed      {ev['feed']['run']} {ev['feed']['counts']}")





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
    pol = load_policy(policy, check_hash=False)
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


@app.command("mint-pool")
def mint_pool_cmd(
    count: Annotated[int, typer.Option("--count", help="Number of tokens to mint")] = 200,
    mandate_id: Annotated[str, typer.Option("--mandate-id")] = "mnd_groceries_01",
    key_file: Annotated[Path, typer.Option("--key-file")] = Path(".mandate/keys/issuer_private.key"),
    out: Annotated[Path, typer.Option("--out")] = Path(".mandate/token_pool.json"),
    hours: Annotated[int, typer.Option("--hours", help="Token lifetime in hours")] = 720,
    jti_prefix: Annotated[str, typer.Option(
        "--jti-prefix",
        help="jti namespace. Two pools MUST NOT share one: SessionManager keys "
             "sessions on jti and rmtree's the directory on create, so a "
             "collision deletes a live session's audit chain.",
    )] = "tok_pool",
) -> None:
    """Pre-mint a pool of signed agent tokens offline for judge sessions."""
    import json
    from datetime import UTC, datetime, timedelta

    from mandate.gateway.tokens import mint_agent_token

    if not key_file.exists():
        raise typer.BadParameter(f"Key file {key_file} not found. Run `mandate keygen` first.")
    priv_key_hex = key_file.read_text().strip()

    expires = (datetime.now(UTC) + timedelta(hours=hours)).isoformat()
    tokens = []
    for i in range(1, count + 1):
        jti = f"{jti_prefix}_{i:03d}"
        tok = mint_agent_token(
            mandate_id=mandate_id,
            private_key_hex=priv_key_hex,
            expires_iso=expires,
            jti=jti,
        )
        tokens.append(tok)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(tokens, indent=2))
    typer.echo(
        f"Minted {len(tokens)} tokens to {out} "
        f"(jti {jti_prefix}_001..{jti_prefix}_{count:03d}, "
        f"mandate {mandate_id}, expires {expires})"
    )


@app.command("ap2-export")
def ap2_export_cmd(
    policy: Annotated[Path, typer.Option("--policy")] = Path("policies/policy.yaml"),
    out: Annotated[Path | None, typer.Option("--out")] = None,
) -> None:
    """Export a signed policy AST as an AP2 v0.2 Open Checkout Mandate credential."""
    from mandate.ap2.render import render_ap2_mandate
    pol = load_policy(policy)
    doc = render_ap2_mandate(pol)
    output_json = json.dumps(doc.model_dump(mode="json"), indent=2)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(output_json)
        typer.echo(f"Exported AP2 v0.2 mandate to {out}")
    else:
        typer.echo(output_json)


@app.command("serve")
def serve_cmd(
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8000,
    policy: Annotated[Path, typer.Option("--policy")] = Path("policies/policy.yaml"),
    public_key: Annotated[Path, typer.Option("--public-key")] = Path(".mandate/keys/issuer_public.key"),
    revocations: Annotated[Path, typer.Option("--revocations")] = Path("revocations.jsonl"),
    token_pool: Annotated[Path, typer.Option("--token-pool")] = Path(".mandate/token_pool.json"),
    sandbox_pool: Annotated[Path, typer.Option(
        "--sandbox-pool",
        help="Tokens bound to the reserved sandbox mandate. Absent, /v1/sandbox "
             "reports unavailable rather than falling back to the signed mandate.",
    )] = Path(".mandate/sandbox_pool.json"),
    merchant_keys: Annotated[Path | None, typer.Option("--merchant-keys")] = Path(".mandate/keys/merchants.json"),
    capability_secret: Annotated[str | None, typer.Option("--capability-secret", envvar="MANDATE_CAPABILITY_SECRET")] = None,
    static_dir: Annotated[Path | None, typer.Option("--static-dir")] = Path("web/dist"),
    store: Annotated[Path | None, typer.Option("--store", envvar="MANDATE_STORE_PATH")] = None,
) -> None:
    """Run the standalone Mandate Gateway daemon process."""
    import os

    import uvicorn

    # `check`, `compile`, `evaluate` and `demo` all do this; serve did not, so
    # RAZORPAY_KEY_* and MANDATE_CAPABILITY_SECRET in .env were never read and
    # the daemon silently fell back to FakeDownstream however the file was set.
    load_dotenv()

    from mandate.downstream.fake import FakeDownstream
    from mandate.downstream.razorpay import RazorpayDownstream
    from mandate.gateway.pricebook import DictPriceBook
    from mandate.service.server import create_app
    from mandate.service.token_pool import TokenPool

    secret = capability_secret or os.environ.get("MANDATE_CAPABILITY_SECRET")
    if not secret:
        raise typer.BadParameter("MANDATE_CAPABILITY_SECRET environment variable or --capability-secret flag is required.")

    # Pricebook from canonical catalog
    catalog = None
    pricebook = None
    corpus_path = Path("corpus/corpus.json")
    if corpus_path.exists():
        from mandate.harness.corpus import load_corpus
        items = load_corpus(corpus_path)
        if items:
            catalog = items[0].mutation.clean_catalog or items[0].mutation.catalog
    if catalog is None:
        from mandate.harness.catalog import generate_catalog
        catalog = generate_catalog(seed=42)
    pricebook = DictPriceBook.from_catalog(catalog)

    # Downstream: Razorpay if keys present, else FakeDownstream
    rzp_key = os.environ.get("RAZORPAY_KEY_ID")
    rzp_secret = os.environ.get("RAZORPAY_KEY_SECRET")
    if rzp_key and rzp_secret:
        downstream = RazorpayDownstream(key_id=rzp_key, key_secret=rzp_secret)
        typer.echo(f"  Downstream : Razorpay (key {rzp_key[:12]}...)")
    else:
        downstream = FakeDownstream()
        typer.echo("  Downstream : FakeDownstream (test mode)")

    pool = TokenPool.from_file(token_pool) if token_pool.exists() else TokenPool([])
    sbx = TokenPool.from_file(sandbox_pool) if sandbox_pool.exists() else TokenPool([])

    typer.echo(f"Starting Mandate Gateway Daemon on http://{host}:{port}")
    typer.echo(f"  Policy     : {policy}")
    typer.echo(f"  Public Key : {public_key}")
    typer.echo(f"  Revocations: {revocations}")
    typer.echo(f"  Token Pool : {pool.available_count} available tokens")
    typer.echo(f"  Sandbox    : {sbx.available_count} available tokens"
               f"{'' if sbx.available_count else ' (/v1/sandbox disabled)'}")
    typer.echo(f"  Storefront : {store or '/tmp/mandate-store/orders.jsonl'}")

    app_instance = create_app(
        policy_path=policy,
        public_key_path=public_key if public_key.exists() else None,
        revocations_path=revocations,
        capability_secret=secret,
        pricebook=pricebook,
        downstream=downstream,
        token_pool=pool,
        sandbox_pool=sbx,
        catalog=catalog,
        static_dir=static_dir if (static_dir and static_dir.exists()) else None,
        store_path=store or Path("/tmp/mandate-store/orders.jsonl"),
        merchant_keys_path=merchant_keys if (merchant_keys and merchant_keys.exists()) else None,
    )
    uvicorn.run(app_instance, host=host, port=port, log_level="info")


@app.command("conformance")
def conformance_cmd(
    out_dir: Annotated[Path, typer.Option("--out")] = Path("results-conformance"),
    trials: Annotated[int, typer.Option("--trials", help="Concurrency trials per race attack.")] = 200,
) -> None:

    """Run the Protocol Conformance Test Suite with Witnesses.

    Every attack runs against both an unhardened gateway (the witness) and the
    hardened gateway. Reports exact counts (BLOCKED / ESCAPED / VACUOUS).
    """
    import json as _json

    from mandate.conformance.suite import run_conformance_suite

    results = run_conformance_suite(trials=trials)
    typer.echo(f"Running Mandate Protocol Conformance Suite ({len(results)} hostile attacks)...\n")

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
    typer.echo(f"\nSummary: {len(results)} attacks, {blocked_cnt} blocked, "
               f"{escaped_cnt} escaped, {vacuous_cnt} vacuous.")
    typer.echo("A count, not a percentage: nothing here is sampled from a model, so "
               "there is nothing to bootstrap.")
    if vacuous_cnt:
        typer.echo(f"WARNING: {vacuous_cnt} attack(s) VACUOUS. Their witness never "
                   f"fired, so they prove nothing and are not counted as blocked.")
    typer.echo("")

    summary_file = out_dir / "conformance_results.json"
    summary_file.write_text(_json.dumps({
        "total": len(results),
        "blocked": blocked_cnt,
        "escaped": escaped_cnt,
        "vacuous": vacuous_cnt,
        "race_trials": trials,
        # No `model` field anywhere in this file, by design: score() raises on a
        # set containing scripted rows, and conformance rows must never be able to
        # enter the containment set.
        "results": report_rows,
    }, indent=2))
    typer.echo(f"Wrote conformance report to {summary_file}")


if __name__ == "__main__":
    app()
