"""Scoped Bearer Tokens for AI Shopping Agents.

Tokens bind strictly to one mandate_id, expire with the policy, and carry
a unique jti for replay detection and revocation.
"""
import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from mandate.policy.crypto import CryptoError, SignatureInvalid, sign_bytes, verify_bytes


class TokenError(CryptoError):
    """Base token error."""


class TokenExpired(TokenError):
    """Token has expired."""


class TokenMalformed(TokenError):
    """Token cannot be parsed."""


@dataclass(frozen=True)
class TokenClaims:
    mandate_id: str
    jti: str
    exp: str
    issued: str


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = len(s) % 4
    if pad:
        s += "=" * (4 - pad)
    return base64.urlsafe_b64decode(s.encode())


def mint_agent_token(
    mandate_id: str,
    private_key_hex: str,
    expires_iso: str,
    jti: str | None = None,
) -> str:
    """Mint a signed bearer token for an agent, bound to a mandate_id."""
    claims = {
        "mandate_id": mandate_id,
        "jti": jti or f"tok_{uuid.uuid4().hex[:12]}",
        "exp": expires_iso,
        "issued": datetime.now(UTC).isoformat(),
    }
    payload_bytes = json.dumps(claims, sort_keys=True).encode()
    sig_hex = sign_bytes(payload_bytes, private_key_hex)
    return f"{_b64url_encode(payload_bytes)}.{sig_hex}"


def verify_agent_token(
    token: str,
    public_key_hex: str,
    now: datetime | None = None,
) -> TokenClaims:
    """Verify a bearer token against the issuer public key and check expiry."""
    parts = token.strip().split(".")
    if len(parts) != 2:
        raise TokenMalformed("Token must consist of <payload_b64>.<sig_hex>")
    
    payload_b64, sig_hex = parts
    try:
        payload_bytes = _b64url_decode(payload_b64)
        claims_dict = json.loads(payload_bytes.decode())
    except Exception as e:
        raise TokenMalformed(f"Failed to decode token claims: {e}") from e

    if not verify_bytes(payload_bytes, sig_hex, public_key_hex):
        raise SignatureInvalid("Token signature is invalid for this public key")

    exp_str = claims_dict.get("exp")
    if exp_str:
        try:
            exp_dt = datetime.fromisoformat(exp_str)
            check_now = now or datetime.now(UTC)
            if check_now >= exp_dt:
                raise TokenExpired(f"Token expired at {exp_str} (current time: {check_now.isoformat()})")
        except ValueError as e:
            raise TokenMalformed(f"Invalid expiration format: {exp_str}") from e

    return TokenClaims(
        mandate_id=claims_dict["mandate_id"],
        jti=claims_dict["jti"],
        exp=claims_dict.get("exp", ""),
        issued=claims_dict.get("issued", ""),
    )
