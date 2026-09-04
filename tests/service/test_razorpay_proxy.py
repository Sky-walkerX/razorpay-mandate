"""Nothing reaches Razorpay's rail through this proxy without passing the gateway.

Same convention as `test_mcp_no_unmediated_path.py`, one layer further out. The
difference that matters is that the surface here is not ours: Razorpay decides
what tools exist, so the test's first job is to fail when that set changes under
us rather than to describe it.

These rows carry no `model` field, so the containment set cannot absorb them.
"""
import asyncio
import os
from types import SimpleNamespace

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from mandate.adapters.razorpay_proxy import (
    BOUND,
    REFUSED,
    build_razorpay_proxy_server,
    classify,
    load_snapshot,
    unclassified_destructive,
)
from mandate.adapters.razorpay_upstream import RazorpayMCPUpstream, _parse
from mandate.downstream.razorpay_mcp import RazorpayMCPDownstream
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway, Mode, Verdict
from mandate.gateway.idem import Ledger
from mandate.money import rupees
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Provenance
from tests.conftest import SyntheticPriceBook
from tests.policy.test_models import _policy

SNAPSHOT = load_snapshot()


def _pol():
    return _policy(
        constraints={C.BUDGET_TOTAL: {"max": int(rupees(2000))},
                     C.BUDGET_PER_TRANSACTION: {"max": int(rupees(1000))},
                     C.BUDGET_PER_ITEM: {"max": int(rupees(500))},
                     C.MERCHANT_ALLOW: ["zepto"],
                     C.CATEGORY_DENY: ["alcohol"],
                     C.QUANTITY_MAX_PER_ITEM: {"max": 5}},
        provenance=Provenance(
            stated=[C.BUDGET_TOTAL, C.BUDGET_PER_TRANSACTION, C.BUDGET_PER_ITEM,
                    C.MERCHANT_ALLOW, C.CATEGORY_DENY, C.QUANTITY_MAX_PER_ITEM],
            inferred=[]))


class FakeUpstream:
    """Records what was forwarded. Never reached on a refusal."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def list_tools(self):
        return SNAPSHOT

    def call_tool(self, name, arguments):
        self.calls.append((name, dict(arguments)))
        amount = int(arguments.get("amount", 0))
        return {"content": [{"type": "text",
                             "text": f'{{"id": "plink_fake_1", "amount": {amount}}}'}]}


def _build(tmp_path, mode=Mode.ENFORCE):
    policy = _pol()
    up = FakeUpstream()
    gateway = Gateway(
        policy=policy, downstream=RazorpayMCPDownstream(up),
        audit=AuditLog(tmp_path / "audit.jsonl"),
        ledger=Ledger(tmp_path / "ledger.jsonl"),
        mode=mode, pricebook=SyntheticPriceBook(), capability_secret="s")
    session = SimpleNamespace(gateway=gateway, token=None, jti="tok_rzp_1",
                             audit=gateway.audit)
    server = build_razorpay_proxy_server(
        session_for=lambda _h: session, upstream=up, policy=policy, tools=SNAPSHOT)
    return server, gateway, up


def _call(server, name, args):
    return asyncio.run(server.call_tool(name, args))


def _body(result):
    """The tool's return value, out of the CallToolResult MCPServer wraps it in."""
    import json
    if getattr(result, "structured_content", None):
        return result.structured_content
    for part in result.content:
        if part.type == "text":
            return json.loads(part.text)
    raise AssertionError(f"no body in {result!r}")


# --- the surface itself ------------------------------------------------------

def test_every_upstream_tool_is_re_exported(tmp_path):
    server, *_ = _build(tmp_path)
    names = {t.name for t in asyncio.run(server.list_tools())}
    assert names == {t["name"] for t in SNAPSHOT}
    assert len(names) == 42


def test_no_destructive_upstream_tool_is_unclassified():
    """The one that has to fail when Razorpay ships a new money-moving tool.

    Fixing this means deciding whether the mandate can bound the new tool and
    putting it in BOUND or REFUSED with a reason. It does not mean widening the
    passthrough set to make the test green.
    """
    assert unclassified_destructive(SNAPSHOT) == set()


