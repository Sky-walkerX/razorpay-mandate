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


def test_afa_wiring_rejection_and_lifecycle(tmp_path: Path):
    priv_hex, pub_hex = generate_keypair()
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
            unit_price=Paise(150000),
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

    # 1. Verify policy includes afa.required bound
    pol_res = client.get("/v1/policy")
    assert pol_res.status_code == 200
    parts = pol_res.json()["parts"]
    afa_part = next((p for p in parts if p["key"] == "afa.required"), None)
    assert afa_part is not None
    assert "₹1,000.00" in afa_part["bound"]

    # 2. Trigger AFA pending item
    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    token = mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti="tok_afa_wire")
    headers = {"Authorization": f"Bearer {token}"}

    client.post(
        "/v1/orders",
        json={"merchant": "blinkit", "items": [{"sku": "sku_costly", "qty": 1}]},
        headers=headers,
    )

    # 3. Check headroom contains afa.required
    hr_res = client.get("/v1/headroom", headers=headers)
    assert hr_res.status_code == 200
    hr_list = hr_res.json()
    afa_hr = next((h for h in hr_list if h["clause_id"] == "afa.required"), None)
    assert afa_hr is not None
    assert afa_hr["limit_paise"] == 100000

    # 4. Pending list
    pending_res = client.get("/v1/pending")
    ref = pending_res.json()["pending"][0]["ref"]

    # 5. Invalid ref preview -> 404
    bad_prev = client.get("/v1/approve/bad_ref_xyz")
    assert bad_prev.status_code == 404

    # 6. Reject decision
    rej_res = client.post("/v1/approve", json={"ref": ref, "decision": "reject"})
    assert rej_res.status_code == 200
    assert rej_res.json()["status"] == "rejected"

    # 7. Double resolve -> 409 conflict
    double_res = client.post("/v1/approve", json={"ref": ref, "decision": "approve"})
    assert double_res.status_code == 409

    # 8. Agent retry after rejection is still UNKNOWN
    retry_res = client.post(
        "/v1/orders",
        json={"merchant": "blinkit", "items": [{"sku": "sku_costly", "qty": 1}]},
        headers=headers,
    )
    assert retry_res.json()["verdict"] == "UNKNOWN"
