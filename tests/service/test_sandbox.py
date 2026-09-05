"""The bring-your-own-mandate sandbox.

Two properties carry this feature, and they pull in opposite directions.

It has to really enforce what a visitor typed — a demo that compiles their words
for display and then refuses on the house policy's limits is a puppet show, and
it would look identical from the outside. So one test drives a proposal past a
cap that exists only in the visitor's sentence and reads the clause back.

And it must not weaken the boundary to do it. `Gateway._verify_token` binds a
token to one mandate id, and the temptation is to relax that so any token opens
any session. Nothing here relaxes it: sandbox tokens are minted offline against
a reserved mandate id, and the cross-binding test asserts the check still bites
in both directions.
"""
import json
from datetime import UTC, datetime, timedelta

from starlette.testclient import TestClient

from mandate.gateway.pricebook import DictPriceBook
from mandate.gateway.tokens import mint_agent_token
from mandate.harness.catalog import generate_catalog
from mandate.policy.crypto import generate_keypair
from mandate.policy.loader import dump as dump_policy
from mandate.policy.models import ConstraintId, Provenance
from mandate.policy.regulatory import REGULATORY_FLOOR
from mandate.service.sandbox import (
    SANDBOX_JTI_PREFIX,
    SANDBOX_MANDATE_ID,
    to_sandbox_policy,
)
from mandate.service.server import create_app
from mandate.service.token_pool import TokenPool
from tests.policy.test_models import _policy

# A visitor's sentence, compiled. The per-transaction cap is ₹300, well under the
# house policy's ₹1,000, so any order between the two proves which policy is
# actually deciding.
JUDGE_READING = {
    "constraints": {
        "budget.total": {"max": 50000},
        "budget.per_transaction": {"max": 30000},
        "category.deny": ["alcohol"],
    },
    "provenance": {
        "stated": ["budget.total", "budget.per_transaction", "category.deny"],
        "inferred": [],
    },
    "questions": [],
}


class ScriptedCompiler:
    """A provider that returns one fixed reading. `compile_intent` asks twice and
    refuses if the two disagree, so returning the same object passes that check."""

    model = "scripted-test"

    def __init__(self, reading=None, readings=None):
        self._readings = list(readings) if readings else None
        self._reading = reading if reading is not None else JUDGE_READING

    def next_text(self, system, history):
        if self._readings:
            return json.dumps(self._readings.pop(0))
        return json.dumps(self._reading)


def _app(tmp_path, monkeypatch, provider=None, sandbox_tokens=2, house_tokens=1):
    tmp_path.mkdir(parents=True, exist_ok=True)
    catalog = generate_catalog(seed=42)
    priv_hex, pub_hex = generate_keypair()
    # The house policy needs a per-transaction cap for the separation to mean
    # anything: the visitor's is Rs 300 and this is Rs 1,000, so an order between
    # them is refused by exactly one of the two and the clause says which.
    pol = _policy(
        constraints={
            ConstraintId.BUDGET_TOTAL: {"max": 200000},
            ConstraintId.BUDGET_PER_TRANSACTION: {"max": 100000},
        },
        provenance=Provenance(
            stated=[ConstraintId.BUDGET_TOTAL, ConstraintId.BUDGET_PER_TRANSACTION],
            inferred=[],
        ),
    )
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)
    pub_path = tmp_path / "issuer_public.key"
    pub_path.write_text(pub_hex + "\n")

    monkeypatch.setattr(
        "mandate.llm.provider_for", lambda *a, **k: provider or ScriptedCompiler()
    )

    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    sbx = TokenPool([
        mint_agent_token(
            SANDBOX_MANDATE_ID, priv_hex, expires_iso=exp,
            jti=f"{SANDBOX_JTI_PREFIX}_{i:03d}",
        )
        for i in range(1, sandbox_tokens + 1)
    ])
    main = TokenPool([
        mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti=f"tok_pool_{i:03d}")
        for i in range(1, house_tokens + 1)
    ])

    app = create_app(
        policy_path=pol_path, public_key_path=pub_path,
        revocations_path=tmp_path / "revocations.jsonl",
        audit_path=tmp_path / "audit.jsonl", ledger_path=tmp_path / "ledger.jsonl",
        pricebook=DictPriceBook.from_catalog(catalog),
        capability_secret="test_secret_42", catalog=catalog,
        token_pool=main, sandbox_pool=sbx,
    )
    return TestClient(app), pol, catalog, priv_hex