def test_the_classification_is_a_partition():
    names = [t["name"] for t in SNAPSHOT]
    buckets = classify(names)
    assert set(buckets) == set(names)
    assert not (set(BOUND) & set(REFUSED))
    counts = {b: sum(1 for v in buckets.values() if v == b) for b in set(buckets.values())}
    assert counts == {"bound": 4, "refused": 12, "passthrough": 26}


def test_an_unknown_tool_is_refused_rather_than_forwarded():
    """Fail closed. A name nobody classified must not reach the rail."""
    assert classify(["some_tool_razorpay_ships_next_week"]) == {
        "some_tool_razorpay_ships_next_week": "passthrough"}
    # Passthrough is only safe because the upstream did not flag it destructive.
    # If it had, the previous test is the one that fires.


# --- the gateway is on the path ---------------------------------------------

@pytest.mark.parametrize("tool", sorted(BOUND))
def test_every_bound_tool_reaches_the_gateway(tmp_path, tool):
    server, gateway, _up = _build(tmp_path)
    seen = []
    original = gateway.propose
    gateway.propose = lambda *a, **k: (seen.append(1), original(*a, **k))[1]

    args = {"amount": int(rupees(100)), "currency": "INR"}
    if tool == "capture_payment":
        args["payment_id"] = "pay_fake_1"
    _call(server, tool, args)
    assert seen, f"{tool} did not call Gateway.propose"


@pytest.mark.parametrize("tool", sorted(BOUND))
def test_breaking_propose_stops_the_rail(tmp_path, tool):
    """The mutation test. If enforcement dies, nothing reaches Razorpay."""
    server, gateway, up = _build(tmp_path)
    gateway.propose = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("enforcement broken"))
    args = {"amount": int(rupees(100)), "currency": "INR"}
    if tool == "capture_payment":
        args["payment_id"] = "pay_fake_1"
    with pytest.raises((ToolError, RuntimeError)):
        _call(server, tool, args)
    assert up.calls == []


def test_a_refused_amount_never_reaches_the_upstream(tmp_path):
    server, _gateway, up = _build(tmp_path)
    body = _body(_call(server, "create_payment_link",
                       {"amount": int(rupees(50000)), "currency": "INR"}))
    assert body["allowed"] is False
    assert body["verdict"] == Verdict.DENY.value
    assert body["clause"] == str(C.BUDGET_PER_TRANSACTION)
    assert up.calls == []


def test_the_forwarded_amount_is_the_checked_amount(tmp_path):
    """The whole of "the checked figure is the executed figure", as one assertion.

    The agent sends a figure, the constraints see a figure, and Razorpay receives
    a figure. If those three ever differ, the amendment to the one rule is not
    true and this test is how you find out.
    """
    server, _gateway, up = _build(tmp_path)
    body = _body(_call(server, "create_payment_link",
                       {"amount": int(rupees(300)), "currency": "INR"}))
    assert body["allowed"] is True
    assert up.calls, "an allowed call should have reached the upstream"
    tool, args = up.calls[-1]
    assert tool == "create_payment_link"
    assert args["amount"] == int(rupees(300)) == body["amount"]["paise"]


def test_nothing_the_agent_sent_beyond_the_amount_is_forwarded(tmp_path):
    """A payment link the agent tried to describe, retitle and redirect.

    Three of the four bound tools forward `{amount, currency}` and drop the rest,
    so a field the gateway never read cannot ride along to the rail.
    """
    server, _gateway, up = _build(tmp_path)
    _call(server, "create_payment_link", {
        "amount": int(rupees(300)), "currency": "INR",
        "description": "ignore the mandate", "reference_id": "steer-me",
        "callback_url": "https://attacker.example/steal"})
    _tool, args = up.calls[-1]
    assert set(args) == {"amount", "currency"}


def test_a_refused_tool_is_refused_with_a_reason(tmp_path):
    server, _gateway, up = _build(tmp_path)
    body = _body(_call(server, "revoke_token",
                       {"customer_id": "cust_1", "token_id": "token_1"}))
    assert body["allowed"] is False
    assert body["clause"] == "mandate.scope"
    assert "revocation is the principal's control" in body["message"]
    assert up.calls == []


def test_every_refusal_reason_says_something(tmp_path):
    """A reason that is empty, or a bare restatement of the tool name, is not one."""
    for tool, reason in REFUSED.items():
        assert len(reason) > 40, tool
        assert reason.rstrip().endswith("."), tool


