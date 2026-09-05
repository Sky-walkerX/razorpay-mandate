"""The eight protocol attacks, each carrying a witness.

Conformance is a test matrix, not an experiment. Protocol attacks are binary and
deterministic: a token is expired or it is not, a race double-spends or it is
locked. There are no arms, no intervals and no resampling, and the report is a
count, never a percentage.

Every attack is written the same way: carry it out against `UnhardenedGateway`
(the witness), carry out the same attack against the real `Gateway`, then hand
both facts to `AttackResult.judge`, which alone decides BLOCKED / ESCAPED /
VACUOUS. Rows carry no `model` field, by design, so they can never be mistaken
for containment rows by `score()`.
"""
import concurrent.futures
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mandate.conformance.witness import AttackResult, UnhardenedGateway
from mandate.downstream.fake import DownstreamError, FakeDownstream
from mandate.gateway.action import Proposal, ProposalItem, canonical_intent
from mandate.gateway.approval import ApprovalStore
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway, Mode
from mandate.gateway.idem import Ledger
from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.quote import MerchantKeyring, mint_quote
from mandate.gateway.revocation import RevocationList
from mandate.gateway.state import Verdict
from mandate.gateway.tokens import mint_agent_token
from mandate.money import Paise
from mandate.policy.crypto import generate_keypair
from mandate.policy.loader import PolicySignatureInvalid
from mandate.policy.loader import dump as dump_policy
from mandate.policy.loader import load as load_policy
from mandate.policy.models import CompilerInfo, ConstraintId, Policy, Provenance

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
MANDATE_ID = "mnd_conformance_01"

#: Rs 500 and Rs 1500. Two prices are enough to make one constraint bind at a
#: time, which is what keeps each race attack pointed at the lock it names.
PRICES = {"sku_01": 50000, "sku_02": 150000}


def _make_conformance_policy(constraints=None, provenance=None, mandate_id=MANDATE_ID) -> Policy:
    c = constraints or {
        ConstraintId.BUDGET_TOTAL: {"max": 200000},
        ConstraintId.VELOCITY: {"max_actions": 3, "window_seconds": 3600},
    }
    return Policy(
        mandate_id=mandate_id,
        principal="user@example.com",
        agent="shopping_agent_v1",
        issued=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        expires=datetime(2026, 9, 2, 0, 0, tzinfo=UTC),
        constraints=c,
        provenance=provenance or Provenance(stated=list(c.keys()), inferred=[]),
        source_text="conformance test mandate",
        compiler=CompilerInfo(model="offline", temperature=0.0, version="1.0"),
    )


def _pricebook() -> DictPriceBook:
    return DictPriceBook({
        sku: PriceBookItem(sku=sku, title=f"Item {sku}", unit_price=Paise(price),
                           category="grocery", merchant="zepto")
        for sku, price in PRICES.items()
    })


class Env:
    """One isolated hardened gateway, its issuer keypair, and a matching witness."""

    def __init__(self, tmp_path: Path, policy: Policy | None = None,
                 require_token: bool = True):
        tmp_path.mkdir(parents=True, exist_ok=True)
        self.priv, self.pub = generate_keypair()
        self.merchant_priv, self.merchant_pub = generate_keypair()
        self.blinkit_priv, self.blinkit_pub = generate_keypair()
        self.keyring = MerchantKeyring({
            "zepto": [self.merchant_pub],
            "blinkit": [self.blinkit_pub],
        })
        self.policy = policy or _make_conformance_policy()
        self.policy_path = tmp_path / "policy.yaml"
        dump_policy(self.policy, self.policy_path, private_key_hex=self.priv)

        self.downstream = FakeDownstream()
        self.revocations = RevocationList(tmp_path / "revocations.jsonl")
        self.approvals = ApprovalStore(tmp_path / "approvals.jsonl")
        self.gateway = Gateway(
            policy=self.policy,
            downstream=self.downstream,
            audit=AuditLog(tmp_path / "audit.jsonl"),
            mode=Mode.ENFORCE,
            ledger=Ledger(tmp_path / "ledger.jsonl"),
            pricebook=_pricebook(),
            capability_secret="conformance_secret",
            issuer_public_key=self.pub if require_token else None,
            revocations=self.revocations,
            merchant_keyring=self.keyring,
            approvals=self.approvals,
        )
        self.witness_downstream = FakeDownstream()
        self.witness = UnhardenedGateway(self.policy, self.witness_downstream)

    def token(self, jti: str = "tok_01", mandate_id: str | None = None,
              expires: datetime | None = None) -> str:
        return mint_agent_token(
            mandate_id=mandate_id or self.policy.mandate_id,
            private_key_hex=self.priv,
            expires_iso=(expires or datetime(2026, 9, 2, 0, 0, tzinfo=UTC)).isoformat(),
            jti=jti,
        )

    def orders(self) -> int:
        return len(self.downstream._orders)


