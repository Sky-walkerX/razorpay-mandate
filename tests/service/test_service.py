"""Tests for the standalone gateway service daemon over HTTP."""
from datetime import UTC, datetime, timedelta

from starlette.testclient import TestClient

from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.tokens import mint_agent_token
from mandate.money import Paise
from mandate.policy.crypto import generate_keypair
from mandate.policy.loader import dump as dump_policy
from mandate.service.server import create_app
from tests.policy.test_models import _policy


def test_gateway_service_authenticated_order_and_capture(tmp_path):
    priv_hex, pub_hex = generate_keypair()
    pol = _policy()
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)
    
    pub_path = tmp_path / "issuer_public.key"
    pub_path.write_text(pub_hex + "\n")
    
    pb = DictPriceBook({
        "sku_tea": PriceBookItem(
            sku="sku_tea",
            title="Assam Tea 500g",
            unit_price=Paise(25000),
            category="grocery",
            merchant="zepto",
        )
    })
    
    app = create_app(
        policy_path=pol_path,
        public_key_path=pub_path,
        revocations_path=tmp_path / "revocations.jsonl",
        audit_path=tmp_path / "audit.jsonl",
        ledger_path=tmp_path / "ledger.jsonl",
        pricebook=pb,
        capability_secret="test_secret_42",
    )
    
    client = TestClient(app)
    
    # 1. Health check
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
    
    # 2. Unauthenticated request rejected with 401
    bad_res = client.post("/v1/orders", json={"merchant": "zepto", "items": [{"sku": "sku_tea", "qty": 1}]})
    assert bad_res.status_code == 401
    
    # 3. Mint valid bearer token
    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    token = mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti="tok_valid_01")
    
    headers = {"Authorization": f"Bearer {token}"}
    order_res = client.post("/v1/orders", json={"merchant": "zepto", "items": [{"sku": "sku_tea", "qty": 1}]}, headers=headers)
    assert order_res.status_code == 200
    data = order_res.json()
    assert data["verdict"] == "ALLOW"
    assert data["executed"] is True
    assert data["downstream"]["amount"] == 25000
    assert "capability" in data["downstream"]
    
    cap = data["downstream"]["capability"]
    order_id = data["downstream"]["id"]
    idem_key = data["idem_key"]
    
    # 4. Attempt capture divergence (price.flip): trying to settle 250000 instead of authorized 25000
    divergent_capture = client.post(
        "/v1/payments/capture",
        json={"order_id": order_id, "amount": 250000, "capability": cap, "idem_key": idem_key},
        headers=headers,
    )
    assert divergent_capture.status_code == 403
    assert divergent_capture.json()["error"] == "invalid_capture_capability"
    
    # 5. Legitimate capture with exact authorized amount
    good_capture = client.post(
        "/v1/payments/capture",
        json={"order_id": order_id, "amount": 250000 // 10, "capability": cap, "idem_key": idem_key},
        headers=headers,
    )
    assert good_capture.status_code == 200
    assert good_capture.json()["status"] == "captured"