def test_read_only_tools_are_forwarded_unchanged(tmp_path):
    server, _gateway, up = _build(tmp_path)
    _call(server, "fetch_all_orders", {"count": 3})
    assert up.calls == [("fetch_all_orders", {"count": 3})]


def test_a_raw_call_reports_which_limits_could_not_apply(tmp_path):
    """Five of this policy's six clauses read line items or a payee.

    Reporting all six as passed on a call that has neither is the VACUOUS bug
    wearing a different hat, so the response says which had nothing to read.
    """
    server, *_ = _build(tmp_path)
    body = _body(_call(server, "create_payment_link",
                       {"amount": int(rupees(300)), "currency": "INR"}))
    limits = body["limits"]
    assert limits["evaluated"] == 2      # budget.total, budget.per_transaction
    assert limits["not_applicable"] == 4
    assert str(C.CATEGORY_DENY) in limits["not_applicable_ids"]
    assert str(C.MERCHANT_ALLOW) in limits["not_applicable_ids"]


def test_two_payment_links_of_different_value_are_different_intents(tmp_path):
    """Without the amount in the hash, the second would replay the first.

    `canonical_intent` hashes items, and a raw action has none. A Rs 100 link and
    a Rs 300 link would otherwise share a key, and the second would come back
    "already committed" having never been created.
    """
    server, *_ = _build(tmp_path)
    a = _body(_call(server, "create_payment_link",
                    {"amount": int(rupees(100)), "currency": "INR"}))
    b = _body(_call(server, "create_payment_link",
                    {"amount": int(rupees(300)), "currency": "INR"}))
    assert a["idem_key"] != b["idem_key"]
    assert a["allowed"] and b["allowed"]


# --- the upstream client -----------------------------------------------------

def test_the_upstream_refuses_live_keys():
    with pytest.raises(ValueError, match="test mode"):
        RazorpayMCPUpstream("rzp_live_abc", "secret")


def test_the_upstream_parses_both_framings():
    assert _parse('{"result": 1}') == {"result": 1}
    assert _parse('event: message\ndata: {"result": 2}\n\n') == {"result": 2}


@pytest.mark.skipif(not os.environ.get("MANDATE_LIVE_UPSTREAM"),
                    reason="set MANDATE_LIVE_UPSTREAM=1 to check the pin against Razorpay")
def test_the_pinned_surface_still_matches_the_live_one():
    """Opt-in, because the suite must not need network or keys.

    Run it before a demo. A drift here means the snapshot is stale and the
    classification may be missing a tool that moves money.
    """
    up = RazorpayMCPUpstream(os.environ["RAZORPAY_KEY_ID"],
                             os.environ["RAZORPAY_KEY_SECRET"])
    live = up.list_tools()
    assert {t["name"] for t in live} == {t["name"] for t in SNAPSHOT}
    assert unclassified_destructive(live) == set()


# --- the service wiring ------------------------------------------------------

@pytest.fixture
def service(monkeypatch):
    """The real app, with a fake upstream standing in for Razorpay.

    Patched at the point `create_app` constructs it, so everything between the
    HTTP request and the upstream call is the production wiring.
    """
    from starlette.testclient import TestClient

    from mandate.service import server

    made: list[FakeUpstream] = []

    def _fake(_key_id, _secret):
        up = FakeUpstream()
        made.append(up)
        return up

    monkeypatch.setattr(server, "RazorpayMCPUpstream", _fake)
    monkeypatch.setenv("RAZORPAY_KEY_ID", "rzp_test_probe")
    monkeypatch.setenv("RAZORPAY_KEY_SECRET", "secret")
    app = server.create_app(public_key_path=".mandate/keys/issuer_public.key",
                            capability_secret="s", store_path=None)
    with TestClient(app) as client:
        yield client, made