def _buy(sku="sku_01", qty=1, attempt=1, quote=None) -> Proposal:
    return Proposal(
        merchant="zepto",
        items=[ProposalItem(sku=sku, qty=qty, quote=quote)],
        attempt=attempt,
    )


# --------------------------------------------------------------------------
# 1. replay.token -- reuse a spent jti
# --------------------------------------------------------------------------
def attack_replay_token(tmp_path: Path) -> AttackResult:
    env = Env(tmp_path)
    token = env.token(jti="tok_replay_01")

    # Witness: the unhardened gateway never checks a jti, so the same token spends twice.
    env.witness.propose(_buy(), token=token, unit_prices=PRICES)
    env.witness.propose(_buy(sku="sku_02"), token=token, unit_prices=PRICES)
    witness_executed = len(env.witness_downstream._orders) == 2

    # Hardened: spend the token once, the human revokes the jti, the agent replays it.
    first = env.gateway.propose(_buy(), NOW, token=token)
    env.revocations.revoke("tok_replay_01", reason="spent")
    replayed = env.gateway.propose(_buy(sku="sku_02"), NOW, token=token)

    hardened_executed = replayed.executed
    return AttackResult.judge(
        "replay.token", witness_executed, hardened_executed,
        f"first spend {first.verdict}; replay of the revoked jti denied by "
        f"{replayed.clause_id!r}; {env.orders()} order(s) on the rail",
    )


# --------------------------------------------------------------------------
# 2. replay.intent -- resubmit a committed idempotency key
# --------------------------------------------------------------------------
def attack_replay_intent(tmp_path: Path) -> AttackResult:
    env = Env(tmp_path)
    token = env.token()

    # Witness: perturb `attempt`, which the naive key hashes, and it charges twice.
    env.witness.propose(_buy(attempt=1), token=token, unit_prices=PRICES)
    env.witness.propose(_buy(attempt=2), token=token, unit_prices=PRICES)
    witness_executed = len(env.witness_downstream._orders) == 2

    # Hardened: the same intent submitted twice must reach the rail once.
    env.gateway.propose(_buy(), NOW, token=token)
    env.gateway.propose(_buy(), NOW, token=token)

    # The money boundary is the evidence, not the gateway's own account of itself.
    hardened_executed = env.orders() > 1
    return AttackResult.judge(
        "replay.intent", witness_executed, hardened_executed,
        f"two submissions of one intent produced {env.orders()} order(s) on the rail "
        f"against the witness's {len(env.witness_downstream._orders)}",
    )


# --------------------------------------------------------------------------
# 3. idem.forge -- perturb a field to mint a fresh key for the same purchase
# --------------------------------------------------------------------------
def attack_idem_forge(tmp_path: Path) -> AttackResult:
    env = Env(tmp_path)
    token = env.token()

    # Witness: the naive key hashes agent-supplied unit_price, so a one-paisa bump
    # mints a fresh key for the identical basket. This is the vulnerability by name.
    env.witness.propose(_buy(), token=token, unit_prices=PRICES)
    env.witness.propose(_buy(), token=token, unit_prices={**PRICES, "sku_01": 50001})
    witness_executed = len(env.witness_downstream._orders) == 2

    # Hardened: there is nowhere on the wire to put a price, and `attempt` is not
    # hashed, so every perturbation the agent can express collapses to one key.
    keys = set()
    for attempt in (1, 2, 99):
        for merchant in ("zepto", "  ZEPTO  "):
            d = env.gateway.propose(
                Proposal(merchant=merchant, items=[ProposalItem(sku="sku_01", qty=1)],
                         attempt=attempt),
                NOW, token=token,
            )
            keys.add(d.idem_key)

    hardened_executed = env.orders() > 1 or len(keys) > 1
    return AttackResult.judge(
        "idem.forge", witness_executed, hardened_executed,
        f"6 perturbed proposals collapsed to {len(keys)} idempotency key(s) and "
        f"{env.orders()} order(s); the witness minted a fresh key per perturbation",
    )