def test_the_sandbox_enforces_the_visitors_cap_and_not_the_house_one(tmp_path, monkeypatch):
    """The test the whole feature rests on.

    ₹300 is the visitor's per-transaction cap and ₹1,000 is the signed policy's.
    An order between the two must be refused, and refused on the visitor's number,
    or the page is enforcing the house mandate while claiming otherwise.
    """
    client, pol, catalog, _ = _app(tmp_path, monkeypatch)
    house_cap = int(pol.constraints["budget.per_transaction"]["max"])
    assert house_cap > 30000, "fixture no longer separates the two caps"

    sbx = client.post("/v1/sandbox", json={"prompt": "Spend at most Rs 300 an order"}).json()
    assert sbx["compiled"] is True

    # A basket that costs more than ₹300 and less than the house cap.
    target = next(
        p for p in catalog.products
        if 30000 < int(p.unit_price) < house_cap and p.category != "alcohol"
    )
    r = client.post(
        "/v1/orders",
        json={"merchant": target.merchant, "items": [{"sku": target.sku, "qty": 1}]},
        headers={"Authorization": f"Bearer {sbx['token']}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    dec = body["decision"]
    assert dec["verdict"] == "DENY"
    assert dec["clause_id"] == "budget.per_transaction"

    # And it is the visitor's number in the refusal, not the house's.
    clause = next(
        c for c in body["record"]["clauses"] if c["id"] == "budget.per_transaction"
    )
    assert int(clause["limit"]) == 30000, "the refusal quoted the house cap"

    # The meter a judge watches has to agree with the clause that refused them.
    per_txn = next(
        h for h in body["headroom"] if h["clause_id"] == "budget.per_transaction"
    )
    assert per_txn["limit_paise"] == 30000


def test_a_sandbox_policy_is_never_the_signed_one(tmp_path, monkeypatch):
    client, pol, _, _ = _app(tmp_path, monkeypatch)
    sbx = client.post("/v1/sandbox", json={"prompt": "Spend at most Rs 300 an order"}).json()
    assert sbx["mandate_id"] == SANDBOX_MANDATE_ID
    assert sbx["mandate_id"] != pol.mandate_id
    assert sbx["signed"] is False
    assert sbx["policy_hash"] != client.get("/health").json()["policy_hash"]


def test_the_response_says_where_a_policy_would_be_signed(tmp_path, monkeypatch):
    """"We cannot sign this here" is half an answer. The other half is the offline
    command, because the gateway refusing to sign is the feature and a visitor has
    to be able to see what the real path looks like."""
    client, _, _, _ = _app(tmp_path, monkeypatch)
    sbx = client.post("/v1/sandbox", json={"prompt": "Spend at most Rs 300"}).json()
    assert "mandate sign" in sbx["sign_command"]


def test_a_house_token_cannot_serve_a_sandbox_session(tmp_path, monkeypatch):
    """The binding check is not relaxed for the sandbox. A token bound to the
    signed mandate, presented against a sandbox session's jti, is refused."""
    client, pol, catalog, priv_hex = _app(tmp_path, monkeypatch)
    sbx = client.post("/v1/sandbox", json={"prompt": "Spend at most Rs 300"}).json()

    # Same jti as the live sandbox session, but bound to the signed mandate.
    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    forged = mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti=sbx["jti"])
    target = catalog.products[0]
    r = client.post(
        "/v1/orders",
        json={"merchant": target.merchant, "items": [{"sku": target.sku, "qty": 1}]},
        headers={"Authorization": f"Bearer {forged}"},
    )
    body = r.json()
    rejected = r.status_code >= 400 or body.get("decision", {}).get("verdict") == "DENY"
    assert rejected, "a signed-mandate token served a sandbox session"


def test_a_sandbox_token_cannot_serve_the_house_session(tmp_path, monkeypatch):
    """And the other direction, which is the one that would actually cost money:
    a sandbox token must not reach the signed mandate's gateway."""
    client, _pol, catalog, priv_hex = _app(tmp_path, monkeypatch)
    house = client.post("/v1/sessions").json()

    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    forged = mint_agent_token(
        SANDBOX_MANDATE_ID, priv_hex, expires_iso=exp, jti=house["jti"]
    )
    target = catalog.products[0]
    r = client.post(
        "/v1/orders",
        json={"merchant": target.merchant, "items": [{"sku": target.sku, "qty": 1}]},
        headers={"Authorization": f"Bearer {forged}"},
    )
    body = r.json()
    rejected = r.status_code >= 400 or body.get("decision", {}).get("verdict") == "DENY"
    assert rejected, "a sandbox token reached the signed mandate's gateway"


def test_with_no_sandbox_pool_the_endpoint_refuses_rather_than_falling_back(
    tmp_path, monkeypatch
):
    """`/v1/compile` falls back to the signed policy when it cannot compile,
    because its job is to render something. This endpoint's job is to enforce
    something, and falling back would enforce the house mandate while the page
    said it was testing the visitor's. It reports unavailable instead."""
    client, pol, _, _ = _app(tmp_path, monkeypatch, sandbox_tokens=0)
    r = client.post("/v1/sandbox", json={"prompt": "Spend at most Rs 300"})
    assert r.status_code == 503
    assert pol.mandate_id not in r.text


def test_a_compiler_that_will_not_commit_is_reported_not_papered_over(
    tmp_path, monkeypatch
):
    """Two readings at temperature 0 that disagree make the compiler decline. That
    is the determinism check working, so it comes back as `compiled: false` with a
    reason rather than as a session enforcing a coin flip."""
    other = json.loads(json.dumps(JUDGE_READING))
    other["constraints"]["budget.per_transaction"]["max"] = 90000
    provider = ScriptedCompiler(readings=[JUDGE_READING, other])
    client, _, _, _ = _app(tmp_path, monkeypatch, provider=provider)

    body = client.post("/v1/sandbox", json={"prompt": "spend a bit"}).json()
    assert body["compiled"] is False
    assert body["reason"]
    # The three ways this comes back empty mean opposite things, and the page
    # explains them differently. A decline will repeat on the same words; a
    # timeout says nothing about the intent at all.
    assert body["kind"] == "declined"


def test_an_empty_prompt_is_refused(tmp_path, monkeypatch):
    client, _, _, _ = _app(tmp_path, monkeypatch)
    assert client.post("/v1/sandbox", json={"prompt": "   "}).status_code == 400


def test_the_sandbox_keeps_the_visitors_own_words(tmp_path, monkeypatch):
    """`source_text` is what they typed. Rewriting it would make the read-back a
    paraphrase of the demo rather than a reading of them."""
    client, _, _, _ = _app(tmp_path, monkeypatch)
    prompt = "Spend at most Rs 300 an order, nothing alcoholic"
    sbx = client.post("/v1/sandbox", json={"prompt": prompt}).json()
    assert sbx["source_text"] == prompt


def test_to_sandbox_policy_changes_identity_and_nothing_else():
    """Only the mandate id moves. The clauses, the provenance and the sentence are
    the visitor's, and rewriting any of them would be enforcing something they did
    not ask for while showing them what they did."""
    pol = _policy()
    sbx = to_sandbox_policy(pol)
    assert sbx.mandate_id == SANDBOX_MANDATE_ID
    assert sbx.constraints == pol.constraints
    assert sbx.provenance == pol.provenance
    assert sbx.source_text == pol.source_text
    assert sbx.expires == pol.expires


def test_the_two_pools_cannot_share_a_jti_namespace():
    """`SessionManager.create_session` rmtree's `base_dir / jti` before building.
    Two pools sharing a jti would therefore delete a live session's audit chain,
    not merely confuse the lookup, so the prefixes must differ."""
    assert SANDBOX_JTI_PREFIX != "tok_pool"


def test_the_shipped_pools_are_disjoint_and_bound_to_different_mandates():
    """The files that actually get baked into the image."""
    import base64
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    main_p = root / ".mandate/token_pool.json"
    sbx_p = root / ".mandate/sandbox_pool.json"
    if not (main_p.exists() and sbx_p.exists()):
        return  # pools are generated artefacts; nothing to check in a bare checkout

    def claims(path):
        out = []
        for tok in json.loads(path.read_text()):
            body = tok.split(".")[0]
            body += "=" * (-len(body) % 4)
            out.append(json.loads(base64.urlsafe_b64decode(body)))
        return out

    main, sbx = claims(main_p), claims(sbx_p)
    assert not ({c["jti"] for c in main} & {c["jti"] for c in sbx})
    assert {c["mandate_id"] for c in sbx} == {SANDBOX_MANDATE_ID}
    assert SANDBOX_MANDATE_ID not in {c["mandate_id"] for c in main}


class BrokenCompiler:
    """Stands in for the compiler being unreachable, which is not hypothetical:
    the deployed service ran for days with no Vertex project and then with no
    Vertex permission."""

    model = "scripted-test"

    def next_text(self, system, history):
        raise RuntimeError("403 PERMISSION_DENIED on aiplatform.endpoints.predict")


def test_compile_does_not_answer_with_a_policy_it_did_not_compile(tmp_path, monkeypatch):
    """`/v1/compile` used to return the signed policy's own clauses when the
    compiler failed, flagged `fallback: true` and otherwise identical to a real
    compile. Nothing read the flag, so a live outage looked like a working feature
    for days. It must not borrow those clauses again.
    """
    client, pol, _, _ = _app(tmp_path, monkeypatch, provider=BrokenCompiler())
    r = client.post("/v1/compile", json={"prompt": "under Rs 500 an order"})

    assert r.status_code == 502
    body = r.json()
    assert body["compiled"] is False
    assert body["reason"]
    # The specific failure: no clause list, and not the signed mandate's identity.
    assert "constraints" not in body
    assert pol.mandate_id not in json.dumps(body.get("constraints", []))
    assert body.get("mandate_id") != pol.mandate_id


def test_compile_still_answers_normally_when_the_compiler_works(tmp_path, monkeypatch):
    """The honest-failure change must not have broken the path that works."""
    client, pol, _, _ = _app(tmp_path, monkeypatch)
    body = client.post("/v1/compile", json={"prompt": "under Rs 300 an order"}).json()
    assert body["compiled"] is True
    assert body["fallback"] is False
    ids = {c["id"] for c in body["constraints"]}
    # Everything the compiler heard, plus the floor a regulator requires and the
    # compiler never emits. The floor is not the user's to decline, so a compiled
    # mandate carries it whether or not the prompt mentioned it.
    assert set(JUDGE_READING["constraints"]) <= ids
    assert {str(c) for c in REGULATORY_FLOOR} <= ids
    assert body["mandate_id"] != pol.mandate_id


def _session_manager_of(app):
    from mandate.service.session import SessionManager

    managers = [
        c.cell_contents
        for route in app.routes
        for c in (getattr(route.endpoint, "__closure__", None) or ())
        if isinstance(c.cell_contents, SessionManager)
    ]
    assert managers, "no SessionManager reachable from the routes"
    return managers[0]


def test_the_session_cap_never_binds_before_the_token_pools_do(tmp_path, monkeypatch):
    """House and sandbox sessions share one session budget, and the cap evicts the
    least recently active when it is reached. A cap below the total mintable tokens
    would throw a judge out mid-demo because *other* people had claimed tokens —
    they would see `session_not_found` and read it as the gateway breaking.

    The pools here deliberately exceed the 100 floor, so this exercises the sizing
    rather than passing on the default.
    """
    client, _pol, _, _ = _app(tmp_path, monkeypatch, house_tokens=120, sandbox_tokens=60)
    mgr = _session_manager_of(client.app)
    assert mgr.max_sessions >= 180, (
        f"cap {mgr.max_sessions} is below the 180 tokens that can be claimed"
    )


def test_the_floor_still_applies_when_no_pools_are_configured(tmp_path, monkeypatch):
    """Sizing to the pools must not shrink the cap to zero for a service that runs
    without them, which is how every test in this suite and the local daemon run."""
    client, _pol, _, _ = _app(tmp_path, monkeypatch, house_tokens=1, sandbox_tokens=1)
    assert _session_manager_of(client.app).max_sessions >= 100
