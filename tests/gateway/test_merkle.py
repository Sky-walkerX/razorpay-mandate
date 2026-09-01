import hashlib

from mandate.gateway.merkle import (
    consistency_proof,
    inclusion_proof,
    leaf_hash,
    merkle_tree_hash,
    node_hash,
    verify_consistency_proof,
    verify_inclusion_proof,
)


def test_rfc6962_domain_separation():
    """Verify 0x00 and 0x01 domain separation prefixes."""
    data = "test_record_hash"
    l_hash = leaf_hash(data)
    expected_leaf = "sha256:" + hashlib.sha256(b"\x00" + data.encode("utf-8")).hexdigest()
    assert l_hash == expected_leaf

    n_hash = node_hash(l_hash, l_hash)
    b_l = bytes.fromhex(l_hash.removeprefix("sha256:"))
    expected_node = "sha256:" + hashlib.sha256(b"\x01" + b_l + b_l).hexdigest()
    assert n_hash == expected_node
    assert l_hash != n_hash


def test_inclusion_proofs_up_to_200():
    """Verify inclusion proofs for every leaf at every tree size up to 200."""
    leaves = [f"sha256:{hashlib.sha256(str(i).encode()).hexdigest()}" for i in range(200)]

    for size in [1, 2, 3, 5, 8, 16, 33, 100, 200]:
        tree_leaves = leaves[:size]
        root = merkle_tree_hash(tree_leaves)

        for idx in range(size):
            proof = inclusion_proof(idx, tree_leaves)
            valid = verify_inclusion_proof(tree_leaves[idx], idx, size, proof, root)
            assert valid, f"Inclusion proof failed for leaf {idx} in tree of size {size}"


def test_tamper_detection_fails_inclusion():
    """Assert editing or deleting a leaf makes inclusion proof fail."""
    leaves = [f"sha256:{hashlib.sha256(str(i).encode()).hexdigest()}" for i in range(10)]
    root = merkle_tree_hash(leaves)

    proof = inclusion_proof(3, leaves)
    # Correct leaf passes
    assert verify_inclusion_proof(leaves[3], 3, 10, proof, root)

    # Tampered leaf fails
    tampered_leaf = "sha256:" + hashlib.sha256(b"tampered").hexdigest()
    assert not verify_inclusion_proof(tampered_leaf, 3, 10, proof, root)


def _leaves(n: int) -> list[str]:
    return [f"sha256:{hashlib.sha256(str(i).encode()).hexdigest()}" for i in range(n)]


def test_inclusion_proof_rejects_wrong_position_and_size():
    """Direction is derived from index and tree_size, so lying about either must fail."""
    t = _leaves(16)
    root = merkle_tree_hash(t)
    proof = inclusion_proof(5, t)

    assert verify_inclusion_proof(t[5], 5, 16, proof, root)
    assert not verify_inclusion_proof(t[5], 6, 16, proof, root)
    assert not verify_inclusion_proof(t[5], 5, 17, proof, root)


def test_consistency_proofs_verify_for_every_pair():
    """Every (m, n) with m <= n must produce a proof that verifies. 820 pairs."""
    leaves = _leaves(40)
    for n in range(1, 41):
        for m in range(1, n + 1):
            first_root = merkle_tree_hash(leaves[:m])
            second_root = merkle_tree_hash(leaves[:n])
            proof = consistency_proof(m, n, leaves[:n])
            assert verify_consistency_proof(m, n, first_root, second_root, proof), (
                f"consistency proof failed for m={m} n={n}"
            )


def test_consistency_proof_catches_a_rewrite():
    """The point of the whole item: a log that edits or drops a committed record is caught.

    A consistency proof only commits to the first m leaves, so the tamper has to land
    inside that prefix to be a rewrite at all. Editing leaf 7 of a 5-leaf commitment is
    an append, not a rewrite, and must still verify.
    """
    honest = _leaves(10)
    head_at_5 = merkle_tree_hash(honest[:5])

    edited = honest[:2] + [_leaves(64)[63]] + honest[3:]
    assert not verify_consistency_proof(
        5, 10, head_at_5, merkle_tree_hash(edited), consistency_proof(5, 10, edited)
    )

    dropped = honest[:3] + honest[4:] + [_leaves(64)[50]]
    assert not verify_consistency_proof(
        5, 10, head_at_5, merkle_tree_hash(dropped), consistency_proof(5, 10, dropped)
    )

    assert verify_consistency_proof(
        5, 10, head_at_5, merkle_tree_hash(honest), consistency_proof(5, 10, honest)
    )


def test_consistency_proof_rejects_an_empty_proof():
    honest = _leaves(10)
    assert not verify_consistency_proof(
        5, 10, merkle_tree_hash(honest[:5]), merkle_tree_hash(honest), []
    )