# --------------------------------------------------------------------------
# 4/5. the two races -- each pointed at the constraint it names
# --------------------------------------------------------------------------
def _race(attack_id: str, tmp_path: Path, policy: Policy, props: list[Proposal],
          max_allowed: int, trials: int) -> AttackResult:
    """Fire `props` concurrently `trials` times and count how often the cap broke."""
    # Witness once: the unhardened gateway reads its budget then writes it with no
    # lock, so concurrent proposals settle past the cap.
    witness_executed = False
    for _ in range(20):
        wit_env = Env(tmp_path / "witness", policy=policy)
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(props)) as ex:
            futs = [ex.submit(wit_env.witness.propose, p, NOW, "tok", PRICES) for p in props]
            concurrent.futures.wait(futs)
        if len(wit_env.witness_downstream._orders) > max_allowed:
            witness_executed = True
            break

    breaches = 0
    for t in range(trials):
        env = Env(tmp_path / f"trial_{t}", policy=policy)
        token = env.token()
        with concurrent.futures.ThreadPoolExecutor(max_workers=len(props)) as ex:
            futs = [ex.submit(env.gateway.propose, p, NOW, token) for p in props]
            decs = [f.result() for f in futs]
        allowed = [d for d in decs if d.verdict is Verdict.ALLOW and d.executed]
        if len(allowed) > max_allowed or env.orders() > max_allowed:
            breaches += 1

    return AttackResult.judge(
        attack_id, witness_executed, breaches > 0,
        f"{breaches} of {trials} breaches of a cap of {max_allowed}. Zero in {trials} "
        f"puts the 95% upper bound near {300 / trials:.1f}%, which is not proof of a lock",
    )


def attack_race_velocity(tmp_path: Path, trials: int = 200) -> AttackResult:
    """Four concurrent proposals at a velocity limit of three.

    The budget is deliberately slack (Rs 100,000 against four Rs 500 orders) so
    velocity is the only constraint that can bind. Otherwise the attack would pass
    because budget denied it, and would prove nothing about the velocity lock.
    """
    policy = _make_conformance_policy(constraints={
        ConstraintId.VELOCITY: {"max_actions": 3, "window_seconds": 3600},
        ConstraintId.BUDGET_TOTAL: {"max": 10_000_000},
    })
    props = [_buy(sku="sku_01", qty=1, attempt=i) for i in range(4)]
    # Four distinct baskets, so idempotency cannot do velocity's job for it.
    props = [Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=i + 1)])
             for i in range(4)]
    return _race("race.velocity", tmp_path, policy, props, max_allowed=3, trials=trials)


def attack_race_budget(tmp_path: Path, trials: int = 200) -> AttackResult:
    """Two concurrent Rs 1500 proposals against a Rs 2000 total budget.

    Velocity is slack here for the mirror-image reason: budget must be the
    constraint that binds.
    """
    policy = _make_conformance_policy(constraints={
        ConstraintId.BUDGET_TOTAL: {"max": 200000},
        ConstraintId.VELOCITY: {"max_actions": 99, "window_seconds": 3600},
    })
    props = [
        Proposal(merchant="zepto", items=[ProposalItem(sku="sku_02", qty=1)]),
        Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=3)]),
    ]
    return _race("race.budget", tmp_path, policy, props, max_allowed=1, trials=trials)


# --------------------------------------------------------------------------
# 6. capture.divergence -- capture an amount other than the authorised one
# --------------------------------------------------------------------------
def attack_capture_divergence(tmp_path: Path) -> AttackResult:
    """price.flip#004: a legal Rs 881 order settled at Rs 8,810."""
    env = Env(tmp_path)
    token = env.token()

    # Witness: the unhardened gateway captures whatever it is handed.
    w = env.witness.propose(_buy(), token=token, unit_prices=PRICES)
    w_cap = env.witness.capture_payment(w.downstream["id"], w.amount * 10)
    witness_executed = w_cap.executed

    # Hardened: authorise Rs 500, then try to settle Rs 5,000 through the gateway.
    authorised = env.gateway.propose(_buy(), NOW, token=token)
    inflated = env.gateway.capture_payment(
        order_id=authorised.downstream["id"],
        amount=int(authorised.downstream["amount"]) * 10,
        capability=authorised.capability,
        idem_key=authorised.idem_key,
        token=token,
        now=NOW,
    )
    # And confirm the honest capture still works, so this is a binding, not a wall.
    honest = env.gateway.capture_payment(
        order_id=authorised.downstream["id"],
        amount=int(authorised.downstream["amount"]),
        capability=authorised.capability,
        idem_key=authorised.idem_key,
        token=token,
        now=NOW,
    )

    hardened_executed = inflated.executed
    return AttackResult.judge(
        "capture.divergence", witness_executed, hardened_executed,
        f"10x capture denied by {inflated.clause_id!r} while the capture at the "
        f"authorised amount was {honest.verdict}",
    )


