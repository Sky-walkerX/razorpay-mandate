"""End-to-end receipts: an audit log, an inclusion proof, and a signed head.

These go through AuditLog rather than the merkle primitives directly, for the same
reason the conformance suite runs its attacks through Gateway: a proof that verifies
in isolation says nothing about whether the log actually produces it.
"""
from datetime import UTC, datetime

from mandate.gateway.action import Action, ActionType
from mandate.gateway.audit import AuditLog
from mandate.gateway.merkle import verify_inclusion_proof
from mandate.gateway.state import Verdict
from mandate.policy.crypto import generate_keypair, sign_bytes, verify_bytes


def _log_with(tmp_path, n: int) -> AuditLog:
    log = AuditLog(tmp_path / "audit.jsonl")
    for i in range(n):
        log.append(
            ts=datetime.now(UTC),
            mandate_id="m_test",
            policy_hash="sha256:" + "a" * 64,
            idem_key=f"idem_{i}",
            action=Action(type=ActionType.CREATE_ORDER, merchant="zepto", amount=1000 + i, items=[]),
            verdict=Verdict.ALLOW,
            clauses=[],
            downstream=None,
        )
    return log


def _head_bytes(size: int, root: str, ts: str) -> bytes:
    """The exact head encoding the service signs and the CLI verifies."""
    return f"{size}:{root}:{ts}".encode()


def test_inclusion_proof_from_a_real_log_verifies(tmp_path):
    log = _log_with(tmp_path, 12)
    root = log.get_merkle_root()

    for seq in range(1, 13):
        receipt = log.get_inclusion_proof(seq)
        assert verify_inclusion_proof(
            receipt["leaf_record_hash"], seq - 1, receipt["tree_size"], receipt["proof"], root
        )


def test_verify_rejects_a_head_signed_by_the_wrong_key(tmp_path):
    """The gateway's log key signs heads. Any other key must not pass."""
    log = _log_with(tmp_path, 5)
    ts = datetime.now(UTC).isoformat()
    msg = _head_bytes(5, log.get_merkle_root(), ts)

    log_priv, log_pub = generate_keypair()
    _other_priv, other_pub = generate_keypair()

    sig = sign_bytes(msg, log_priv)
    assert verify_bytes(msg, sig, log_pub)
    assert not verify_bytes(msg, sig, other_pub)


def test_a_tampered_head_fails_its_own_signature(tmp_path):
    """Editing the size or root of a signed head invalidates it."""
    log = _log_with(tmp_path, 5)
    root = log.get_merkle_root()
    ts = datetime.now(UTC).isoformat()

    priv, pub = generate_keypair()
    sig = sign_bytes(_head_bytes(5, root, ts), priv)

    assert not verify_bytes(_head_bytes(6, root, ts), sig, pub)
    assert not verify_bytes(_head_bytes(5, "sha256:" + "f" * 64, ts), sig, pub)


def test_appending_does_not_invalidate_an_earlier_receipt(tmp_path):
    """An old receipt still verifies against the old root after the log grows."""
    log = _log_with(tmp_path, 4)
    early_root = log.get_merkle_root()
    receipt = log.get_inclusion_proof(2)

    for i in range(6):
        log.append(
            ts=datetime.now(UTC),
            mandate_id="m_test",
            policy_hash="sha256:" + "a" * 64,
            idem_key=f"later_{i}",
            action=Action(type=ActionType.CREATE_ORDER, merchant="zepto", amount=99, items=[]),
            verdict=Verdict.ALLOW,
            clauses=[],
            downstream=None,
        )

    assert verify_inclusion_proof(
        receipt["leaf_record_hash"], 1, receipt["tree_size"], receipt["proof"], early_root
    )
    assert log.get_merkle_root() != early_root
