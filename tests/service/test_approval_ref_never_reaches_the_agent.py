from datetime import UTC, datetime, timedelta
from pathlib import Path

from starlette.testclient import TestClient

from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.tokens import mint_agent_token
from mandate.money import Paise
from mandate.policy.crypto import generate_keypair
from mandate.policy.loader import dump as dump_policy
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Provenance
from mandate.service.server import create_app
from tests.policy.test_models import IST, _policy


def test_approval_ref_never_reaches_the_agent_and_enables_oob_approval(tmp_path: Path):
    priv_hex, pub_hex = generate_keypair()
    # Threshold ₹1,000 (100000 paise), Total budget ₹5,000 (500000 paise)
    pol = _policy(
        constraints={
            C.BUDGET_TOTAL: {"max": 500000},
            C.AFA_REQUIRED: {"threshold": 100000},
        },
        provenance=Provenance(
            stated=[C.BUDGET_TOTAL],
            inferred=[],
            regulatory=[C.AFA_REQUIRED],
        ),
        expires=datetime.now(IST) + timedelta(days=2),
    )
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)

    pub_path = tmp_path / "issuer_public.key"
    pub_path.write_text(pub_hex + "\n")

    pb = DictPriceBook({
        "sku_costly": PriceBookItem(
            sku="sku_costly",
            title="Premium Olive Oil 5L",
            unit_price=Paise(150000),  # ₹1,500
            category="grocery",
            merchant="blinkit",
        )
    })

    app = create_app(
        policy_path=pol_path,
        public_key_path=pub_path,
        revocations_path=tmp_path / "revocations.jsonl",
        audit_path=tmp_path / "audit.jsonl",
        ledger_path=tmp_path / "ledger.jsonl",
        pricebook=pb,
        capability_secret="secret_test_42",
    )

    client = TestClient(app)

    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    token = mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti="tok_agent_afa")
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Agent submits proposal above AFA threshold (₹1,500 > ₹1,000)
    order_payload = {
        "merchant": "blinkit",
        "items": [{"sku": "sku_costly", "qty": 1}],
    }
    agent_res = client.post("/v1/orders", json=order_payload, headers=headers)
    assert agent_res.status_code == 200
    res_data = agent_res.json()
    assert res_data["verdict"] == "UNKNOWN"
    assert res_data["clause_id"] == "afa.required"
    assert res_data["executed"] is False

    # 2. Inspect pending approvals on principal channel
    pending_res = client.get("/v1/pending")
    assert pending_res.status_code == 200
    pending_list = pending_res.json()["pending"]
    assert len(pending_list) == 1
    pending_item = pending_list[0]
    ref = pending_item["ref"]
    assert ref
    assert pending_item["amount"] == 150000
    assert pending_item["threshold"] == 100000
    assert pending_item["status"] == "pending"

    # CRITICAL SECURITY INVARIANT:
    # The ref token MUST NOT appear anywhere in the agent's response body or headers
    assert ref not in agent_res.text
    for h_val in agent_res.headers.values():
        assert ref not in h_val

    # 3. Preview approval via out-of-band link without agent credentials
    preview_res = client.get(f"/v1/approve/{ref}")
    assert preview_res.status_code == 200
    preview_data = preview_res.json()
    assert preview_data["ref"] == ref
    assert preview_data["amount"] == 150000
    assert preview_data["status"] == "pending"
    assert preview_data["items"][0]["title"] == "Premium Olive Oil 5L"

    # 4. Principal approves out-of-band
    approve_res = client.post("/v1/approve", json={"ref": ref, "decision": "approve"})
    assert approve_res.status_code == 200
    assert approve_res.json()["status"] == "approved"

    # 5. Agent retries identical order -> Now APPROVED and EXECUTED
    retry_res = client.post("/v1/orders", json=order_payload, headers=headers)
    assert retry_res.status_code == 200
    retry_data = retry_res.json()
    assert retry_data["verdict"] == "ALLOW"
    assert retry_data["executed"] is True
    assert retry_data["capability"] is not None

    # 6. In the same session, re-sending the same order returns cached commit without re-executing
    replay_same_res = client.post("/v1/orders", json=order_payload, headers=headers)
    assert replay_same_res.status_code == 200
    assert replay_same_res.json()["executed"] is False
    assert "already committed" in replay_same_res.json()["message"]

    # 7. In a new session (fresh ledger), attempting the same order is NOT pre-approved
    # because the approval was single-use and consumed upon execution
    token2 = mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti="tok_agent_afa_2")
    headers2 = {"Authorization": f"Bearer {token2}"}
    fresh_session_res = client.post("/v1/orders", json=order_payload, headers=headers2)
    assert fresh_session_res.status_code == 200
    fresh_data = fresh_session_res.json()
    assert fresh_data["verdict"] == "UNKNOWN"
    assert fresh_data["clause_id"] == "afa.required"
    assert fresh_data["executed"] is False