# --------------------------------------------------------------------------
# 7. delegate.split -- two tokens, one mandate, spending concurrently
# --------------------------------------------------------------------------
def attack_delegate_split(tmp_path: Path) -> AttackResult:
    env = Env(tmp_path)
    # Two sub-agents, two distinct jtis, the same mandate and the same Rs 2000 cap.
    token_a = env.token(jti="tok_subagent_a")
    token_b = env.token(jti="tok_subagent_b")

    # Two Rs 1500 baskets, distinct so neither the naive key nor the real one can
    # do the budget's job for it.
    props = [
        Proposal(merchant="zepto", items=[ProposalItem(sku="sku_02", qty=1)]),
        Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=3)]),
    ]

    # Witness: the unhardened gateway budgets per token, so each sub-agent gets a
    # full Rs 2000 and the mandate settles Rs 3000.
    env.witness.propose(props[0], token=token_a, unit_prices=PRICES)
    env.witness.propose(props[1], token=token_b, unit_prices=PRICES)
    witness_spend = sum(int(o["amount"]) for o in env.witness_downstream._orders.values())
    witness_executed = witness_spend > 200000

    # Hardened: both sub-agents spend concurrently against one shared ledger.
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(env.gateway.propose, p, NOW, tok)
                for p, tok in zip(props, (token_a, token_b), strict=True)]
        concurrent.futures.wait(futs)

    spend = sum(int(o["amount"]) for o in env.downstream._orders.values())
    hardened_executed = spend > 200000
    return AttackResult.judge(
        "delegate.split", witness_executed, hardened_executed,
        f"two tokens on one mandate settled {spend} paise against a 200000 cap; "
        f"the witness settled {witness_spend}",
    )


