"""Request path step 1: the gateway verifies the token before it does anything else.

Before this, token verification lived only in the HTTP handler, so `Gateway` itself
had no notion of a token and the boundary held only for callers that went over the
wire. These tests pin it to the gateway, which is the thing both transports share.
"""
from datetime import UTC, datetime, timedelta

import pytest

from mandate.downstream.fake import FakeDownstream
from mandate.gateway.action import Proposal, ProposalItem
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway, Mode
from mandate.gateway.idem import Ledger
from mandate.gateway.revocation import RevocationList
from mandate.gateway.state import Verdict
from mandate.gateway.tokens import mint_agent_token
from mandate.policy.crypto import generate_keypair
from tests.conftest import SyntheticPriceBook, priced_sku
from tests.gateway.test_core import _pol

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
EXPIRES = datetime(2026, 9, 2, 0, 0, tzinfo=UTC)


@pytest.fixture
def env(tmp_path):
    priv, pub = generate_keypair()
    policy = _pol()
    revocations = RevocationList(tmp_path / "revocations.jsonl")
    gw = Gateway(
        policy=policy, downstream=FakeDownstream(),
        audit=AuditLog(tmp_path / "audit.jsonl"), mode=Mode.ENFORCE,
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        pricebook=SyntheticPriceBook(),
        capability_secret="test_secret",
        issuer_public_key=pub, revocations=revocations,
    )
    return priv, pub, policy, gw, revocations


def _buy(amount=50000):
    return Proposal(merchant="zepto", items=[ProposalItem(sku=priced_sku(amount), qty=1)])


def _token(priv, policy, jti="tok_01", mandate_id=None, expires=EXPIRES):
    return mint_agent_token(
        mandate_id=mandate_id or policy.mandate_id,
        private_key_hex=priv, expires_iso=expires.isoformat(), jti=jti)


def test_a_valid_token_is_accepted(env):
    priv, _pub, policy, gw, _rev = env
    d = gw.propose(_buy(), NOW, token=_token(priv, policy))
    assert d.verdict is Verdict.ALLOW and d.executed


def test_no_token_is_denied(env):
    _priv, _pub, _policy, gw, _rev = env
    d = gw.propose(_buy(), NOW, token=None)
    assert d.verdict is Verdict.DENY and d.clause_id == "authentication"
    assert not d.executed


def test_a_token_signed_by_another_key_is_denied(env):
    _priv, _pub, policy, gw, _rev = env
    attacker_priv, _ = generate_keypair()
    d = gw.propose(_buy(), NOW, token=_token(attacker_priv, policy))
    assert d.verdict is Verdict.DENY and d.clause_id == "authentication"


def test_an_expired_token_is_denied(env):
    priv, _pub, policy, gw, _rev = env
    expired = _token(priv, policy, expires=NOW - timedelta(hours=1))
    d = gw.propose(_buy(), NOW, token=expired)
    assert d.verdict is Verdict.DENY and d.clause_id == "authentication"


def test_a_token_for_another_mandate_is_denied(env):
    priv, _pub, policy, gw, _rev = env
    other = _token(priv, policy, mandate_id="mnd_someone_else")
    d = gw.propose(_buy(), NOW, token=other)
    assert d.verdict is Verdict.DENY and d.clause_id == "authentication"


def test_a_revoked_jti_is_denied(env):
    priv, _pub, policy, gw, rev = env
    token = _token(priv, policy, jti="tok_to_revoke")
    assert gw.propose(_buy(50000), NOW, token=token).executed
    rev.revoke("tok_to_revoke", reason="spent")
    d = gw.propose(_buy(60000), NOW, token=token)
    assert d.verdict is Verdict.DENY and d.clause_id == "authentication"


def test_the_token_check_runs_before_the_price_book(env):
    """An unauthenticated caller learns nothing, not even whether a SKU exists."""
    _priv, _pub, _policy, gw, _rev = env
    d = gw.propose(
        Proposal(merchant="zepto", items=[ProposalItem(sku="no_such_sku", qty=1)]),
        NOW, token=None,
    )
    assert d.clause_id == "authentication", "a bad token must not reveal price book state"


def test_a_gateway_with_no_issuer_key_does_not_require_a_token(tmp_path):
    """The in-process harness runs inside the trust domain and carries no token.

    This is why the standalone service refuses to start without a key: it is the
    configuration that turns the check on.
    """
    gw = Gateway(policy=_pol(), downstream=FakeDownstream(),
                 audit=AuditLog(tmp_path / "audit.jsonl"),
                 pricebook=SyntheticPriceBook(),
                 capability_secret="test_secret")
    assert gw.propose(_buy(), NOW).verdict is Verdict.ALLOW
