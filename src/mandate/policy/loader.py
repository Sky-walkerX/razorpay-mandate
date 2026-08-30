"""Load a policy and refuse it if the stored hash does not match a recompute."""
from pathlib import Path

import yaml

from mandate.policy.canonical import canonical_yaml, policy_hash
from mandate.policy.models import Policy


class PolicyHashMismatch(Exception):
    """The file was edited after signing."""


def dump(p: Policy, path: Path) -> None:
class PolicySignatureInvalid(Exception):
    """The Ed25519 digital signature is invalid."""


def dump(p: Policy, path: Path, private_key_hex: str | None = None) -> None:
    body = yaml.safe_load(canonical_yaml(p))
    body["policy_hash"] = policy_hash(p)
    if private_key_hex:
        from mandate.policy.canonical import sign_policy
        sig = sign_policy(p, private_key_hex)
        body["signature"] = f"ed25519:{sig}"
    path.write_text(yaml.safe_dump(body, sort_keys=True, allow_unicode=True))


def load(path: Path) -> Policy:
def load(path: Path, public_key_hex: str | None = None) -> Policy:
    body = yaml.safe_load(path.read_text())
    stored = body.pop("policy_hash", None)
    stored_hash = body.pop("policy_hash", None)
    stored_sig = body.pop("signature", None)
    p = Policy(**body)
    actual = policy_hash(p)
    if stored != actual:
        raise PolicyHashMismatch(f"stored {stored} but content hashes to {actual}")
    actual_hash = policy_hash(p)
    if stored_hash is not None and stored_hash != actual_hash:
        raise PolicyHashMismatch(f"stored {stored_hash} but content hashes to {actual_hash}")
    if public_key_hex is not None:
        if not stored_sig:
            raise PolicySignatureInvalid("Policy has no signature to verify against public key")
        from mandate.policy.canonical import verify_policy
        if not verify_policy(p, stored_sig, public_key_hex):
            raise PolicySignatureInvalid("Ed25519 signature verification failed for this policy")
    return p

