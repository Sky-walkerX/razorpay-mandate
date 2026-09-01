"""RFC 6962 compliant Merkle tree implementation with domain separation.

Leaves are prefixed with 0x00 and interior nodes with 0x01 before hashing.
"""
import hashlib
from typing import Any


def leaf_hash(raw_hex_or_bytes: str | bytes) -> str:
    """Hash a leaf with RFC 6962 0x00 domain separation prefix."""
    if isinstance(raw_hex_or_bytes, str):
        payload = bytes.fromhex(raw_hex_or_bytes.removeprefix("sha256:")) if raw_hex_or_bytes.startswith("sha256:") else raw_hex_or_bytes.encode("utf-8")
    else:
        payload = raw_hex_or_bytes
    return "sha256:" + hashlib.sha256(b"\x00" + payload).hexdigest()


def node_hash(left_hex: str, right_hex: str) -> str:
    """Hash an interior node with RFC 6962 0x01 domain separation prefix."""
    left_bytes = bytes.fromhex(left_hex.removeprefix("sha256:"))
    right_bytes = bytes.fromhex(right_hex.removeprefix("sha256:"))
    return "sha256:" + hashlib.sha256(b"\x01" + left_bytes + right_bytes).hexdigest()


def _largest_power_of_two_less_than(n: int) -> int:
    k = 1
    while k < n:
        k <<= 1
    return k >> 1


def merkle_tree_hash(leaves: list[str]) -> str:
    """Compute the Merkle tree hash (root) for a list of leaf record hashes according to RFC 6962."""
    n = len(leaves)
    if n == 0:
        return "sha256:" + hashlib.sha256(b"").hexdigest()
    if n == 1:
        return leaf_hash(leaves[0])
    
    k = _largest_power_of_two_less_than(n)
    left_root = merkle_tree_hash(leaves[:k])
    right_root = merkle_tree_hash(leaves[k:])
    return node_hash(left_root, right_root)


def inclusion_proof(index: int, leaves: list[str]) -> list[dict[str, Any]]:
    """Generate an RFC 6962 audit path (inclusion proof) for leaf at index in leaves."""
    n = len(leaves)
    if index < 0 or index >= n:
        raise ValueError(f"Index {index} out of range for tree of size {n}")
    
    return _subproof(index, leaves)


def _subproof(m: int, leaves: list[str]) -> list[dict[str, Any]]:
    n = len(leaves)
    if n <= 1:
        return []
    
    k = _largest_power_of_two_less_than(n)
    if m < k:
        proof = _subproof(m, leaves[:k])
        proof.append({"node": merkle_tree_hash(leaves[k:]), "dir": "right"})
        return proof
    else:
        proof = _subproof(m - k, leaves[k:])
        proof.append({"node": merkle_tree_hash(leaves[:k]), "dir": "left"})
        return proof


def _nodes(proof: list[dict[str, Any]]) -> list[str]:
    """Take only the hashes from a proof. Direction is derived, never trusted."""
    return [p["node"] for p in proof]


def verify_inclusion_proof(
    leaf_record: str,
    index: int,
    tree_size: int,
    proof: list[dict[str, Any]],
    expected_root: str,
) -> bool:
    """Verify an inclusion proof against an expected root, per RFC 6962 section 2.1.1.

    Direction at each level comes from `index` and `tree_size`, not from the `dir`
    field in the proof. A verifier that reads its own instructions out of the
    document it is checking is not verifying anything.
    """
    if index < 0 or tree_size <= 0 or index >= tree_size:
        return False

    nodes = _nodes(proof)
    fn, sn = index, tree_size - 1
    current = leaf_hash(leaf_record)

    for sibling in nodes:
        if sn == 0:
            return False  # proof longer than the tree is deep
        if (fn & 1) or fn == sn:
            current = node_hash(sibling, current)
            while fn != 0 and not (fn & 1):
                fn >>= 1
                sn >>= 1
        else:
            current = node_hash(current, sibling)
        fn >>= 1
        sn >>= 1

    return sn == 0 and current == expected_root


def consistency_proof(first_count: int, second_count: int, leaves: list[str]) -> list[dict[str, Any]]:
    """Generate an RFC 6962 consistency proof between tree of size first_count and second_count."""
    if first_count <= 0 or first_count > second_count or second_count > len(leaves):
        raise ValueError("Invalid first_count / second_count bounds")
    
    return _subconsistency(first_count, leaves[:second_count], True)


def _subconsistency(m: int, leaves: list[str], b: bool) -> list[dict[str, Any]]:
    n = len(leaves)
    if m == n:
        if b:
            return []
        else:
            return [{"node": merkle_tree_hash(leaves), "dir": "root"}]
    
    k = _largest_power_of_two_less_than(n)
    if m <= k:
        proof = _subconsistency(m, leaves[:k], b)
        proof.append({"node": merkle_tree_hash(leaves[k:]), "dir": "right"})
        return proof
    else:
        proof = _subconsistency(m - k, leaves[k:], False)
        proof.append({"node": merkle_tree_hash(leaves[:k]), "dir": "left"})
        return proof



def verify_consistency_proof(
    first_count: int,
    second_count: int,
    first_root: str,
    second_root: str,
    proof: list[dict[str, Any]],
) -> bool:
    """Verify that a tree of size second_count extends one of size first_count.

    This is the check that makes a rewrite detectable. An inclusion proof says a
    record is in the log now; only a consistency proof says the log did not drop
    or reorder anything since a head someone already holds.
    """
    if first_count < 1 or first_count > second_count:
        return False
    if first_count == second_count:
        return not proof and first_root == second_root

    nodes = _nodes(proof)
    fn, sn = first_count - 1, second_count - 1
    while fn & 1:
        fn >>= 1
        sn >>= 1

    if fn != 0:
        if not nodes:
            return False
        node = nodes.pop(0)
    else:
        # first_count is a power of two, so its root is implicit and omitted.
        node = first_root

    fr = sr = node
    while sn != 0:
        if not nodes:
            return False
        if (fn & 1) or fn == sn:
            nxt = nodes.pop(0)
            fr = node_hash(nxt, fr)
            sr = node_hash(nxt, sr)
            while fn != 0 and not (fn & 1):
                fn >>= 1
                sn >>= 1
        else:
            nxt = nodes.pop(0)
            sr = node_hash(sr, nxt)
        fn >>= 1
        sn >>= 1

    return not nodes and fr == first_root and sr == second_root
