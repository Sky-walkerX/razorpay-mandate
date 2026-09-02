"""afa.required: the third verdict, and the binding that makes it worth having.

RBI's Digital Payments E-mandate Framework, 2026 permits recurring debits up to
Rs 15,000 without an Additional Factor of Authentication and requires AFA above
that. These tests pin the threshold behaviour and, more importantly, pin what an
approval is keyed on.
"""
from mandate.gateway.approval import ApprovalStore
from mandate.gateway.constraints import afa_required
from mandate.gateway.state import Verdict
from mandate.money import rupees
from mandate.policy.models import ConstraintId as C
from tests.gateway.test_constraints_budget import _ctx
from tests.gateway.test_constraints_resolution import _with

THRESHOLD = {"threshold": int(rupees(15000))}


def test_absent_from_policy_allows():
    assert afa_required(_ctx(rupees(50000))).result is Verdict.ALLOW


def test_at_or_below_the_threshold_allows_without_approval():
    ctx = _with(_ctx(rupees(15000)), C.AFA_REQUIRED, THRESHOLD)
    assert afa_required(ctx).result is Verdict.ALLOW


def test_above_the_threshold_escalates_rather_than_refusing():
    ctx = _with(_ctx(rupees(15001)), C.AFA_REQUIRED, THRESHOLD)
    r = afa_required(ctx)
    assert r.result is Verdict.UNKNOWN
    assert "additional factor" in r.detail


def test_above_the_threshold_allows_once_the_principal_has_approved():
    ctx = _with(_ctx(rupees(20000)), C.AFA_REQUIRED, THRESHOLD)
    ctx.afa_approved = True
    assert afa_required(ctx).result is Verdict.ALLOW


def test_an_approval_is_keyed_on_one_intent_and_does_not_generalise():
    store = ApprovalStore()
    store.approve("intent_aaa")
    assert store.is_approved("intent_aaa")
    assert not store.is_approved("intent_bbb")


def test_approvals_survive_a_reload_from_disk(tmp_path):
    path = tmp_path / "approvals.jsonl"
    ApprovalStore(path).approve("intent_aaa", approver="user_local", factor="otp")
    assert ApprovalStore(path).is_approved("intent_aaa")


def test_the_recorded_approval_names_its_factor(tmp_path):
    store = ApprovalStore(tmp_path / "a.jsonl")
    store.approve("intent_aaa", approver="user_local", factor="otp")
    rec = store.get("intent_aaa")
    assert rec["factor"] == "otp"
    assert rec["approver"] == "user_local"