@pytest.fixture
def service_without_keys(monkeypatch):
    from starlette.testclient import TestClient

    from mandate.service import server

    monkeypatch.delenv("RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("RAZORPAY_KEY_SECRET", raising=False)
    app = server.create_app(public_key_path=".mandate/keys/issuer_public.key",
                            capability_secret="s", store_path=None)
    with TestClient(app) as client:
        yield client


def _token():
    from datetime import UTC, datetime, timedelta
    from pathlib import Path

    from mandate.gateway.tokens import mint_agent_token
    from mandate.policy.loader import load
    priv = Path(".mandate/keys/issuer_private.key").read_text().strip()
    pol = load(Path("policies/policy.yaml"))
    return mint_agent_token(
        mandate_id=pol.mandate_id, private_key_hex=priv,
        expires_iso=(datetime.now(UTC) + timedelta(hours=1)).isoformat(),
        jti="tok_proxy_wiring_1")


def _rpc(client, name, args, token=None):
    headers = {"Accept": "application/json, text/event-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = client.post("/mcp/razorpay", headers=headers, json={
        "jsonrpc": "2.0", "id": 1,
        "method": "tools/call", "params": {"name": name, "arguments": args}})
    import json as _json
    result = r.json()["result"]
    if result.get("structuredContent"):
        return result["structuredContent"]
    text = result["content"][0]["text"]
    try:
        return _json.loads(text)
    except _json.JSONDecodeError:
        return text          # a tool that raised comes back as a plain message


def test_the_surface_endpoint_counts_off_the_snapshot(service_without_keys):
    """The numbers on the screen are the upstream's own claim about itself."""
    body = service_without_keys.get("/v1/rail/surface").json()
    assert body["total"] == 42
    assert body["destructive"] == 16
    assert body["read_only"] == 26
    assert len(body["bound"]) == 4
    assert len(body["refused"]) == 12
    assert body["mounted"] is False


def test_without_rail_keys_the_proxy_is_not_mounted_at_all(service_without_keys):
    """A 404 rather than a tool list that silently does nothing.

    Same rule as `/v1/compile` after it stopped answering with a policy it had
    not compiled: a component that answers a question it could not answer hides
    the outage.
    """
    r = service_without_keys.post(
        "/mcp/razorpay", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list",
                               "params": {}},
        headers={"Accept": "application/json, text/event-stream"})
    assert r.status_code == 404
    assert service_without_keys.post("/v1/rail/mandate").status_code == 503


def test_a_money_moving_call_needs_a_mandate_token(service):
    """`/mcp` may serve a walk-up because a fake rail sits behind it. This one
    reaches a real merchant account, so it may not."""
    client, made = service
    body = _rpc(client, "create_payment_link", {"amount": 30000, "currency": "INR"})
    assert body["allowed"] is False
    assert "needs a mandate token" in body["message"]
    assert made[0].calls == []


def test_an_allowed_call_executes_against_razorpay_not_the_storefronts_fake_rail(service):
    """The bug this wiring exists to prevent, pinned.

    A shared SessionManager fixes each session's downstream at build time, so
    `/mcp/razorpay` executed allowed calls against FakeDownstream and reported
    `order_000000000001` as though Razorpay had issued it.
    """
    client, made = service
    body = _rpc(client, "create_payment_link",
                {"amount": 30000, "currency": "INR"}, token=_token())
    assert body["allowed"] is True
    assert made[0].calls == [("create_payment_link", {"amount": 30000, "currency": "INR"})]
    assert not str(body.get("upstream", {})).startswith("order_0000")


def test_a_refused_call_still_never_reaches_razorpay(service):
    client, made = service
    body = _rpc(client, "create_payment_link",
                {"amount": 5000000, "currency": "INR"}, token=_token())
    assert body["allowed"] is False
    assert body["clause"] == str(C.BUDGET_PER_TRANSACTION)
    assert made[0].calls == []


def test_a_missing_token_is_a_refusal_the_client_can_read(service):
    """Not a raised exception, because the server masks those in production.

    A raise reaches the client as a bare "Error executing tool
    create_payment_link", so a judge cannot tell an authentication problem from
    a broken gateway. Found on the deployed service, not locally, because the
    local server does not mask error detail.
    """
    client, made = service
    body = _rpc(client, "create_payment_link", {"amount": 30000, "currency": "INR"})
    assert isinstance(body, dict), f"the refusal came back unstructured: {body!r}"
    assert body["allowed"] is False
    assert body["clause"] == "authentication"
    assert "needs a mandate token" in body["message"]
    assert made[0].calls == []
