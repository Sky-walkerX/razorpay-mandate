"""Tests for Ed25519 cryptographic issuer, bearer tokens, and revocation."""
from datetime import UTC, datetime, timedelta

import pytest

from mandate.gateway.revocation import RevocationList
from mandate.gateway.tokens import (
    TokenExpired,
    mint_agent_token,
    verify_agent_token,
)
from mandate.policy.crypto import (
    CryptoError,
    generate_keypair,
    sign_bytes,
    verify_bytes,
)
from mandate.policy.loader import PolicySignatureInvalid, dump, load
from tests.policy.test_models import _policy


def test_ed25519_keypair_generation_and_signing():
    priv, pub = generate_keypair()
    assert len(priv) == 64
    assert len(pub) == 64
    
    msg = b"hello from mandate offline issuer"
    sig = sign_bytes(msg, priv)
    assert verify_bytes(msg, sig, pub) is True
    
    # Tampering fails verification
    tampered_msg = b"hello from mandate offline issuer - tampered"
    assert verify_bytes(tampered_msg, sig, pub) is False


def test_policy_ed25519_signing_and_verification(tmp_path):
    priv, pub = generate_keypair()
    pol = _policy()
    
    path = tmp_path / "signed_policy.yaml"
    dump(pol, path, private_key_hex=priv)
    
    # Valid load with correct public key
    loaded = load(path, public_key_hex=pub)
    assert loaded.mandate_id == pol.mandate_id
    
    # Fails with incorrect public key
    _, other_pub = generate_keypair()
    with pytest.raises(PolicySignatureInvalid):
        load(path, public_key_hex=other_pub)


def test_bearer_token_mint_and_verify():
    priv, pub = generate_keypair()
    now = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    exp = (now + timedelta(hours=2)).isoformat()
    
    tok = mint_agent_token("mnd_01", priv, expires_iso=exp, jti="tok_test_01")
    claims = verify_agent_token(tok, pub, now=now)
    assert claims.mandate_id == "mnd_01"
    assert claims.jti == "tok_test_01"
    
    # Expired token raises TokenExpired
    later = now + timedelta(hours=3)
    with pytest.raises(TokenExpired):
        verify_agent_token(tok, pub, now=later)
        
    # Tampered token raises SignatureInvalid or TokenMalformed
    tampered_tok = tok[:-4] + "ffff"
    with pytest.raises(CryptoError):
        verify_agent_token(tampered_tok, pub, now=now)




def test_revocation_list(tmp_path):
    r_path = tmp_path / "revocations.jsonl"
    rlist = RevocationList(r_path)
    assert rlist.is_revoked("tok_abc") is False
    
    rlist.revoke("tok_abc", reason="test_kill_switch")
    assert rlist.is_revoked("tok_abc") is True
    
    # Reloads from disk in fresh instance
    rlist2 = RevocationList(r_path)
    assert rlist2.is_revoked("tok_abc") is True
    assert rlist2.is_revoked("tok_xyz") is False
