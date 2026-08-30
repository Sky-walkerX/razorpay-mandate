"""Ed25519 asymmetric cryptography for offline policy signing and token verification.

The Issuer holds the private key and signs policies and agent tokens.
The Gateway holds only the public key and verifies both.
"""
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


class CryptoError(Exception):
    """Base cryptographic failure."""


class SignatureInvalid(CryptoError):
    """Signature verification failed."""


def generate_keypair() -> tuple[str, str]:
    """Generate a fresh Ed25519 keypair, returned as raw hex strings."""
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    return priv.private_bytes_raw().hex(), pub.public_bytes_raw().hex()


def sign_bytes(data: bytes, private_key_hex: str) -> str:
    """Sign raw bytes with an Ed25519 private key, returning hex signature."""
    priv = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(private_key_hex))
    sig = priv.sign(data)
    return sig.hex()


def verify_bytes(data: bytes, signature_hex: str, public_key_hex: str) -> bool:
    """Verify signature over raw bytes with an Ed25519 public key."""
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex))
        pub.verify(bytes.fromhex(signature_hex), data)
        return True
    except (InvalidSignature, ValueError):
        return False
