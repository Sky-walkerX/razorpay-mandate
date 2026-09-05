"""The TypeScript port must agree with Python byte for byte.

`record_hash` is `sha256(json.dumps(body, sort_keys=True, default=str))`, and a
browser recomputing it has to produce the identical string. Two things make a naive
`JSON.stringify` wrong, and a fixture that does not contain both passes while the
port is broken:

  - Python separates with ", " and ": "; JSON.stringify uses no spaces.
  - Python escapes non-ASCII to \\uXXXX; JSON.stringify passes it through. A real
    rail.divergence record carries a rupee sign in its clause detail.

So the fixture below deliberately carries a rupee sign, a null, a nested list, an
empty container and an astral character. Node runs the TypeScript directly; v22+
strips types natively.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from mandate.gateway.audit import _hash_body
from mandate.gateway.merkle import inclusion_proof, leaf_hash, merkle_tree_hash

REPO = Path(__file__).resolve().parents[1]
WEB_LIB = REPO / "web" / "src" / "lib"

# Each of these exists to break a specific shortcut in the port.
BODIES = [
    {"seq": 1, "amount": 9500, "merchant": "zepto", "voided": None},
    # The rupee sign. Python writes ₹, JSON.stringify writes the character.
    {"detail": "rail amount ₹85.00 diverges from authorised ₹8.50"},
    # Key order: insertion order here is deliberately not sorted order.
    {"zeta": 1, "alpha": 2, "Mid": 3, "_under": 4},
    # Nested containers, an empty one of each, and a bool.
    {"items": [{"sku": "a", "qty": 2}, {"sku": "b", "qty": 1}], "none": [], "map": {},
     "executed": True},
    # Control characters and a quote, which have named escapes in both languages.
    {"detail": 'line\nbreak\ttab "quoted" back\\slash'},
    # Above the BMP: Python emits a surrogate pair, and so must the port.
    {"note": "receipt \U0001f9fe ok"},
]


def _node() -> str:
    exe = shutil.which("node")
    if exe is None:
        pytest.skip("node is not installed; the TypeScript port cannot be checked")
    return exe


def _run_node(script: str, payload: str) -> str:
    scratch = REPO / "web" / "src" / "lib" / "__parity_check.mts"
    scratch.write_text(script, encoding="utf-8")
    try:
        proc = subprocess.run(
            [_node(), str(scratch)],
            input=payload, capture_output=True, text=True, timeout=60, check=False,
        )
    finally:
        scratch.unlink(missing_ok=True)
    if proc.returncode != 0:
        pytest.fail(f"node failed:\n{proc.stderr}")
    return proc.stdout.strip()


def test_the_typescript_canonicaliser_matches_python_byte_for_byte():
    script = """
import { pythonJsonDumps } from './canonical.ts';
let raw = '';
process.stdin.on('data', (c) => { raw += c; });
process.stdin.on('end', () => {
  const bodies = JSON.parse(raw);
  console.log(JSON.stringify(bodies.map(pythonJsonDumps)));
});
"""
    got = json.loads(_run_node(script, json.dumps(BODIES)))
    want = [json.dumps(b, sort_keys=True, default=str) for b in BODIES]

    for i, (g, w) in enumerate(zip(got, want, strict=True)):
        assert g == w, f"body {i} diverged:\n  python: {w!r}\n  node:   {g!r}"


def test_the_typescript_record_hash_matches_the_stored_one():
    """The hash, not just the string. This is what a tamper check compares."""
    script = """
import { recordHash } from './merkle.ts';
let raw = '';
process.stdin.on('data', (c) => { raw += c; });
process.stdin.on('end', async () => {
  const bodies = JSON.parse(raw);
  const out = [];
  for (const b of bodies) out.push(await recordHash(b));
  console.log(JSON.stringify(out));
});
"""
    got = json.loads(_run_node(script, json.dumps(BODIES)))
    want = [_hash_body(b) for b in BODIES]
    assert got == want


def test_the_typescript_verifier_accepts_a_real_proof_and_rejects_a_tampered_leaf():
    """Proof shape and the fn/sn walk, over tree sizes that exercise odd splits."""
    leaves = [leaf_hash(f"record-{i}") for i in range(1, 12)]
    cases = []
    for size in (1, 2, 3, 5, 8, 11):
        subset = leaves[:size]
        root = merkle_tree_hash(subset)
        for index in range(size):
            cases.append({
                "leaf": subset[index],
                "index": index,
                "treeSize": size,
                "proof": inclusion_proof(index, subset),
                "root": root,
            })

    script = """
