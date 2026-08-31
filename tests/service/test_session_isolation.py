"""Tests for per-session isolation and token pool management on the HTTP gateway."""
from datetime import UTC, datetime, timedelta

from starlette.testclient import TestClient

from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.tokens import mint_agent_token
from mandate.money import Paise
from mandate.policy.crypto import generate_keypair
from mandate.policy.loader import dump as dump_policy
from mandate.service.server import create_app
from mandate.service.token_pool import TokenPool
from tests.policy.test_models import _policy


def _setup_service(tmp_path, token_count=5):
    priv_hex, pub_hex = generate_keypair()
    pol = _policy()
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)
    
    pub_path = tmp_path / "issuer_public.key"
    pub_path.write_text(pub_hex + "\n")
    
    pb = DictPriceBook({
        "sku_dal": PriceBookItem(
            sku="sku_dal",
            title="Toor Dal 1kg",
            unit_price=Paise(80000),  # Rs 800
            category="grocery",
            merchant="zepto",
        ),
        "sku_oil": PriceBookItem(
            sku="sku_oil",
            title="Mustard Oil 1L",
            unit_price=Paise(80000),  # Rs 800
            category="grocery",
            merchant="zepto",
        ),
        "sku_rice": PriceBookItem(
            sku="sku_rice",
            title="Basmati Rice 1kg",
            unit_price=Paise(80000),  # Rs 800
            category="grocery",
            merchant="zepto",
        ),
        "sku_cheap": PriceBookItem(
            sku="sku_cheap",
            title="Matchbox",
            unit_price=Paise(5000),   # Rs 50
            category="grocery",
            merchant="zepto",
        )
    })
    
    # Pre-mint tokens
    exp = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    raw_tokens = [
        mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti=f"tok_iso_{i:02d}")
        for i in range(1, token_count + 1)
    ]
    pool = TokenPool(raw_tokens)
    
    app = create_app(
        policy_path=pol_path,
        public_key_path=pub_path,
        revocations_path=tmp_path / "revocations.jsonl",
        audit_path=tmp_path / "audit.jsonl",
        ledger_path=tmp_path / "ledger.jsonl",
        pricebook=pb,
        capability_secret="test_secret_session_isolation_2026",
        token_pool=pool,
    )
    return TestClient(app), pool, pol


def test_session_isolation_budget_exhaustion(tmp_path):
    client, _pool, _pol = _setup_service(tmp_path)
    
    # 1. Claim session A
    res_a = client.post("/v1/sessions")
    assert res_a.status_code == 200
    tok_a = res_a.json()["token"]
    
    # 2. Claim session B
    res_b = client.post("/v1/sessions")
    assert res_b.status_code == 200
    tok_b = res_b.json()["token"]
    
    hdr_a = {"Authorization": f"Bearer {tok_a}"}
    hdr_b = {"Authorization": f"Bearer {tok_b}"}
    
    # Session A spends 3 x Rs 800 = Rs 2,400 (cap is Rs 2,000)
    # Order 1: Rs 800 (dal) -> ALLOW
    r1 = client.post("/v1/orders", json={"merchant": "zepto", "items": [{"sku": "sku_dal", "qty": 1}]}, headers=hdr_a)
    assert r1.status_code == 200 and r1.json()["verdict"] == "ALLOW"
    
    # Order 2: Rs 800 (oil) -> ALLOW (total Rs 1,600)
    r2 = client.post("/v1/orders", json={"merchant": "zepto", "items": [{"sku": "sku_oil", "qty": 1}]}, headers=hdr_a)
    assert r2.status_code == 200 and r2.json()["verdict"] == "ALLOW"
    
    # Order 3: Rs 800 (rice) -> DENY (would be Rs 2,400, over Rs 2,000)
    r3 = client.post("/v1/orders", json={"merchant": "zepto", "items": [{"sku": "sku_rice", "qty": 1}]}, headers=hdr_a)
    assert r3.status_code == 200 and r3.json()["verdict"] == "DENY"
    assert r3.json()["clause_id"] == "budget.total"
    
    # Session B starts fresh! Order 1: Rs 800 -> MUST ALLOW
    rb1 = client.post("/v1/orders", json={"merchant": "zepto", "items": [{"sku": "sku_dal", "qty": 1}]}, headers=hdr_b)
    assert rb1.status_code == 200 and rb1.json()["verdict"] == "ALLOW"
    assert rb1.json()["executed"] is True


def test_session_revocation_isolation(tmp_path):
    client, _pool, _pol = _setup_service(tmp_path)
    
    res_a = client.post("/v1/sessions")
    tok_a = res_a.json()["token"]
    res_a.json()["jti"]
    
    res_b = client.post("/v1/sessions")
    tok_b = res_b.json()["token"]
    
    hdr_a = {"Authorization": f"Bearer {tok_a}"}
    hdr_b = {"Authorization": f"Bearer {tok_b}"}
    
    # Revoke session A
    rev_res = client.post("/v1/revoke", headers=hdr_a)
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "revoked"
    
    # Session A is immediately rejected with 403
    r_a = client.post("/v1/orders", json={"merchant": "zepto", "items": [{"sku": "sku_cheap", "qty": 1}]}, headers=hdr_a)
    assert r_a.status_code == 403
    assert r_a.json()["error"] == "token_revoked"
    
    # Session B is completely unaffected!
    r_b = client.post("/v1/orders", json={"merchant": "zepto", "items": [{"sku": "sku_cheap", "qty": 1}]}, headers=hdr_b)
    assert r_b.status_code == 200 and r_b.json()["verdict"] == "ALLOW"


def test_pool_exhaustion_returns_503(tmp_path):
    client, _pool, _pol = _setup_service(tmp_path, token_count=2)
    
    # Claim 1
    r1 = client.post("/v1/sessions")
    assert r1.status_code == 200
    
    # Claim 2
    r2 = client.post("/v1/sessions")
    assert r2.status_code == 200
    
    # Claim 3 -> pool exhausted (503)
    r3 = client.post("/v1/sessions")
    assert r3.status_code == 503
    assert r3.json()["error"] == "token_pool_exhausted"
