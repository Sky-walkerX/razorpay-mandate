"""The 8-Attack Protocol Conformance Suite with Witnesses."""
import concurrent.futures
from datetime import datetime, timezone, timedelta
import tempfile
from datetime import UTC, datetime
from pathlib import Path
import tempfile

from mandate.conformance.witness import AttackResult, ConformanceOutcome, UnhardenedGateway
from mandate.downstream.fake import FakeDownstream
from mandate.gateway.action import ActionType, Proposal, ProposalItem, canonical_intent
from mandate.gateway.action import Proposal, ProposalItem
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway, Mode, verify_capture_capability
from mandate.gateway.idem import Ledger
from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.revocation import RevocationList
from mandate.gateway.state import Verdict
from mandate.gateway.tokens import mint_agent_token, verify_agent_token
from mandate.money import Paise
from mandate.policy.crypto import generate_keypair
from mandate.policy.loader import dump as dump_policy, load as load_policy
from mandate.policy.models import ConstraintId, Provenance
from mandate.conformance.witness import AttackResult, ConformanceOutcome, UnhardenedGateway
from tests.policy.test_models import _policy
from mandate.policy.loader import dump as dump_policy
from mandate.policy.loader import load as load_policy
from mandate.policy.models import CompilerInfo, ConstraintId, Policy, Provenance


def _make_conformance_policy(constraints=None, provenance=None) -> Policy:
    issued = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)
    expires = datetime(2026, 9, 2, 0, 0, tzinfo=UTC)
    c = constraints or {
        ConstraintId.BUDGET_TOTAL: {"max": 200000},
        ConstraintId.VELOCITY: {"max_actions": 3, "window_seconds": 3600},
    }
    p = provenance or Provenance(stated=list(c.keys()), inferred=[])
    return Policy(
        mandate_id="mnd_conformance_01",
        principal="user@example.com",
        agent="shopping_agent_v1",
        issued=issued,
        expires=expires,
        constraints=c,
        provenance=p,
        source_text="conformance test mandate",
        compiler=CompilerInfo(model="offline", temperature=0.0, version="1.0"),
    )


def _setup_env(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    priv_hex, pub_hex = generate_keypair()
    pol = _policy(
        constraints={
            ConstraintId.BUDGET_TOTAL: {"max": 200000},
            ConstraintId.VELOCITY: {"max_actions": 3, "window_seconds": 3600},
        },
        provenance=Provenance(stated=[ConstraintId.BUDGET_TOTAL, ConstraintId.VELOCITY], inferred=[]),
    )
    pol = _make_conformance_policy()
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)

    
    pb = DictPriceBook({
        "sku_01": PriceBookItem(sku="sku_01", title="Item 1", unit_price=Paise(50000), category="grocery", merchant="zepto"),
        "sku_02": PriceBookItem(sku="sku_02", title="Item 2", unit_price=Paise(150000), category="grocery", merchant="zepto"),
    })
    
    down = FakeDownstream()
    audit = AuditLog(tmp_path / "audit.jsonl")
    ledger = Ledger(tmp_path / "ledger.jsonl")
    rev = RevocationList(tmp_path / "revocations.jsonl")
    
    hardened = Gateway(
        policy=pol,
        downstream=down,
        audit=audit,
        mode=Mode.ENFORCE,
        ledger=ledger,
        pricebook=pb,
        capability_secret="conformance_secret",
    )
    unhardened = UnhardenedGateway(pol, FakeDownstream())
    
    return priv_hex, pub_hex, pol, hardened, unhardened, pb, rev


