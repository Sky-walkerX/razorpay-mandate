"""The live judge agent endpoint, driven by a scripted provider.

No Vertex, no network. The point of these tests is the endpoint, the arms and the
ceiling, not whether Gemini can shop.
"""
import json
from datetime import UTC, datetime, timedelta

from starlette.testclient import TestClient

from mandate.gateway.core import Mode
from mandate.gateway.pricebook import DictPriceBook
from mandate.gateway.tokens import mint_agent_token
from mandate.harness.catalog import generate_catalog
from mandate.policy.crypto import generate_keypair
from mandate.policy.loader import dump as dump_policy
from mandate.service.agent_runner import CeilingReached, DailyCallBudget
from mandate.service.server import create_app
from tests.policy.test_models import _policy


class ScriptedProvider:
    """Returns a fixed list of tool calls, then None. Stands in for a real model."""

    model = "scripted-test"

    def __init__(self, calls):
        self._calls = list(calls)
        self.seen = 0

    def next_tool_call(self, system, history, tools):
        self.seen += 1
        if not self._calls:
            return None
        args = self._calls.pop(0)
        return "create_order", args, f"call_{self.seen}", None


def _app(tmp_path, monkeypatch, calls, catalog=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    catalog = catalog if catalog is not None else generate_catalog(seed=42)
    priv_hex, pub_hex = generate_keypair()
    pol = _policy()
    pol_path = tmp_path / "policy.yaml"
    dump_policy(pol, pol_path, private_key_hex=priv_hex)
    pub_path = tmp_path / "issuer_public.key"
    pub_path.write_text(pub_hex + "\n")

    pb = DictPriceBook.from_catalog(catalog)
    provider = ScriptedProvider(calls)
    monkeypatch.setattr("mandate.llm.provider_for", lambda *a, **k: provider)

    app = create_app(
        policy_path=pol_path, public_key_path=pub_path,
        revocations_path=tmp_path / "revocations.jsonl",
        audit_path=tmp_path / "audit.jsonl", ledger_path=tmp_path / "ledger.jsonl",
        pricebook=pb, capability_secret="test_secret_42", catalog=catalog,
    )
    exp = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
    token = mint_agent_token(pol.mandate_id, priv_hex, expires_iso=exp, jti="tok_agent_01")
    return app, {"Authorization": f"Bearer {token}"}, provider


def _sse(raw: str) -> list[dict]:
    out = []
    for block in raw.strip().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[6:]))
    return out


def test_agent_requires_a_token(tmp_path, monkeypatch):
    app, _headers, _p = _app(tmp_path, monkeypatch, [])
    res = TestClient(app).post("/v1/agent", json={"intent": "buy tea"})
    assert res.status_code == 401


def test_agent_rejects_an_empty_intent(tmp_path, monkeypatch):
    app, headers, _p = _app(tmp_path, monkeypatch, [])
    res = TestClient(app).post("/v1/agent", json={"intent": "  "}, headers=headers)
    assert res.status_code == 400


def test_agent_rejects_an_unknown_family(tmp_path, monkeypatch):
    app, headers, _p = _app(tmp_path, monkeypatch, [])
    res = TestClient(app).post(
        "/v1/agent", json={"intent": "buy tea", "family": "no.such.family"}, headers=headers
    )
    assert res.status_code == 400
    assert "families" in res.json()


def test_agent_streams_a_step_and_verdict_per_call(tmp_path, monkeypatch):
    calls = [{"merchant": "zepto", "items": [{"sku": "sku_0000", "qty": 1}]}]
    app, headers, _p = _app(tmp_path, monkeypatch, calls)

    with TestClient(app).stream(
        "POST", "/v1/agent", json={"intent": "buy tea", "family": "clean"}, headers=headers
    ) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        events = _sse("".join(res.iter_text()))

    kinds = [e.get("event") for e in events if "event" in e]
    assert kinds.count("step") == 1
    assert kinds.count("verdict") == 1
    assert kinds[-1] == "done"

    verdict = next(e for e in events if e.get("event") == "verdict")
    assert verdict["verdict"] == "ALLOW"
    assert verdict["executed"] is True


def test_every_event_carries_its_arm(tmp_path, monkeypatch):
    """A screenshot of an unenforced pane must be identifiable as unenforced."""
    calls = [{"merchant": "zepto", "items": [{"sku": "sku_0000", "qty": 1}]}]
    app, headers, _p = _app(tmp_path, monkeypatch, calls)

    with TestClient(app).stream(
        "POST", "/v1/agent",
        json={"intent": "buy tea", "family": "clean", "mode": "observe"},
        headers=headers,
    ) as res:
        events = _sse("".join(res.iter_text()))

    assert all(e.get("mode") == "observe" for e in events if "mode" in e)


def test_observe_executes_what_enforce_refuses(tmp_path, monkeypatch):
    """The contrast the console exists to show, asserted rather than hoped for."""
    over_cap = [{"merchant": "zepto", "items": [{"sku": "sku_0000", "qty": 40}]}]

    def spend(mode):
        app, headers, _p = _app(tmp_path / mode, monkeypatch, list(over_cap))
        with TestClient(app).stream(
            "POST", "/v1/agent",
            json={"intent": "buy lots of tea", "family": "clean", "mode": mode},
            headers=headers,
        ) as res:
            events = _sse("".join(res.iter_text()))
        return next(e for e in events if e.get("event") == "verdict")

    enforced = spend("enforce")
    observed = spend("observe")

    assert enforced["executed"] is False
    assert enforced["verdict"] == "DENY"
    assert observed["executed"] is True
    assert observed["verdict"] == "DENY"  # same verdict, but observe still executes


def test_ceiling_returns_429_and_does_not_call_the_model(tmp_path, monkeypatch):
    monkeypatch.setenv("MANDATE_DAILY_CALL_CEILING", "0")
    app2, headers2, provider2 = _app(tmp_path / "capped", monkeypatch, [])
    res = TestClient(app2).post(
        "/v1/agent", json={"intent": "buy tea", "family": "clean"}, headers=headers2
    )
    assert res.status_code == 429
    assert res.json()["error"] == "daily_call_ceiling_reached"
    assert provider2.seen == 0


def test_families_endpoint_lists_clean(tmp_path, monkeypatch):
    app, _headers, _p = _app(tmp_path, monkeypatch, [])
    body = TestClient(app).get("/v1/agent/families").json()
    assert "clean" in body["families"]
    assert body["ceiling"] >= 0


def test_daily_budget_reserves_refunds_and_caps():
    b = DailyCallBudget(ceiling=10)
    b.reserve(6)
    assert b.remaining == 4
    b.refund(6)
    assert b.remaining == 10
    b.reserve(10)
    try:
        b.reserve(1)
    except CeilingReached:
        pass
    else:
        raise AssertionError("expected CeilingReached")


def test_mode_enum_default_unchanged():
    import inspect

    from mandate.service.session import SessionManager

    sig = inspect.signature(SessionManager.create_session)
    assert sig.parameters["mode"].default is Mode.ENFORCE
