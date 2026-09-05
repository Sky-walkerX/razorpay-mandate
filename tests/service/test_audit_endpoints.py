"""HTTP coverage for /v1/audit/{head,proof,consistency}.

These endpoints shipped referencing an undefined `audit_log`, so every request
raised NameError. Nothing caught it because nothing called them over HTTP. The
merkle unit tests all passed, which is the point: they tested the primitive, not
the boundary.
"""
from datetime import UTC, datetime, timedelta

from starlette.testclient import TestClient

from mandate.gateway.merkle import verify_inclusion_proof
from mandate.gateway.pricebook import DictPriceBook, PriceBookItem
from mandate.gateway.tokens import mint_agent_token
from mandate.money import Paise
from mandate.policy.crypto import generate_keypair, verify_bytes
from mandate.policy.loader import dump as dump_policy
from mandate.service.server import create_app
from tests.policy.test_models import _policy


def _setup(tmp_path, *, with_log_key: bool = True, monkeypatch=None,
           env_key_hex: str | None = None):
    priv_hex, pub_hex = generate_keypair()
    pol = _policy()
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)
    pub_path = tmp_path / "issuer_public.key"
    pub_path.write_text(pub_hex + "\n")

    log_priv, log_pub = generate_keypair()
    log_key_path = tmp_path / "log_private.key"
    if with_log_key:
        log_key_path.write_text(log_priv + "\n")
    if env_key_hex is not None:
        monkeypatch.setenv("MANDATE_LOG_PRIVATE_KEY", env_key_hex)

    pb = DictPriceBook({
        "sku_tea": PriceBookItem(
            sku="sku_tea", title="Assam Tea 500g", unit_price=Paise(25000),
            category="grocery", merchant="zepto",
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
        log_private_key_path=log_key_path,
    )
    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    token = mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti="tok_audit_01")
    return TestClient(app), {"Authorization": f"Bearer {token}"}, log_pub


def _place_orders(client, headers, n: int) -> None:
    for _ in range(n):
        client.post(
            "/v1/orders",
            json={"merchant": "zepto", "items": [{"sku": "sku_tea", "qty": 1}]},
            headers=headers,
        )


def test_audit_endpoints_require_a_token(tmp_path):
    client, _headers, _ = _setup(tmp_path)
    for path in ("/v1/audit/head", "/v1/audit/proof?seq=1", "/v1/audit/consistency?from=1&to=2"):
        assert client.get(path).status_code == 401, path


def test_head_is_signed_by_the_log_key(tmp_path):
    client, headers, log_pub = _setup(tmp_path)
    _place_orders(client, headers, 3)

    res = client.get("/v1/audit/head", headers=headers)
    assert res.status_code == 200
    head = res.json()
    assert head["size"] >= 1

    msg = f"{head['size']}:{head['root']}:{head['ts']}".encode()
    assert verify_bytes(msg, head["sig"], log_pub)

    _other_priv, other_pub = generate_keypair()
    assert not verify_bytes(msg, head["sig"], other_pub)


def test_head_refuses_rather_than_serving_an_unsigned_head(tmp_path):
    """No log key means 503. An unsigned head that looks verified is worse than none."""
    client, headers, _ = _setup(tmp_path, with_log_key=False)
    _place_orders(client, headers, 1)

    res = client.get("/v1/audit/head", headers=headers)
    assert res.status_code == 503
    assert "log signing key" in res.json()["error"]


def test_the_log_key_can_arrive_as_an_environment_variable(tmp_path, monkeypatch):
    """Production has no key file and cannot get one.

    `test_docker_image_ships_no_signing_key` rejects any COPY whose source contains
    "private", so the deployed image carries no log key by construction. Without an
    environment path the signed tree head can never run in production, which is
    exactly where it was found returning 503.
    """
    env_priv, env_pub = generate_keypair()
    client, headers, _unused = _setup(
        tmp_path, with_log_key=False, monkeypatch=monkeypatch, env_key_hex=env_priv,
    )
    _place_orders(client, headers, 2)

    res = client.get("/v1/audit/head", headers=headers)
    assert res.status_code == 200, res.json()
    head = res.json()
    msg = f"{head['size']}:{head['root']}:{head['ts']}".encode()
    assert verify_bytes(msg, head["sig"], env_pub)


def test_a_key_file_wins_over_the_environment(tmp_path, monkeypatch):
    """Precedence is file, then environment, and it is pinned so it cannot flip.

    Production has a variable and no file; a developer has a file and possibly a
    stale exported variable. This ordering means the key you just generated always
    wins locally, and production is unaffected because it has no file to prefer.
    """
    env_priv, env_pub = generate_keypair()
    client, headers, file_pub = _setup(
        tmp_path, with_log_key=True, monkeypatch=monkeypatch, env_key_hex=env_priv,
    )
    _place_orders(client, headers, 1)

    head = client.get("/v1/audit/head", headers=headers).json()
    msg = f"{head['size']}:{head['root']}:{head['ts']}".encode()
    assert verify_bytes(msg, head["sig"], file_pub)
    assert not verify_bytes(msg, head["sig"], env_pub)


def test_inclusion_proof_verifies_against_the_served_head(tmp_path):
    client, headers, _ = _setup(tmp_path)
    _place_orders(client, headers, 4)

    head = client.get("/v1/audit/head", headers=headers).json()
    res = client.get("/v1/audit/proof?seq=1", headers=headers)
    assert res.status_code == 200
    receipt = res.json()

    assert verify_inclusion_proof(
        receipt["leaf_record_hash"], 0, receipt["tree_size"], receipt["proof"], head["root"]
    )


def test_proof_rejects_an_out_of_range_sequence(tmp_path):
    client, headers, _ = _setup(tmp_path)
    _place_orders(client, headers, 2)
    assert client.get("/v1/audit/proof?seq=999", headers=headers).status_code == 400


def test_consistency_endpoint_returns_a_verifiable_proof(tmp_path):
    from mandate.gateway.merkle import verify_consistency_proof

    client, headers, _ = _setup(tmp_path)
    _place_orders(client, headers, 2)
    early = client.get("/v1/audit/head", headers=headers).json()

    _place_orders(client, headers, 3)
    later = client.get("/v1/audit/head", headers=headers).json()

    res = client.get(
        f"/v1/audit/consistency?from={early['size']}&to={later['size']}", headers=headers
    )
    assert res.status_code == 200
    body = res.json()
    assert verify_consistency_proof(
        early["size"], later["size"], early["root"], later["root"], body["proof"]
    )
