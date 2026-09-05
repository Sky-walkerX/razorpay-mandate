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
from mandate.service.token_pool import TokenPool
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
        # A pool, because /v1/sessions is the only place a principal key is issued
        # and the principal channel is what makes an approval an approval.
        token_pool=TokenPool.from_tokens([
            mint_agent_token(
                pol.mandate_id, priv_hex,
                expires_iso=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                jti="tok_afa_wire",
            )
        ]),
    )

    client = TestClient(app)
    session = client.post("/v1/sessions").json()
    principal_hdr = {"X-Principal-Key": session["principal_key"]}

    # 1. Verify policy includes afa.required bound
    pol_res = client.get("/v1/policy")
    assert pol_res.status_code == 200
    parts = pol_res.json()["parts"]
    afa_part = next((p for p in parts if p["key"] == "afa.required"), None)
    assert afa_part is not None
    assert "₹1,000.00" in afa_part["bound"]

    # 2. Trigger AFA pending item
    headers = {"Authorization": f"Bearer {session['token']}"}

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
    pending_res = client.get("/v1/pending", headers=principal_hdr)
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


def test_the_policy_endpoint_and_the_evidence_file_agree_on_every_bound(tmp_path: Path):
    """Two `_bound` implementations exist and they had already drifted.

    `harness/evidence.py` feeds the built page; `service/server.py` feeds the live
    endpoint. Neither had an `afa.required` branch, and when one gained it the page
    still read "Set" while the endpoint read "₹15,000.00" -- the same fact rendered
    two ways on two screens, which is the bug `evidence.json` exists to prevent.

    The trap is that `afa.required` is keyed on `threshold` while every budget clause
    is keyed on `max`, so a branch copy-pasted from a budget clause silently falls
    through instead of failing.
    """
    from mandate.harness.evidence import _parts
    from mandate.policy.loader import load as load_policy

    repo_root = Path(__file__).resolve().parents[2]
    pol = load_policy(repo_root / "policies" / "policy.yaml")

    for part in _parts(pol):
        if part["source"] == "unset":
            continue
        assert part["bound"] != "Set", (
            f"{part['key']} renders as the placeholder 'Set' on the page while the "
            f"signed policy sets it. Give it a branch in harness/evidence.py._bound; "
            f"note afa.required is keyed on 'threshold', not 'max'."
        )
