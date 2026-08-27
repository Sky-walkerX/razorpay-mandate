from datetime import timedelta

from mandate.gateway.constraints import ALL_EVALUATORS, item_deny_recent, time_window, velocity
from mandate.gateway.state import Verdict
from mandate.money import rupees
from mandate.policy.models import ConstraintId as C
from tests.gateway.test_constraints_budget import _ctx
from tests.gateway.test_constraints_resolution import _with


def test_all_evaluators_covers_the_nine_ids():
    ctx = _ctx(rupees(10))
    ids = {r.id for r in (fn(ctx) for fn in ALL_EVALUATORS)}
    assert ids == set(C)

def test_velocity_under_cap_allows():
    ctx = _with(_ctx(rupees(10)), C.VELOCITY, {"max_actions": 3, "window": "mandate"})
    ctx.state.actions_in_window = 2
    assert velocity(ctx).result is Verdict.ALLOW

def test_velocity_at_cap_denies_the_next_action():
    ctx = _with(_ctx(rupees(10)), C.VELOCITY, {"max_actions": 3, "window": "mandate"})
    ctx.state.actions_in_window = 3
    assert velocity(ctx).result is Verdict.DENY

def test_before_expiry_allows():
    ctx = _with(_ctx(rupees(10)), C.TIME_WINDOW, {})
    ctx.now = ctx.policy.expires - timedelta(seconds=1)
    assert time_window(ctx).result is Verdict.ALLOW

def test_one_second_after_expiry_denies():
    ctx = _with(_ctx(rupees(10)), C.TIME_WINDOW, {})
    ctx.now = ctx.policy.expires + timedelta(seconds=1)
    assert time_window(ctx).result is Verdict.DENY

def test_exactly_at_expiry_denies():
    """Expiry is exclusive. Ties go to the user, not the agent."""
    ctx = _with(_ctx(rupees(10)), C.TIME_WINDOW, {})
    ctx.now = ctx.policy.expires
    assert time_window(ctx).result is Verdict.DENY

def test_before_issued_denies():
    ctx = _with(_ctx(rupees(10)), C.TIME_WINDOW, {})
    ctx.now = ctx.policy.issued - timedelta(seconds=1)
    assert time_window(ctx).result is Verdict.DENY

def test_recent_sku_denies():
    ctx = _with(_ctx(rupees(10)), C.ITEM_DENY_RECENT,
                {"window_days": 7, "source": "order_history"})
    ctx.state.recent_skus = {"s1"}
    assert item_deny_recent(ctx).result is Verdict.DENY
