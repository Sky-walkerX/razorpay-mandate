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


def test_approval_ref_never_reaches_the_agent_and_enables_oob_approval(tmp_path: Path):
    client = _afa_app(tmp_path)
    headers, principal = _open_session(client)
    principal_hdr = {"X-Principal-Key": principal}

    # 1. Agent submits proposal above AFA threshold (₹1,500 > ₹1,000)
    order_payload = dict(ORDER)
    agent_res = client.post("/v1/orders", json=order_payload, headers=headers)
    assert agent_res.status_code == 200
    res_data = agent_res.json()
    assert res_data["verdict"] == "UNKNOWN"
    assert res_data["clause_id"] == "afa.required"
    assert res_data["executed"] is False

    # 2. Inspect pending approvals on principal channel
    pending_res = client.get("/v1/pending", headers=principal_hdr)
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
    # The preview does not echo the ref: the caller already holds it, it arrived in
    # the URL, and a payload that carries it is one more place for it to be logged.
    assert "ref" not in preview_data
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
    headers2, _principal2 = _open_session(client)
    fresh_session_res = client.post("/v1/orders", json=order_payload, headers=headers2)
    assert fresh_session_res.status_code == 200
    fresh_data = fresh_session_res.json()
    assert fresh_data["verdict"] == "UNKNOWN"
    assert fresh_data["clause_id"] == "afa.required"
    assert fresh_data["executed"] is False


def _afa_app(tmp_path: Path):
    """A service whose AFA threshold is low enough that one order escalates.

    Built with a token pool, which is the deployed configuration and the only one
    that has a principal channel: `/v1/sessions` is called by the human's page, and
    the page hands the agent the bearer token and keeps the principal key.
    """
    priv_hex, pub_hex = generate_keypair()
    pol = _policy(
        constraints={
            C.BUDGET_TOTAL: {"max": 500000},
            C.AFA_REQUIRED: {"threshold": 100000},
        },
        provenance=Provenance(stated=[C.BUDGET_TOTAL], inferred=[],
                              regulatory=[C.AFA_REQUIRED]),
        expires=datetime.now(IST) + timedelta(days=2),
    )
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)
    pub_path = tmp_path / "issuer_public.key"
    pub_path.write_text(pub_hex + "\n")
    pb = DictPriceBook({
        "sku_costly": PriceBookItem(
            sku="sku_costly", title="Premium Olive Oil 5L",
            unit_price=Paise(150000), category="grocery", merchant="blinkit",
        )
    })
    app = create_app(
        policy_path=pol_path, public_key_path=pub_path,
        revocations_path=tmp_path / "revocations.jsonl",
        audit_path=tmp_path / "audit.jsonl", ledger_path=tmp_path / "ledger.jsonl",
        pricebook=pb, capability_secret="secret_test_42",
        token_pool=TokenPool.from_tokens([
            mint_agent_token(pol.mandate_id, priv_hex,
                             expires_iso=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                             jti=f"tok_sec_{n:02d}")
            for n in range(1, 5)
        ]),
    )
    return TestClient(app)


def _open_session(client: TestClient) -> tuple[dict, str]:
    """What the page does: claim a session, keep the principal key, hand over the token."""
    body = client.post("/v1/sessions").json()
    return {"Authorization": f"Bearer {body['token']}"}, body["principal_key"]


ORDER = {"merchant": "blinkit", "items": [{"sku": "sku_costly", "qty": 1}]}


def test_an_agent_cannot_approve_its_own_escalation(tmp_path: Path):
    """The property the whole feature exists to provide.

    Served unauthenticated, /v1/pending hands any caller the ref that approves the
    escalation it is holding, and POST /v1/approve asks for nothing else. That is
    `escalate.self` with extra steps, and it was live: the agent escalated, read its
    own ref, approved itself, retried, and the order settled on the rail.
    """
    client = _afa_app(tmp_path)
    agent, _principal = _open_session(client)

    held = client.post("/v1/orders", json=ORDER, headers=agent).json()
    assert held["verdict"] == "UNKNOWN" and held["clause_id"] == "afa.required"

    # Everything the agent holds, tried against the principal's channel.
    assert client.get("/v1/pending").status_code == 401
    assert client.get("/v1/pending", headers=agent).status_code == 401

    retry = client.post("/v1/orders", json=ORDER, headers=agent).json()
    assert retry["executed"] is False
    assert retry["verdict"] == "UNKNOWN"


def test_the_principal_key_is_not_interchangeable_with_the_agent_token(tmp_path: Path):
    """Two credentials, neither of which does the other's job."""
    client = _afa_app(tmp_path)
    agent, principal = _open_session(client)

    # The principal's credential cannot spend.
    assert client.post("/v1/orders", json=ORDER,
                       headers={"Authorization": f"Bearer {principal}"}).status_code in (401, 403)
    # The agent's credential cannot approve.
    assert client.get("/v1/pending",
                      headers={"X-Principal-Key": agent["Authorization"]}).status_code == 401


def test_a_principal_sees_only_its_own_sessions_escalations(tmp_path: Path):
    """On a public deployment an unscoped queue shows one visitor another's basket.

    Worse than disclosure: the row carries the ref that approves it.
    """
    client = _afa_app(tmp_path)
    agent, _mine = _open_session(client)
    client.post("/v1/orders", json=ORDER, headers=agent)

    _other_agent, other = _open_session(client)
    listed = client.get("/v1/pending", headers={"X-Principal-Key": other}).json()["pending"]
    assert listed == []