import { verifyInclusionProof } from './merkle.ts';
let raw = '';
process.stdin.on('data', (c) => { raw += c; });
process.stdin.on('end', async () => {
  const cases = JSON.parse(raw);
  const out = [];
  for (const c of cases) {
    const good = await verifyInclusionProof(c.leaf, c.index, c.treeSize, c.proof, c.root);
    // Same proof, one bit of the root flipped: must not verify.
    const flipped = c.root.slice(0, -1) + (c.root.endsWith('0') ? '1' : '0');
    const bad = await verifyInclusionProof(c.leaf, c.index, c.treeSize, c.proof, flipped);
    out.push([good, bad]);
  }
  console.log(JSON.stringify(out));
});
"""
    got = json.loads(_run_node(script, json.dumps(cases)))
    assert len(got) == len(cases)
    for (good, bad), case in zip(got, cases, strict=True):
        assert good is True, f"valid proof rejected at index {case['index']}/{case['treeSize']}"
        assert bad is False, f"tampered root accepted at index {case['index']}/{case['treeSize']}"


def test_the_browser_verifier_checks_a_real_gateway_receipt_and_catches_a_tamper():
    """End to end against the real endpoints, in the shapes the browser receives.

    The unit fixtures above prove the port. This proves the integration: a receipt
    the gateway actually wrote, its real inclusion proof, and its real signed head,
    verified by the same TypeScript the page runs -- and then the same receipt with
    one field edited, which must stop reaching the root.
    """
    import tempfile
    from datetime import UTC, datetime, timedelta

    from starlette.testclient import TestClient

    from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
    from mandate.gateway.tokens import mint_agent_token
    from mandate.money import Paise
    from mandate.policy.crypto import generate_keypair
    from mandate.policy.loader import dump as dump_policy
    from mandate.service.server import create_app
    from tests.policy.test_models import _policy

    work = Path(tempfile.mkdtemp())
    priv, pub = generate_keypair()
    pol = _policy()
    pol_path = work / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv)
    (work / "pub.key").write_text(pub + "\n")
    log_priv, log_pub = generate_keypair()
    (work / "log.key").write_text(log_priv + "\n")

    pb = DictPriceBook({
        "sku_tea": PriceBookItem(sku="sku_tea", title="Assam Tea 500g",
                                 unit_price=Paise(25000), category="grocery",
                                 merchant="zepto")
    })
    app = create_app(
        policy_path=pol_path, public_key_path=work / "pub.key",
        revocations_path=work / "rev.jsonl", audit_path=work / "a.jsonl",
        ledger_path=work / "l.jsonl", pricebook=pb, capability_secret="s3cret",
        log_private_key_path=work / "log.key",
    )
    client = TestClient(app)
    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    headers = {"Authorization": f"Bearer {mint_agent_token(pol.mandate_id, priv, expires_iso=exp, jti='tok_ts_01')}"}

    for qty in (1, 2, 3):
        client.post("/v1/orders",
                    json={"merchant": "zepto", "items": [{"sku": "sku_tea", "qty": qty}]},
                    headers=headers)

    head = client.get("/v1/audit/head", headers=headers).json()
    records = client.get("/v1/audit", headers=headers).json()["records"]
    assert len(records) >= 2, "need a tree deeper than one leaf to exercise the walk"
    target = records[1]
    proof = client.get(f"/v1/audit/proof?seq={target['seq']}", headers=headers).json()

    payload = json.dumps({
        "head": head, "record": target, "proof": proof, "logPublicKey": log_pub,
    })

    script = """
import { verifyTreeHead, recordHash, leafHash, nodeHash } from './merkle.ts';

async function climb(leaf, seq, treeSize, proof) {
  let current = await leafHash(leaf);
  let fn = seq - 1, sn = treeSize - 1;
  for (const s of proof) {
    if (sn === 0) break;
    if (fn % 2 === 1 || fn === sn) {
      current = await nodeHash(s.node, current);
      while (fn !== 0 && fn % 2 === 0) { fn = Math.floor(fn / 2); sn = Math.floor(sn / 2); }
    } else {
      current = await nodeHash(current, s.node);
    }
    fn = Math.floor(fn / 2); sn = Math.floor(sn / 2);
  }
  return { root: current, done: sn === 0 };
}

let raw = '';
process.stdin.on('data', (c) => { raw += c; });
process.stdin.on('end', async () => {
  const { head, record, proof, logPublicKey } = JSON.parse(raw);
  const headOk = await verifyTreeHead(head, logPublicKey);
  const headWrongKey = await verifyTreeHead(head, '00'.repeat(32));

  const honest = await recordHash(record);
  const honestClimb = await climb(honest, proof.seq, proof.tree_size, proof.proof);

  const edited = { ...record, action: { ...record.action, amount: 1 } };
  const tamperedHash = await recordHash(edited);
  const tamperedClimb = await climb(tamperedHash, proof.seq, proof.tree_size, proof.proof);

  console.log(JSON.stringify({
    headOk,
    headWrongKey,
    leafMatches: honest === proof.leaf_record_hash,
    reachesRoot: honestClimb.done && honestClimb.root === head.root,
    tamperedLeafDiffers: tamperedHash !== proof.leaf_record_hash,
    tamperedReachesRoot: tamperedClimb.done && tamperedClimb.root === head.root,
  }));
});
"""
    got = json.loads(_run_node(script, payload))
    assert got["headOk"] is True, "the browser could not verify a head the gateway signed"
    assert got["headWrongKey"] is False, "a head verified against the wrong key"
    assert got["leafMatches"] is True, "recomputed record hash differs from the published leaf"
    assert got["reachesRoot"] is True, "an honest receipt did not reach the signed root"
    assert got["tamperedLeafDiffers"] is True, "editing the amount did not change the hash"
    assert got["tamperedReachesRoot"] is False, "a tampered receipt still reached the root"
