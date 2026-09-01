"""The pool must not hand out a token that is revoked on disk.

`_retired` is per-process and forgets across a restart. Five tokens revoked during
earlier demos were still first in line, so the first visitor after any restart got
a session whose every gateway call failed authentication.
"""
from datetime import UTC, datetime, timedelta

from mandate.gateway.revocation import RevocationList
from mandate.gateway.tokens import mint_agent_token
from mandate.policy.crypto import generate_keypair
from mandate.service.token_pool import TokenPool


def _tokens(priv: str, n: int) -> list[str]:
    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    return [mint_agent_token("mnd_x", priv, expires_iso=exp, jti=f"tok_pool_{i:03d}")
            for i in range(1, n + 1)]


def test_claim_skips_tokens_revoked_on_disk(tmp_path):
    priv, pub = generate_keypair()
    rev = RevocationList(tmp_path / "revocations.jsonl")
    rev.revoke("tok_pool_001", reason="earlier demo")
    rev.revoke("tok_pool_002", reason="earlier demo")

    pool = TokenPool(_tokens(priv, 5), is_revoked=rev.is_revoked)
    _tok, claims = pool.claim_token(pub)
    assert claims.jti == "tok_pool_003"


def test_a_revoked_token_is_not_returned_later(tmp_path):
    priv, pub = generate_keypair()
    rev = RevocationList(tmp_path / "revocations.jsonl")
    rev.revoke("tok_pool_001", reason="earlier demo")

    pool = TokenPool(_tokens(priv, 3), is_revoked=rev.is_revoked)
    seen = {pool.claim_token(pub)[1].jti for _ in range(2)}
    assert "tok_pool_001" not in seen


def test_without_a_revocation_check_behaviour_is_unchanged(tmp_path):
    """The parameter is optional, so existing callers keep working."""
    priv, pub = generate_keypair()
    pool = TokenPool(_tokens(priv, 2))
    _tok, claims = pool.claim_token(pub)
    assert claims.jti == "tok_pool_001"
