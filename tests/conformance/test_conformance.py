"""Pytest wrapper for the 8-Attack Protocol Conformance Suite with Witnesses."""
from mandate.conformance.suite import run_conformance_suite
from mandate.conformance.witness import ConformanceOutcome


def test_conformance_suite_all_attacks_blocked_with_witnesses(tmp_path):
    results = run_conformance_suite(tmp_path)
    assert len(results) == 8
    
    for r in results:
        # 1. Meta-assertion: Witness MUST have executed (otherwise attack is vacuous)
        assert r.witness_executed is True, f"Attack {r.attack_id} had a failing witness (VACUOUS)!"
        assert r.outcome is ConformanceOutcome.BLOCKED, (
            f"Attack {r.attack_id} was NOT blocked: outcome={r.outcome}, detail={r.detail}"
        )
        assert r.hardened_executed is False, f"Hardened gateway allowed attack {r.attack_id} to execute!"