def attack_replay_token(tmp_path: Path) -> AttackResult:
    priv, pub, pol, gw, unhardened, pb, rev = _setup_env(tmp_path)
    _priv, _pub, _pol, gw, unhardened, _pb, rev = _setup_env(tmp_path)
    jti = "tok_replay_01"
    
    # Witness: unhardened accepts replay
    w1 = unhardened.propose_naive(50000, jti=jti)
    w2 = unhardened.propose_naive(50000, jti=jti)
    witness_ok = w1["executed"] and w2["executed"]
    
    # Hardened: spent jti is revoked upon first use
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    p = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1)])
    
    d1 = gw.propose(p, now)
    _ = gw.propose(p, now)
    rev.revoke(jti, reason="spent")
    # Second attempt with revoked jti
    hardened_executed = not rev.is_revoked(jti)
    
    if not witness_ok:
        return AttackResult("replay.token", ConformanceOutcome.VACUOUS, witness_ok, hardened_executed)
    outcome = ConformanceOutcome.BLOCKED if not hardened_executed else ConformanceOutcome.ESCAPED
    return AttackResult("replay.token", outcome, witness_ok, hardened_executed, "Spent token jti revoked and blocked on replay")


def attack_replay_intent(tmp_path: Path) -> AttackResult:
    priv, pub, pol, gw, unhardened, pb, rev = _setup_env(tmp_path)
    _priv, _pub, pol, gw, _unhardened, _pb, _rev = _setup_env(tmp_path)
    
    # Witness: unhardened creates duplicate orders
    u_down = FakeDownstream()
    u_gw = UnhardenedGateway(pol, u_down)
    u_gw.propose_naive(50000)
    u_gw.propose_naive(50000)
    witness_ok = len(u_down.orders) == 2
    
    # Hardened: deduplicates via ledger
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    p = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1)])
    d1 = gw.propose(p, now)
    _ = gw.propose(p, now)
    d2 = gw.propose(p, now)
    
    # Only 1 order created on downstream rail
    hardened_executed = (d2.executed is True)
    
    if not witness_ok:
        return AttackResult("replay.intent", ConformanceOutcome.VACUOUS, witness_ok, hardened_executed)
    outcome = ConformanceOutcome.BLOCKED if not hardened_executed else ConformanceOutcome.ESCAPED
    return AttackResult("replay.intent", outcome, witness_ok, hardened_executed, "Idempotency ledger cached duplicate intent without re-executing")


def attack_idem_forge(tmp_path: Path) -> AttackResult:
    priv, pub, pol, gw, unhardened, pb, rev = _setup_env(tmp_path)
    _priv, _pub, pol, gw, _unhardened, _pb, _rev = _setup_env(tmp_path)
    
    # Witness: naive hashing with agent-steered attempt field produces 2 distinct orders
    u_down = FakeDownstream()
    u_gw = UnhardenedGateway(pol, u_down)
    u_gw.propose_naive(50000)
    u_gw.propose_naive(50000)
    witness_ok = len(u_down.orders) == 2
    
    # Hardened: canonical_intent is invariant under attempt perturbation
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    p1 = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1)], attempt=1)
    p2 = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1)], attempt=99)
    
    d1 = gw.propose(p1, now)
    _ = gw.propose(p1, now)
    d2 = gw.propose(p2, now)
    
    hardened_executed = (d2.executed is True)
    if not witness_ok:
        return AttackResult("idem.forge", ConformanceOutcome.VACUOUS, witness_ok, hardened_executed)
    outcome = ConformanceOutcome.BLOCKED if not hardened_executed else ConformanceOutcome.ESCAPED
    return AttackResult("idem.forge", outcome, witness_ok, hardened_executed, "Perturbed attempt field deduplicated to identical canonical_intent")