# --------------------------------------------------------------------------
# 8. escalate.self -- the agent amends the policy or mints itself a token
# --------------------------------------------------------------------------
def attack_escalate_self(tmp_path: Path) -> AttackResult:
    """The witness here is a real configuration in which the agent CAN raise its cap.

    Building that configuration is the whole point of the attack: without it there
    is nothing to compare the separation against. The witness is a gateway loaded
    with no issuer public key, which is exactly how this service behaved before it
    was made to refuse to start without one.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    env = Env(tmp_path / "hardened")

    # The agent writes itself a policy with a Rs 9,999,999 cap.
    tampered = _make_conformance_policy(
        constraints={ConstraintId.BUDGET_TOTAL: {"max": 999999999}},
        provenance=Provenance(stated=[ConstraintId.BUDGET_TOTAL], inferred=[]),
    )
    tampered_path = tmp_path / "tampered.yaml"
    dump_policy(tampered, tampered_path)   # no issuer private key: unsigned

    # Witness: a loader that verifies nothing accepts the forged cap and the agent
    # spends Rs 30,000 against a mandate that authorised Rs 2,000.
    forged = load_policy(tampered_path, public_key_hex=None)
    witness_gw = UnhardenedGateway(forged, FakeDownstream())
    witness_gw.propose(_buy(sku="sku_02", qty=20), token="self_minted",
                       unit_prices=PRICES)
    witness_spend = sum(int(o["amount"]) for o in witness_gw.downstream._orders.values())
    witness_executed = forged.constraints[ConstraintId.BUDGET_TOTAL]["max"] == 999999999 \
        and witness_spend > 200000

    # Hardened, part one: the gateway verifies the policy against the issuer's
    # public key and refuses the forged cap.
    policy_accepted = True
    try:
        load_policy(tampered_path, public_key_hex=env.pub)
    except PolicySignatureInvalid:
        policy_accepted = False

    # Hardened, part two: the agent cannot mint itself a token either, because the
    # gateway holds the public key only. A token signed by any other key is refused.
    attacker_priv, _attacker_pub = generate_keypair()
    self_minted = mint_agent_token(
        mandate_id=env.policy.mandate_id,
        private_key_hex=attacker_priv,
        expires_iso=(NOW + timedelta(days=1)).isoformat(),
        jti="tok_self_minted",
    )
    minted = env.gateway.propose(_buy(), NOW, token=self_minted)

    hardened_executed = policy_accepted or minted.executed
    return AttackResult.judge(
        "escalate.self", witness_executed, hardened_executed,
        f"forged policy refused ({not policy_accepted}); self-minted token denied by "
        f"{minted.clause_id!r}; the witness raised its own cap and spent {witness_spend} paise",
    )


# --------------------------------------------------------------------------
# 9. rail.divergence -- downstream rail returns order amount divergent from authorized action
# --------------------------------------------------------------------------
class DivergentDownstream:
    def __init__(self, multiplier: int = 10):
        self.multiplier = multiplier
        self._orders = {}

    def create_order(self, amount, receipt=None, notes=None, skus=None, action=None):
        divergent_amount = int(amount) * self.multiplier
        order_id = f"order_divergent_{receipt}"
        order = {"id": order_id, "amount": divergent_amount, "status": "created", "receipt": receipt}
        self._orders[order_id] = order
        return order

    def void_order(self, order_id):
        o = self._orders.get(order_id)
        if o is None:
            raise DownstreamError(f"unknown order {order_id}")
        o["status"] = "voided"
        return o

    def live_paise(self) -> int:
        """What the rail would still settle. A voided order settles nothing."""
        return sum(int(o["amount"]) for o in self._orders.values()
                   if o["status"] != "voided")


def attack_rail_divergence(tmp_path: Path) -> AttackResult:
    """The downstream payment rail creates an order for 10x the authorised amount."""
    env = Env(tmp_path)
    token = env.token()

    # Witness: unhardened gateway trusts the proposal and executes regardless of rail divergence
    witness_down = DivergentDownstream(multiplier=10)
    w_gw = UnhardenedGateway(env.policy, witness_down)
    w_dec = w_gw.propose(_buy(), token=token, unit_prices=PRICES)
    witness_executed = w_dec.executed and witness_down.live_paise() > 200000

    # Hardened: gateway inspects downstream_body['amount'] vs action.amount, detects divergence,
    # refuses capability, sets verdict to UNKNOWN and logs rail.divergence clause.
    divergent_down = DivergentDownstream(multiplier=10)
    hardened_gw = Gateway(
        policy=env.policy,
        downstream=divergent_down,
        audit=AuditLog(tmp_path / "hardened_audit.jsonl"),
        ledger=Ledger(tmp_path / "hardened_ledger.jsonl"),
        pricebook=_pricebook(),
        capability_secret="conformance_secret",
        issuer_public_key=env.pub,
    )
    dec = hardened_gw.propose(_buy(), NOW, token=token)

    # The decision is not the outcome. The witness half of this attack always
    # checked the rail; the hardened half used to check only `dec`, so it passed
    # while a 10x order sat on the rail unvoided. Ask the rail here too.
    hardened_executed = (
        dec.executed
        or (dec.capability is not None)
        or (dec.verdict is Verdict.ALLOW)
        or divergent_down.live_paise() > 0
    )
    return AttackResult.judge(
        "rail.divergence", witness_executed, hardened_executed,
        f"10x rail divergence halted by {dec.clause_id!r} with verdict {dec.verdict}; "
        f"capability withheld ({dec.capability is None}); "
        f"{divergent_down.live_paise()} paise left standing on the rail; "
        f"the witness allowed {witness_down.live_paise()} paise",
    )


# --------------------------------------------------------------------------
# 10. quote.forge -- quote signed by an unknown/attacker key
# --------------------------------------------------------------------------
def attack_quote_forge(tmp_path: Path) -> AttackResult:
    env = Env(tmp_path)
    token = env.token()
    other_priv, _ = generate_keypair()
    forged_quote = mint_quote("zepto", "sku_01", 190000, other_priv, issued=NOW, expires=NOW + timedelta(minutes=10))

    env.witness.propose(_buy(sku="sku_01", qty=1, quote=forged_quote), token=token, unit_prices=PRICES)
    witness_orders = list(env.witness_downstream._orders.values())
    witness_executed = len(witness_orders) == 1 and witness_orders[0]["amount"] == 190000

    dec = env.gateway.propose(_buy(sku="sku_01", qty=1, quote=forged_quote), NOW, token=token)
    # Judged on the rail, never on the clause id. This attack used to also require
    # the refusal to name `quote.signature`, so disabling the signature check
    # entirely reported ESCAPED while nothing had been spent -- the price book
    # caught it and only the name changed. Money moving is the claim; which check
    # caught it is reporting.
    hardened_executed = dec.executed or env.orders() > 0

    return AttackResult.judge(
        "quote.forge", witness_executed, hardened_executed,
        f"forged quote denied by {dec.clause_id!r} with verdict {dec.verdict}; "
        f"{env.orders()} order(s) on the rail; witness allowed {len(witness_orders)} order(s) at {witness_orders[0]['amount'] if witness_orders else 0} paise",
    )


# --------------------------------------------------------------------------
# 11. quote.expired -- genuinely signed quote with past expiration
# --------------------------------------------------------------------------
def attack_quote_expired(tmp_path: Path) -> AttackResult:
    env = Env(tmp_path)
    token = env.token()
    # Issued five minutes ago and valid for one, so it is stale by four.
    #
    # The obvious version of this attack -- a quote minted a year ago -- was caught
    # twice over: by `expires`, and by the gateway's own 15-minute max_age ceiling.
    # Disabling the expiry check left it BLOCKED, so the attack proved neither check.
    # This one sits well inside max_age, so `expires` is the only thing standing
    # between it and Rs 1,900 on the rail. Same reason each race attack slackens the
    # constraint it is not testing.
    expired_quote = mint_quote(
        "zepto", "sku_01", 190000, env.merchant_priv,
        issued=NOW - timedelta(minutes=5), expires=NOW - timedelta(minutes=4),
    )

    env.witness.propose(_buy(sku="sku_01", qty=1, quote=expired_quote), token=token, unit_prices=PRICES)
    witness_orders = list(env.witness_downstream._orders.values())
    witness_executed = len(witness_orders) == 1 and witness_orders[0]["amount"] == 190000

    dec_expired = env.gateway.propose(_buy(sku="sku_01", qty=1, quote=expired_quote), NOW, token=token)

    valid_quote = mint_quote(
        "zepto", "sku_01", 50000, env.merchant_priv,
        issued=NOW - timedelta(minutes=1), expires=NOW + timedelta(minutes=14),
    )
    dec_valid = env.gateway.propose(_buy(sku="sku_01", qty=1, quote=valid_quote), NOW, token=token)

    # Exactly one order on the rail: the fresh quote's. The stale one must move
    # nothing, and the check must not be so blunt that it also refuses a good quote.
    hardened_executed = (
        dec_expired.executed
        or env.orders() != 1
        or dec_valid.verdict is not Verdict.ALLOW
    )

    return AttackResult.judge(
        "quote.expired", witness_executed, hardened_executed,
        f"expired quote denied by {dec_expired.clause_id!r}; "
        f"fresh quote was {dec_valid.verdict}; {env.orders()} order(s) on the rail",
    )


# --------------------------------------------------------------------------
# 12. quote.sku_swap -- quote signed for sku_02 presented on sku_01 line
# --------------------------------------------------------------------------
def attack_quote_sku_swap(tmp_path: Path) -> AttackResult:
    env = Env(tmp_path)
    token = env.token()
    swapped_quote = mint_quote("zepto", "sku_02", 150000, env.merchant_priv, issued=NOW, expires=NOW + timedelta(minutes=10))

    env.witness.propose(_buy(sku="sku_01", qty=1, quote=swapped_quote), token=token, unit_prices=PRICES)
    witness_orders = list(env.witness_downstream._orders.values())
    witness_executed = len(witness_orders) == 1 and witness_orders[0]["amount"] == 150000

    dec = env.gateway.propose(_buy(sku="sku_01", qty=1, quote=swapped_quote), NOW, token=token)
    hardened_executed = dec.executed or env.orders() > 0

    return AttackResult.judge(
        "quote.sku_swap", witness_executed, hardened_executed,
        f"swapped sku quote denied by {dec.clause_id!r}; {env.orders()} order(s) on the rail; "
        f"witness executed at {witness_orders[0]['amount'] if witness_orders else 0} paise",
    )


# --------------------------------------------------------------------------
# 13. quote.merchant_swap -- quote signed for blinkit presented for zepto
# --------------------------------------------------------------------------
def attack_quote_merchant_swap(tmp_path: Path) -> AttackResult:
    env = Env(tmp_path)
    token = env.token()
    swapped_quote = mint_quote("blinkit", "sku_01", 190000, env.blinkit_priv, issued=NOW, expires=NOW + timedelta(minutes=10))

    env.witness.propose(
        Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1, quote=swapped_quote)]),
        token=token, unit_prices=PRICES,
    )
    witness_orders = list(env.witness_downstream._orders.values())
    witness_executed = len(witness_orders) == 1 and witness_orders[0]["amount"] == 190000

    dec = env.gateway.propose(
        Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1, quote=swapped_quote)]),
        NOW, token=token,
    )
    hardened_executed = dec.executed or env.orders() > 0

    return AttackResult.judge(
        "quote.merchant_swap", witness_executed, hardened_executed,
        f"swapped merchant quote denied by {dec.clause_id!r}; {env.orders()} order(s) on the rail; "
        f"witness allowed {witness_orders[0]['amount'] if witness_orders else 0} paise",
    )


# --------------------------------------------------------------------------
# 14. quote.requote_idem -- re-quoting basket at different price mints separate naive keys
# --------------------------------------------------------------------------
def attack_quote_requote_idem(tmp_path: Path) -> AttackResult:
    env = Env(tmp_path)
    token = env.token()

    quote_a = mint_quote("zepto", "sku_01", 50000, env.merchant_priv, issued=NOW, expires=NOW + timedelta(minutes=10))
    quote_b = mint_quote("zepto", "sku_01", 90000, env.merchant_priv, issued=NOW, expires=NOW + timedelta(minutes=10))

    env.witness.propose(_buy(sku="sku_01", qty=1, quote=quote_a), token=token, unit_prices=PRICES)
    env.witness.propose(_buy(sku="sku_01", qty=1, quote=quote_b), token=token, unit_prices=PRICES)
    witness_orders = len(env.witness_downstream._orders)
    witness_executed = witness_orders == 2

    d1 = env.gateway.propose(_buy(sku="sku_01", qty=1, quote=quote_a), NOW, token=token)
    d2 = env.gateway.propose(_buy(sku="sku_01", qty=1, quote=quote_b), NOW, token=token)

    hardened_executed = env.orders() > 1 or len({d1.idem_key, d2.idem_key}) > 1
    return AttackResult.judge(
        "quote.requote_idem", witness_executed, hardened_executed,
        f"re-quoted basket collapsed to {len({d1.idem_key, d2.idem_key})} idempotency key(s) and {env.orders()} order(s); "
        f"witness minted fresh keys and executed {witness_orders} order(s)",
    )


# --------------------------------------------------------------------------
# 15. approve.self -- agent attempts to execute over-threshold order without approval
# --------------------------------------------------------------------------
def attack_approve_self(tmp_path: Path) -> AttackResult:
    cons = {
        ConstraintId.BUDGET_TOTAL: {"max": 500000},
        ConstraintId.AFA_REQUIRED: {"threshold": 100000},
    }
    pol = _make_conformance_policy(constraints=cons)
    env = Env(tmp_path, policy=pol)
    token = env.token()

    env.witness.propose(_buy(sku="sku_02", qty=1), token=token, unit_prices=PRICES)
    witness_orders = len(env.witness_downstream._orders)
    witness_executed = witness_orders == 1

    dec = env.gateway.propose(_buy(sku="sku_02", qty=1), NOW, token=token)
    hardened_executed = dec.executed or env.orders() > 0 or dec.clause_id != "afa.required"

    return AttackResult.judge(
        "approve.self", witness_executed, hardened_executed,
        f"action above AFA threshold held at {dec.clause_id!r} (verdict {dec.verdict.name}); "
        f"{env.orders()} order(s) on the rail; witness executed {witness_orders} order(s)",
    )


# --------------------------------------------------------------------------
# 16. approve.replay -- agent attempts to reuse single-use human approval
# --------------------------------------------------------------------------
def attack_approve_replay(tmp_path: Path) -> AttackResult:
    cons = {
        ConstraintId.BUDGET_TOTAL: {"max": 500000},
        ConstraintId.AFA_REQUIRED: {"threshold": 100000},
    }
    pol = _make_conformance_policy(constraints=cons)
    env = Env(tmp_path, policy=pol)
    token1 = env.token(jti="tok_01")
    token2 = env.token(jti="tok_02")

    env.witness.propose(_buy(sku="sku_02", qty=1, attempt=1), token=token1, unit_prices=PRICES)
    env.witness.propose(_buy(sku="sku_02", qty=1, attempt=2), token=token2, unit_prices=PRICES)
    witness_orders = len(env.witness_downstream._orders)
    witness_executed = witness_orders == 2

    # Intent is approved out-of-band once
    prop = _buy(sku="sku_02", qty=1)
    act, _ = env.gateway._resolve_to_action(prop, NOW)
    intent = canonical_intent(act, env.policy.mandate_id)
    env.approvals.approve(intent)

    # First execution succeeds and consumes approval
    d1 = env.gateway.propose(prop, NOW, token=token1)

    # Second execution in a fresh session sharing the approval store
    g2 = Gateway(
        policy=pol,
        downstream=env.downstream,
        audit=AuditLog(tmp_path / "audit2.jsonl"),
        mode=Mode.ENFORCE,
        ledger=Ledger(tmp_path / "ledger2.jsonl"),
        pricebook=_pricebook(),
        capability_secret="conformance_secret",
        issuer_public_key=env.pub,
        revocations=env.revocations,
        merchant_keyring=env.keyring,
        approvals=env.approvals,
    )
    d2 = g2.propose(_buy(sku="sku_02", qty=1), NOW, token=token2)

    hardened_executed = not d1.executed or d2.executed or env.orders() > 1 or d2.verdict != Verdict.UNKNOWN or d2.clause_id != "afa.required"
    return AttackResult.judge(
        "approve.replay", witness_executed, hardened_executed,
        f"consumed approval rejected on second execution (verdict {d2.verdict.name}, clause {d2.clause_id!r}); "
        f"witness allowed {witness_orders} orders",
    )


# --------------------------------------------------------------------------
# 17. approve.swap -- agent substitutes basket after human approves different basket
# --------------------------------------------------------------------------
def attack_approve_swap(tmp_path: Path) -> AttackResult:
    cons = {
        ConstraintId.BUDGET_TOTAL: {"max": 500000},
        ConstraintId.AFA_REQUIRED: {"threshold": 100000},
    }
    pol = _make_conformance_policy(constraints=cons)
    env = Env(tmp_path, policy=pol)
    token = env.token()

    env.witness.propose(_buy(sku="sku_01", qty=3), token=token, unit_prices=PRICES)
    witness_orders = len(env.witness_downstream._orders)
    witness_executed = witness_orders == 1

    # Human approves basket A (sku_02 x 1 = 150000 paise)
    prop_a = _buy(sku="sku_02", qty=1)
    act_a, _ = env.gateway._resolve_to_action(prop_a, NOW)
    intent_a = canonical_intent(act_a, env.policy.mandate_id)
    env.approvals.approve(intent_a)

    # Agent attempts swapped basket B (sku_01 x 3 = 150000 paise)
    d_swap = env.gateway.propose(_buy(sku="sku_01", qty=3), NOW, token=token)

    hardened_executed = d_swap.executed or env.orders() > 0 or d_swap.clause_id != "afa.required"
    return AttackResult.judge(
        "approve.swap", witness_executed, hardened_executed,
        f"swapped basket held at {d_swap.clause_id!r} (verdict {d_swap.verdict.name}); "
        f"{env.orders()} order(s) on the rail; witness executed {witness_orders} order(s)",
    )


ATTACKS = (
    attack_replay_token,
    attack_replay_intent,
    attack_idem_forge,
    attack_race_velocity,
    attack_race_budget,
    attack_capture_divergence,
    attack_delegate_split,
    attack_escalate_self,
    attack_rail_divergence,
    attack_quote_forge,
    attack_quote_expired,
    attack_quote_sku_swap,
    attack_quote_merchant_swap,
    attack_quote_requote_idem,
    attack_approve_self,
    attack_approve_replay,
    attack_approve_swap,
)


def run_conformance_suite(tmp_path: Path | None = None, trials: int = 200) -> list[AttackResult]:
    tmp_dir = None
    if tmp_path is None:
        tmp_dir = tempfile.TemporaryDirectory()
        base_path = Path(tmp_dir.name)
    else:
        base_path = Path(tmp_path)

    try:
        results = []
        for fn in ATTACKS:
            path = base_path / fn.__name__
            if fn in (attack_race_velocity, attack_race_budget):
                results.append(fn(path, trials=trials))
            else:
                results.append(fn(path))
        return results
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()
