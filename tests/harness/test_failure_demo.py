"""The demo makes a claim on stage. These assert the claim is true before it is made."""
from pathlib import Path

from mandate.gateway.idem import EntryState
from mandate.harness.failure_demo import run_failure_demo
from mandate.policy.loader import load as load_policy


def _policy():
    return load_policy(Path(__file__).resolve().parents[2] / "policies" / "policy.yaml")


def test_a_lost_response_charges_exactly_once(tmp_path):
    r = run_failure_demo(_policy(), tmp_path)
    assert r.orders_downstream == 1
    assert int(r.charged) == 15900
    assert int(r.budget_consumed) == 15900


def test_the_naive_path_charges_twice(tmp_path):
    """Without the ledger the same two calls double charge. That contrast is the demo."""
    r = run_failure_demo(_policy(), tmp_path)
    assert r.naive_orders == 2
    assert int(r.naive_charged) == 31800
    assert int(r.naive_charged) == 2 * int(r.charged)


def test_the_retry_is_held_rather_than_executed(tmp_path):
    r = run_failure_demo(_policy(), tmp_path)
    retry = r.steps[1]
    assert retry.executed is False
    assert retry.clause == "idempotency"
    # Fail closed: an unknown outcome escalates, it never passes through as an allow.
    assert retry.verdict == "UNKNOWN"


def test_reconciliation_commits_the_order_that_actually_landed(tmp_path):
    r = run_failure_demo(_policy(), tmp_path)
    assert str(EntryState.COMMITTED) in r.steps[2].detail


def test_the_post_reconciliation_retry_does_not_execute(tmp_path):
    r = run_failure_demo(_policy(), tmp_path)
    assert r.steps[3].executed is False
    assert r.steps[3].verdict == "ALLOW"


def test_the_audit_chain_survives_the_failure(tmp_path):
    r = run_failure_demo(_policy(), tmp_path)
    assert r.chain_intact
    assert r.audit_records >= 1


def test_the_demo_needs_no_model(tmp_path, monkeypatch):
    """It must not break on stage because a provider is unreachable."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_VERTEX_PROJECT", raising=False)
    monkeypatch.delenv("GOOGLE_CLOUD_PROJECT", raising=False)
    r = run_failure_demo(_policy(), tmp_path)
    assert r.orders_downstream == 1
