"""Load a policy and refuse it if the stored hash does not match a recompute."""
from pathlib import Path

import yaml

from mandate.policy.canonical import canonical_yaml, policy_hash
from mandate.policy.models import Policy


class PolicyHashMismatch(Exception):
    """The file was edited after signing."""


def dump(p: Policy, path: Path) -> None:
    body = yaml.safe_load(canonical_yaml(p))
    body["policy_hash"] = policy_hash(p)
    path.write_text(yaml.safe_dump(body, sort_keys=True, allow_unicode=True))


def load(path: Path) -> Policy:
    body = yaml.safe_load(path.read_text())
    stored = body.pop("policy_hash", None)
    p = Policy(**body)
    actual = policy_hash(p)
    if stored != actual:
        raise PolicyHashMismatch(f"stored {stored} but content hashes to {actual}")
    return p