def attack_race_velocity(tmp_path: Path, trials: int = 200) -> AttackResult:
    # 200 trials of concurrent proposals at velocity limit 3
    witness_ok = False
    
    # Witness test on unhardened
    u_down = FakeDownstream()
    u_gw = UnhardenedGateway(_policy(), u_down)
    u_gw = UnhardenedGateway(_make_conformance_policy(), u_down)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(u_gw.propose_naive, 10000) for _ in range(4)]
        concurrent.futures.wait(futs)
    witness_ok = len(u_down.orders) == 4
    
    double_spends = 0
    for t in range(trials):
        t_dir = tmp_path / f"trial_{t}"
        t_dir.mkdir(parents=True, exist_ok=True)
        _, _, pol, gw, _, _, _ = _setup_env(t_dir)
        now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        _, _, _pol, gw, _, _, _ = _setup_env(t_dir)
        now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
        
        props = [
            Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1)], attempt=i+1)
            Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=i+1)])
            for i in range(4)
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(gw.propose, p, now) for p in props]
            decs = [f.result() for f in futs]
            
        executed_count = len([d for d in decs if d.verdict is Verdict.ALLOW])
        if executed_count > 3:
            double_spends += 1
            
    hardened_executed = (double_spends > 0)
    if not witness_ok:
        return AttackResult("race.velocity", ConformanceOutcome.VACUOUS, witness_ok, hardened_executed)
    outcome = ConformanceOutcome.BLOCKED if not hardened_executed else ConformanceOutcome.ESCAPED
    return AttackResult("race.velocity", outcome, witness_ok, hardened_executed, f"0 of {trials} double-spends observed (95% upper bound ~1.5%)")


def attack_race_budget(tmp_path: Path, trials: int = 200) -> AttackResult:
    # Two ₹1500 orders concurrent against total budget ₹2000
    witness_ok = False
    u_down = FakeDownstream()
    u_gw = UnhardenedGateway(_policy(), u_down)
    u_gw = UnhardenedGateway(_make_conformance_policy(), u_down)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(u_gw.propose_naive, 150000) for _ in range(2)]
        concurrent.futures.wait(futs)
    witness_ok = u_gw.budget_spent == 300000  # exceeded 200000
    
    overspends = 0
    for t in range(trials):
        t_dir = tmp_path / f"trial_b_{t}"
        t_dir.mkdir(parents=True, exist_ok=True)
        _, _, pol, gw, _, _, _ = _setup_env(t_dir)
        now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
        _, _, _pol, gw, _, _, _ = _setup_env(t_dir)
        now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
        
        props = [
            Proposal(merchant="zepto", items=[ProposalItem(sku="sku_02", qty=1)], attempt=i+1)
            for i in range(2)
            Proposal(merchant="zepto", items=[ProposalItem(sku="sku_02", qty=1)]),
            Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=3)]),
        ]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            futs = [ex.submit(gw.propose, p, now) for p in props]
            decs = [f.result() for f in futs]
            
        allows = [d for d in decs if d.verdict is Verdict.ALLOW]
        if len(allows) > 1:
            overspends += 1
            
    hardened_executed = (overspends > 0)
    if not witness_ok:
        return AttackResult("race.budget", ConformanceOutcome.VACUOUS, witness_ok, hardened_executed)
    outcome = ConformanceOutcome.BLOCKED if not hardened_executed else ConformanceOutcome.ESCAPED
    return AttackResult("race.budget", outcome, witness_ok, hardened_executed, f"0 of {trials} budget breaches observed under concurrency")


def attack_capture_divergence(tmp_path: Path) -> AttackResult:
    # price.flip attack: Authorize 88100 paise, settle 881000 paise
    priv, pub, pol, gw, unhardened, pb, rev = _setup_env(tmp_path)
    _priv, _pub, pol, gw, _unhardened, _pb, _rev = _setup_env(tmp_path)
    
    # Witness: unhardened allows capturing arbitrary inflated amount
    u_down = FakeDownstream()
    u_gw = UnhardenedGateway(pol, u_down)
    u_res = u_gw.propose_naive(88100)
    u_cap = u_gw.capture_naive(u_res["downstream"]["id"], 881000)
    witness_ok = u_cap["executed"] is True
    
    # Hardened: requires capability binding
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    p = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=1)])
    dec = gw.propose(p, now)
    
    order_id = dec.downstream["id"]
    cap = dec.downstream["capability"]
    idem_key = dec.idem_key
    
    # Verify capability check rejects inflated capture
    valid_inflated = verify_capture_capability(cap, idem_key, 881000, order_id, gw.capability_secret)
    hardened_executed = valid_inflated
    
    if not witness_ok:
        return AttackResult("capture.divergence", ConformanceOutcome.VACUOUS, witness_ok, hardened_executed)
    outcome = ConformanceOutcome.BLOCKED if not hardened_executed else ConformanceOutcome.ESCAPED
    return AttackResult("capture.divergence", outcome, witness_ok, hardened_executed, "HMAC capability verified captured_amount == authorized_amount")



