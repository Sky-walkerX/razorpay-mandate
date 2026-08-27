"""Canonical form: sorted keys, integer paise, RFC3339 timestamps. Then hash it."""
import hashlib

import yaml

from mandate.policy.models import Policy

HASHED_FIELDS = ("version", "mandate_id", "principal", "agent", "issued", "expires",
                 "constraints", "provenance", "source_text", "compiler")


def _plain(obj):
    if isinstance(obj, dict):
        return {str(k): _plain(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [_plain(v) for v in obj]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, bool) or obj is None:
        return obj
    if isinstance(obj, int):
        return int(obj)
    return str(obj) if not isinstance(obj, float) else obj


def canonical_yaml(p: Policy) -> str:
    d = p.model_dump(mode="python", include=set(HASHED_FIELDS))
    return yaml.safe_dump(_plain(d), sort_keys=True, allow_unicode=True, default_flow_style=False)


def policy_hash(p: Policy) -> str:
    return "sha256:" + hashlib.sha256(canonical_yaml(p).encode("utf-8")).hexdigest()