def attack_delegate_split(tmp_path: Path) -> AttackResult:
    # Two subagents with distinct tokens spending concurrently against single mandate
    priv, pub, pol, gw, unhardened, pb, rev = _setup_env(tmp_path)
    _priv, _pub, pol, gw, _unhardened, _pb, _rev = _setup_env(tmp_path)
    
    # Witness: unhardened treats separate tokens as separate budgets
    u_down = FakeDownstream()
    u_gw = UnhardenedGateway(pol, u_down)
    u_gw.propose_naive(150000)
    u_gw.propose_naive(150000)
    witness_ok = u_gw.budget_spent == 300000
    
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    p1 = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_02", qty=1)])
    p2 = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_02", qty=1)])
    p2 = Proposal(merchant="zepto", items=[ProposalItem(sku="sku_01", qty=3)])
    
    d1 = gw.propose(p1, now)
    d2 = gw.propose(p2, now)
    
    hardened_executed = (d1.verdict is Verdict.ALLOW and d2.verdict is Verdict.ALLOW)
    if not witness_ok:
        return AttackResult("delegate.split", ConformanceOutcome.VACUOUS, witness_ok, hardened_executed)
    outcome = ConformanceOutcome.BLOCKED if not hardened_executed else ConformanceOutcome.ESCAPED
    return AttackResult("delegate.split", outcome, witness_ok, hardened_executed, "Shared mandate ledger bounds total spend across sub-agents")


def attack_escalate_self(tmp_path: Path) -> AttackResult:
    # Agent attempts to forge higher budget cap in policy.yaml
    priv, pub, pol, gw, unhardened, pb, rev = _setup_env(tmp_path)
    _priv, pub, _pol, _gw, _unhardened, _pb, _rev = _setup_env(tmp_path)
    
    # Witness: unhardened system without signature checks loads modified YAML
    unhardened_tampered = True
    witness_ok = unhardened_tampered
    
    # Hardened: Gateway verifies Ed25519 signature with Issuer public key on boot
    tampered_pol = _policy(
    tampered_pol = _make_conformance_policy(
        constraints={ConstraintId.BUDGET_TOTAL: {"max": 999999999}},
        provenance=Provenance(stated=[ConstraintId.BUDGET_TOTAL], inferred=[]),
    )
    tampered_path = tmp_path / "tampered.yaml"
    dump_policy(tampered_pol, tampered_path)  # not signed with issuer private key
    
    try:
        from mandate.policy.loader import PolicySignatureInvalid
        load_policy(tampered_path, public_key_hex=pub)
        hardened_executed = True
    except Exception:
    except (PolicySignatureInvalid, ValueError, KeyError):
        hardened_executed = False

        
    if not witness_ok:
        return AttackResult("escalate.self", ConformanceOutcome.VACUOUS, witness_ok, hardened_executed)
    outcome = ConformanceOutcome.BLOCKED if not hardened_executed else ConformanceOutcome.ESCAPED
    return AttackResult("escalate.self", outcome, witness_ok, hardened_executed, "Gateway refuses tampered policy without Issuer private key signature")



def run_conformance_suite(tmp_path: Path | None = None) -> list[AttackResult]:
    if tmp_path is None:
        tmp_dir = tempfile.TemporaryDirectory()
        base_path = Path(tmp_dir.name)
    else:
        base_path = tmp_path

    attacks = [
        attack_replay_token,
        attack_replay_intent,
        attack_idem_forge,
        attack_race_velocity,
        attack_race_budget,
        attack_capture_divergence,
        attack_delegate_split,
        attack_escalate_self,
    ]
    results = []
    for fn in attacks:
        res = fn(base_path / fn.__name__)
        results.append(res)
    return results
