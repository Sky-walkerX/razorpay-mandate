"""Standalone Mandate Gateway HTTP Service.

Holds RAZORPAY_KEY_*, the price book, and the Issuer public key.
Enforces the process boundary: agents communicate with this service
via scoped bearer tokens over HTTP or MCP.
"""
import asyncio
import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from mcp.server.streamable_http_manager import StreamableHTTPASGIApp
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from mandate.adapters.mcp_server import build_mcp_server
from mandate.downstream.fake import FakeDownstream
from mandate.gateway.action import ActionType, Proposal, ProposalItem
from mandate.gateway.audit import AuditChainBroken
from mandate.gateway.core import Mode
from mandate.gateway.pricebook import DictPriceBook, PriceBook
from mandate.gateway.revocation import RevocationList
from mandate.gateway.state import AccumulatedState, Verdict
from mandate.gateway.tokens import (
    TokenClaims,
    TokenError,
    TokenExpired,
    TokenMalformed,
    verify_agent_token,
)
from mandate.harness.catalog import Catalog
from mandate.policy.canonical import policy_hash
from mandate.policy.crypto import SignatureInvalid, sign_bytes
from mandate.policy.labels import PART_LABELS, label_for
from mandate.policy.loader import load as load_policy
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Policy
from mandate.service.agent_runner import (
    CLEAN,
    DEMO_MAX_STEPS,
    CeilingReached,
    DailyCallBudget,
    FamilyCatalogs,
    TokenBoundClient,
    pricebook_for,
    run_agent_stream,
)
from mandate.service.order_store import OrderStore
from mandate.service.sandbox import (
    SANDBOX_MANDATE_ID,
    SIGN_COMMAND,
    to_sandbox_policy,
)
from mandate.service.session import SessionManager
from mandate.service.token_pool import PoolExhausted, TokenPool


class ServiceMisconfigured(Exception):
    """The service was asked to start without the material it needs to verify anything."""


def _compute_headroom(policy: Policy, state: AccumulatedState) -> list[dict[str, Any]]:
    """Compute remaining headroom against all limits."""
    headroom = []
    c = policy.constraints

    # 1. budget.total
    if C.BUDGET_TOTAL in c and "max" in c[C.BUDGET_TOTAL]:
        lim = int(c[C.BUDGET_TOTAL]["max"])
        used = int(state.spent)
        headroom.append({
            "clause_id": "budget.total",
            "label": label_for("budget.total"),
            "used_paise": used,
            "limit_paise": lim,
            "remaining_paise": max(0, lim - used),
            "unit": "paise",
        })

    # 2. budget.per_transaction
    if C.BUDGET_PER_TRANSACTION in c and "max" in c[C.BUDGET_PER_TRANSACTION]:
        lim = int(c[C.BUDGET_PER_TRANSACTION]["max"])
        headroom.append({
            "clause_id": "budget.per_transaction",
            "label": label_for("budget.per_transaction"),
            "used_paise": 0,
            "limit_paise": lim,
            "remaining_paise": lim,
            "unit": "paise",
        })

    # 3. budget.per_item
    if C.BUDGET_PER_ITEM in c and "max" in c[C.BUDGET_PER_ITEM]:
        lim = int(c[C.BUDGET_PER_ITEM]["max"])
        headroom.append({
            "clause_id": "budget.per_item",
            "label": label_for("budget.per_item"),
            "used_paise": 0,
            "limit_paise": lim,
            "remaining_paise": lim,
            "unit": "paise",
        })

    # 4. velocity
    if C.VELOCITY in c and "max_actions" in c[C.VELOCITY]:
        lim = int(c[C.VELOCITY]["max_actions"])
        used = int(state.action_count)
        headroom.append({
            "clause_id": "velocity",
            "label": label_for("velocity"),
            "used_count": used,
            "limit_count": lim,
            "remaining_count": max(0, lim - used),
            "unit": "count",
        })

    # 5. quantity.max_per_item
    if C.QUANTITY_MAX_PER_ITEM in c and "max" in c[C.QUANTITY_MAX_PER_ITEM]:
        lim = int(c[C.QUANTITY_MAX_PER_ITEM]["max"])
        headroom.append({
            "clause_id": "quantity.max_per_item",
            "label": label_for("quantity.max_per_item"),
            "used_count": 0,
            "limit_count": lim,
            "remaining_count": lim,
            "unit": "count",
        })

    return headroom


class SPAStaticFiles(StaticFiles):
    """StaticFiles subclass that falls back to index.html for client-side SPA routing."""
    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
            if response.status_code == 404 and "." not in path.split("/")[-1]:
                return await super().get_response("index.html", scope)
            return response
        except Exception:
            return await super().get_response("index.html", scope)



def _source(cid, policy) -> str:
    """Where a clause came from, in the interface's vocabulary.

    Three buckets, not two. A clause RBI imposes was neither heard from the user
    nor guessed by the compiler, and labelling it "inferred" would credit the model
    for a statutory floor and invite the user to decline something they cannot.
    """
    if cid in policy.provenance.regulatory:
        return "regulatory"
    if cid in policy.provenance.stated:
        return "heard"
    return "inferred"


def _reserve_pay_shadow(session, prop, now, token: str, shadow_for=None) -> dict | None:
    """Answer the same proposal as UPI Reserve Pay would, for the panel beside
    the verdict.

    Razorpay already ships spending limits for agents on Reserve Pay, so a cap is
    not the claim. The claim is shape: a block names one payee and one total, so
    it lets an attack through that the mandate refuses AND refuses a legitimate
    order at a second shop that the mandate allows. Both directions are reported;
    showing only the first would overstate the rail.

    This is a projection of Reserve Pay's published vocabulary, not an emulation
    of Razorpay's implementation, and the UI says so.
    """
    if shadow_for is None:
        return None
    # The block a user would actually have opened for the shop being used, not
    # whichever payee happened to sort first. See `project_to_reserve_pay`.
    shadow = shadow_for(session, getattr(prop, "merchant", None))
    if shadow is None:
        return None
    dec = shadow.propose(prop, now=now, token=token)
    state = shadow._state()
    block = int(shadow.policy.constraints.get(C.BUDGET_TOTAL, {}).get("max", 0))
    payees = shadow.policy.constraints.get(C.MERCHANT_ALLOW) or []
    return {
        "verdict": str(dec.verdict),
        "clause_id": dec.clause_id,
        "clause_label": label_for(dec.clause_id),
        "message": dec.message,
        "executed": dec.executed,
        "payee": payees[0] if payees else None,
        "block_paise": block,
        "spent_paise": int(getattr(state, "spent", 0) or 0),
        "clauses_kept": sorted(str(c) for c in shadow.policy.constraints),
    }


def create_app(
    policy_path: Path | str = Path("policies/policy.yaml"),
    public_key_path: Path | str | None = None,
    revocations_path: Path | str = Path("revocations.jsonl"),
    audit_path: Path | str = Path("results/audit.jsonl"),
    ledger_path: Path | str = Path("results/ledger.jsonl"),
    pricebook: PriceBook | None = None,
    downstream=None,
    capability_secret: str | None = None,
    token_pool: TokenPool | None = None,
    sandbox_pool: TokenPool | None = None,
    catalog: Catalog | None = None,
    static_dir: Path | str | None = None,
    log_private_key_path: Path | str | None = Path(".mandate/keys/log_private.key"),
    store_path: Path | str | None = None,
) -> Starlette:
    if not capability_secret:
        raise ServiceMisconfigured(
            "capability_secret is required and cannot be empty. Pass MANDATE_CAPABILITY_SECRET "
            "or --capability-secret."
        )

    if not public_key_path or not Path(public_key_path).exists():
        raise ServiceMisconfigured(
            f"issuer public key not found at {public_key_path!r}. The gateway "
            f"service will not start without it. Run `mandate keygen` and "
            f"`mandate sign` first."
        )
    pub_hex = Path(public_key_path).read_text().strip()

    # The log signs its own tree heads with a key distinct from the issuer's, so the
    # issuer key can stay offline. Absent, /v1/audit/head reports 503 rather than
    # serving an unsigned head that would look verified.
    log_private_key_hex = None
    if log_private_key_path and Path(log_private_key_path).exists():
        log_private_key_hex = Path(log_private_key_path).read_text().strip()

    policy = load_policy(Path(policy_path), public_key_hex=pub_hex)
    pol_hash = policy_hash(policy)
    revocations = RevocationList(Path(revocations_path))
    down = downstream if downstream is not None else FakeDownstream()

    # Load catalog & pricebook
    cat = catalog
    if cat is None:
        corpus_file = Path("corpus/corpus.json")
        if corpus_file.exists():
            try:
                from mandate.harness.corpus import load_corpus
                items = load_corpus(corpus_file)
                if items:
                    cat = items[0].mutation.clean_catalog or items[0].mutation.catalog
            except Exception:
                pass
        if cat is None:
            from mandate.harness.catalog import generate_catalog
            cat = generate_catalog(seed=42)

    call_budget = DailyCallBudget()
    families = FamilyCatalogs(clean=cat)
    # `store_path` defaults to None, i.e. in memory. A shared on-disk default
    # would have every test in the suite appending to one file.
    store = OrderStore(store_path)

    pb = pricebook
    if pb is None:
        if cat is not None:
            pb = DictPriceBook.from_catalog(cat)
        else:
            pb = DictPriceBook()

    pool = token_pool if token_pool is not None else TokenPool([])
    # The pool must skip tokens already revoked on disk, or the first session
    # after a restart is handed a dead token.
    if pool.is_revoked is None:
        pool.is_revoked = revocations.is_revoked

    # A second pool, bound offline to the reserved sandbox mandate rather than to
    # the signed one. It is separate rather than mixed in because `claim_token`
    # hands out whatever is next, and a sandbox session must not be opened on a
    # token bound to the signed mandate — `Gateway._verify_token` would reject it,
    # correctly, and the judge would see an authentication error instead of the
    # feature. Empty pool means the sandbox is simply unavailable, not open.
    sbx_pool = sandbox_pool if sandbox_pool is not None else TokenPool([])
    if sbx_pool.is_revoked is None:
        sbx_pool.is_revoked = revocations.is_revoked

    session_manager = SessionManager(
        policy=policy,
        pricebook=pb,
        downstream=down,
        capability_secret=capability_secret,
        issuer_public_key=pub_hex,
        revocations=revocations,
        # Sized so the token pools, not this cap, decide how many people can hold
        # a session at once. House and sandbox sessions share one budget, and the
        # cap evicts the least recently active when it is reached — so a cap below
        # the mintable total would throw a judge out mid-demo because *other*
        # people had claimed tokens, and they would see `session_not_found`. The
        # 100 floor keeps the old behaviour when no pools are configured.
        max_sessions=max(100, pool.total_count + sbx_pool.total_count),
    )

    def _extract_and_verify_token(req: Request) -> tuple[str | None, TokenClaims | None, JSONResponse | None]:
        auth_hdr = req.headers.get("Authorization", "")
        if not auth_hdr.startswith("Bearer "):
            return None, None, JSONResponse({"error": "missing_or_invalid_bearer_token"}, status_code=401)
        token = auth_hdr.removeprefix("Bearer ").strip()

        try:
            claims = verify_agent_token(token, pub_hex)
        except TokenExpired as e:
            return None, None, JSONResponse({"error": "token_expired", "detail": str(e)}, status_code=403)
        except (SignatureInvalid, TokenMalformed, TokenError) as e:
            return None, None, JSONResponse({"error": "invalid_token_signature", "detail": str(e)}, status_code=403)

        if revocations.is_revoked(claims.jti) or revocations.is_revoked(claims.mandate_id):
            return None, None, JSONResponse({"error": "token_revoked", "detail": f"jti {claims.jti} is revoked"}, status_code=403)

        return token, claims, None

    def _audit_row_for(session, decision):
        """The audit record this decision wrote, or None.

        `Gateway.propose` returns early on `authentication` and `pricebook`
        before appending anything, so a missing row is a real outcome rather
        than a failed lookup, and the storefront still shows those refusals.
        """
        records = session.audit.records()
        if records and records[-1].idem_key == decision.idem_key:
            return records[-1]
        return None

    async def health(req: Request) -> JSONResponse:
        return JSONResponse({
            "status": "ok",
            "mandate_id": policy.mandate_id,
            "policy_hash": pol_hash,
            "tokens_available": pool.available_count,
            "pool_available": pool.available_count,
            "time": datetime.now(UTC).isoformat(),
        })

    async def create_session(req: Request) -> JSONResponse:
        try:
            token, claims = pool.claim_token(pub_hex)
        except PoolExhausted:
            return JSONResponse({
                "error": "token_pool_exhausted",
                "message": "no judge sessions available",
            }, status_code=503)

        session_manager.create_session(token, claims)
        return JSONResponse({
            "token": token,
            "jti": claims.jti,
            "mandate_id": claims.mandate_id,
            "policy_hash": pol_hash,
            "expires_at": claims.exp,
            "remaining_tokens": pool.available_count,
        })

    async def get_catalog(req: Request):
        if cat is None:
            return JSONResponse([])
        items = [
            {
                "sku": p.sku,
                "title": p.title,
                "category": p.category,
                "merchant": p.merchant,
                "unit_price": int(p.unit_price),
            }
            for p in cat.products
        ]
        return JSONResponse(items)

    def _bound(key: str) -> tuple[str, int | None] | None:
        """The clause's bound as a person reads it, and as a number.

        Returns None for a clause this policy does not set, so the caller drops
        the row rather than printing a bound nobody signed.
        """
        c = policy.constraints
        if key == "budget.total" and C.BUDGET_TOTAL in c:
            lim = int(c[C.BUDGET_TOTAL].get("max", 200000))
            return f"\u20b9{lim/100:,.2f}", lim
        if key == "budget.per_transaction" and C.BUDGET_PER_TRANSACTION in c:
            lim = int(c[C.BUDGET_PER_TRANSACTION].get("max", 100000))
            return f"\u20b9{lim/100:,.2f}", lim
        if key == "budget.per_item" and C.BUDGET_PER_ITEM in c:
            lim = int(c[C.BUDGET_PER_ITEM].get("max", 50000))
            return f"\u20b9{lim/100:,.2f}", lim
        if key == "velocity" and C.VELOCITY in c:
            lim = int(c[C.VELOCITY].get("max_actions", 3))
            return f"{lim} orders", lim
        if key == "quantity.max_per_item" and C.QUANTITY_MAX_PER_ITEM in c:
            lim = int(c[C.QUANTITY_MAX_PER_ITEM].get("max", 5))
            return f"{lim} per item", lim
        if key == "merchant.allow" and C.MERCHANT_ALLOW in c:
            return ", ".join(s.title() for s in c[C.MERCHANT_ALLOW]), None
        if key == "category.deny" and C.CATEGORY_DENY in c:
            return ", ".join(ct.title() for ct in c[C.CATEGORY_DENY]), None
        if key == "time.window" and (C.TIME_WINDOW in c or policy.expires):
            return policy.expires.strftime("%-d %b %Y") if policy.expires else "Session", None
        return None

    async def get_policy(req: Request):
        """The signed document, part by part.

        Driven off `PART_LABELS` rather than a hand-written block per clause.
        The block it replaces retyped every label, every Part number and the key
        itself, and one of those copies had drifted: it filed the expiry clause
        under `time_window` while the policy, the audit log and `evidence.json`
        all call it `time.window`, so the web could not match that row to a
        label and showed the bare identifier for it.
        """
        parts = []
        for n, part in enumerate(PART_LABELS, start=1):
            bound = _bound(part["key"])
            if bound is None:
                continue
            text, maximum = bound
            parts.append({
                "n": n,
                "key": part["key"],
                "label": part["label"],
                "kind": part["kind"],
                "bound": text,
                "max": maximum,
                "source": _source(C(part["key"]), policy),
            })

        return JSONResponse({
            "mandate_id": policy.mandate_id,
            "policy_hash": pol_hash,
            "signed_by": policy.principal,
            "signed_on": policy.issued.isoformat(),
            "parts": parts,
            "signature_valid": True,
        })

    async def create_order(req: Request):
        token, claims, err_resp = _extract_and_verify_token(req)
        if err_resp is not None:
            return err_resp
        assert claims is not None and token is not None

        session = session_manager.get_session(claims.jti)
        if session is None:
            # Fallback for single-token tests or non-session harness
            if not pool.total_count:
                session = session_manager.create_session(
                    token, claims, pricebook=_week_pricebook())
            else:
                return JSONResponse({
                    "error": "session_not_found",
                    "detail": f"no active session for token jti {claims.jti}. Call POST /v1/sessions first.",
                }, status_code=409)

        try:
            body = await req.json()
            items = [ProposalItem(**it) for it in body.get("items", [])]
            prop = Proposal(
                type=ActionType.CREATE_ORDER,
                merchant=body.get("merchant", "unknown"),
                items=items,
                attempt=body.get("attempt", 1),
                downstream_ref=body.get("downstream_ref"),
            )
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return JSONResponse({"error": "malformed_proposal", "detail": str(e)}, status_code=400)

        now = datetime.now(UTC)
        dec = session.gateway.propose(prop, now=now, token=token)
        dec_json = dec.model_dump(mode="json")

        rec = _audit_row_for(session, dec)
        rec_json = rec.model_dump(mode="json") if rec is not None else None
        # The session's own policy, not the service's. A sandbox order filed
        # under the signed mandate's id would make the order history claim the
        # signed document authorised something a visitor typed.
        store.record(decision=dec, audit_record=rec, jti=claims.jti,
                     mandate_id=session.gateway.policy.mandate_id, source="http")

        # Against the session's own policy. A sandbox session showing the house
        # mandate's headroom would put the wrong limits on the visitor's meter
        # while their clauses did the deciding — the same mismatch, one layer up.
        headroom = _compute_headroom(session.gateway.policy, session.gateway._state())

        # Always after the real decision, and never able to disturb it. The
        # shadow is a talking point; the gateway is the product.
        try:
            reserve_pay = _reserve_pay_shadow(
                session, prop, now, token, shadow_for=session_manager.shadow_for)
        except Exception:  # a comparison must never cost a verdict
            reserve_pay = None

        return JSONResponse({
            "decision": dec_json,
            "record": rec_json,
            "headroom": headroom,
            "reserve_pay": reserve_pay,
            # Backwards compatibility top-level fields
            "verdict": dec_json["verdict"],
            "clause_id": dec_json["clause_id"],
            "clause_label": label_for(dec_json["clause_id"]),
            "message": dec_json["message"],
            "idem_key": dec_json["idem_key"],
            "downstream": dec_json["downstream"],
            "executed": dec_json["executed"],
            "capability": dec_json["capability"],
        })

    async def capture_payment(req: Request):
        token, claims, err_resp = _extract_and_verify_token(req)
        if err_resp is not None:
            return err_resp
        assert claims is not None and token is not None

        session = session_manager.get_session(claims.jti)
        gw = session.gateway if session else session_manager.create_session(token, claims).gateway

        try:
            body = await req.json()
            order_id = body["order_id"]
            amount = int(body["amount"])
            cap = body["capability"]
            idem_key = body["idem_key"]
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return JSONResponse({"error": "malformed_capture_request", "detail": str(e)}, status_code=400)

        dec = gw.capture_payment(
            order_id=order_id, amount=amount, capability=cap,
            idem_key=idem_key, token=token,
        )
        if dec.verdict is not Verdict.ALLOW:
            return JSONResponse({
                "error": "invalid_capture_capability",
                "clause_id": dec.clause_id,
                "clause_label": label_for(dec.clause_id),
                "detail": dec.message,
            }, status_code=403)
        return JSONResponse({"status": "captured", "result": dec.downstream})

    async def get_audit(req: Request):
        _token, claims, err_resp = _extract_and_verify_token(req)
        if err_resp is not None:
            return err_resp
        assert claims is not None

        session = session_manager.get_session(claims.jti)
        if session is None:
            return JSONResponse({"records": [], "chain_intact": True})

        chain_intact = True
        try:
            session.audit.verify_chain()
        except AuditChainBroken:
            chain_intact = False

        return JSONResponse({
            "records": [r.model_dump(mode="json") for r in session.audit.records()],
            "chain_intact": chain_intact,
        })

    async def get_headroom(req: Request):
        _token, claims, err_resp = _extract_and_verify_token(req)
        if err_resp is not None:
            return err_resp
        assert claims is not None

        session = session_manager.get_session(claims.jti)
        state = session.gateway._state() if session else AccumulatedState()
        return JSONResponse(_compute_headroom(policy, state))

    async def revoke_token(req: Request):
        _token, claims, err_resp = _extract_and_verify_token(req)
        if err_resp is not None:
            return err_resp
        assert claims is not None

        # Revoke caller own jti only
        revocations.revoke(claims.jti, reason="judge_manual_revocation")
        pool.retire_token(claims.jti)
        session_manager.evict_session(claims.jti)

        return JSONResponse({"status": "revoked", "jti": claims.jti})

    async def compile_policy(req: Request):
        try:
            body = await req.json()
            prompt = body.get("prompt", "")
        except Exception:
            prompt = ""

        if not prompt:
            prompt = "Order groceries for the week from Zepto, Blinkit or Instamart under Rs 2000 total"

        # Attempt temperature-0 compile with 8s timeout
        try:
            import asyncio
            from datetime import timedelta

            from mandate.compiler.compile import compile_intent
            from mandate.llm import provider_for
            
            provider = provider_for()
            exp = datetime.now(UTC) + timedelta(days=30)
            res = await asyncio.wait_for(
                asyncio.to_thread(compile_intent, prompt, "user_local", "agt_shopper", exp, provider),
                timeout=30.0,
            )
            if res.policy:
                compiled_pol = res.policy
                return JSONResponse({
                    "prompt": prompt,
                    "mandate_id": compiled_pol.mandate_id,
                    "policy_hash": policy_hash(compiled_pol),
                    "constraints": [
                        {"id": str(cid), "label": label_for(str(cid)), "spec": spec,
                         "source": _source(cid, compiled_pol)}
                        for cid, spec in compiled_pol.constraints.items()
                    ],
                    "compiled": True,
                    "fallback": False,
                    "binding_policy_hash": pol_hash,
                })
            # The compiler declining is not an error and is reported as itself,
            # the same way /v1/sandbox reports it.
            return JSONResponse({
                "prompt": prompt,
                "compiled": False,
                "kind": "declined",
                "reason": "the compiler would not commit to a single reading of that",
                "questions": [q.model_dump(mode="json") for q in (res.questions or [])],
                "binding_policy_hash": pol_hash,
            })
        except Exception as e:
            # It used to answer with the signed policy's own clauses here, on the
            # reasoning that this endpoint only renders and so a fallback was
            # harmless. That was wrong, and provably: the deployed service had no
            # Vertex project set and then no Vertex permission, so for days this
            # returned the demo mandate's nine clauses to anyone who typed their
            # own intent, labelled `fallback: true` and otherwise indistinguishable
            # from a real compile. Nothing on the page read that flag. An endpoint
            # that answers a question it could not answer is worse than one that
            # fails, because the failure is what gets noticed and fixed.
            #
            # `constraints` is now absent rather than borrowed. `/v1/sandbox` makes
            # the same choice for the same reason.
            return JSONResponse({
                "prompt": prompt,
                "compiled": False,
                "kind": "error",
                "reason": str(e),
                "binding_policy_hash": pol_hash,
            }, status_code=502)

    async def create_sandbox(req: Request) -> JSONResponse:
        """Compile a visitor's own intent and enforce it, unsigned, for one session.

        The whole feature is that the clauses doing the refusing are the ones the
        visitor's sentence compiled to. So nothing here rewrites what they asked
        for, and nothing falls back to the signed policy when the compiler cannot
        read them: `/v1/compile` does fall back, because its job is to render
        something, and this one's job is to enforce something. Enforcing the
        house mandate while a judge believes their own is being tested would be a
        rigged demo.

        The compiler refusing is a real outcome and is returned as one. It runs
        two readings at temperature 0 and declines when they disagree, which is
        the determinism check working rather than an error to paper over.
        """
        try:
            body = await req.json()
            prompt = (body.get("prompt") or "").strip()
        except (ValueError, json.JSONDecodeError):
            prompt = ""

        if not prompt:
            return JSONResponse(
                {"error": "empty_prompt", "detail": "say what the agent may spend"},
                status_code=400,
            )

        if not sbx_pool.available_count:
            return JSONResponse({
                "error": "sandbox_unavailable",
                "detail": "no sandbox tokens remain. Sandbox tokens are minted "
                          "offline (`mandate mint-pool --mandate-id "
                          f"{SANDBOX_MANDATE_ID}`); the service cannot mint one, "
                          "which is the same property that stops it signing a policy.",
            }, status_code=503)

        from datetime import timedelta

        from mandate.compiler.compile import compile_intent
        from mandate.llm import provider_for

        try:
            provider = provider_for()
            exp = datetime.now(UTC) + timedelta(days=30)
            res = await asyncio.wait_for(
                asyncio.to_thread(
                    compile_intent, prompt, "judge", "agt_shopper", exp, provider
                ),
                timeout=30.0,
            )
        except TimeoutError:
            # `kind` separates the three ways this can come back empty, because
            # they mean opposite things. A timeout says nothing about the intent
            # and is worth retrying; a decline is the determinism check firing and
            # retrying the same words will decline again. Collapsing them into one
            # message had the page explain a slow network as a careful compiler.
            return JSONResponse({
                "compiled": False, "kind": "timeout",
                "reason": "the compiler did not answer in time",
            }, status_code=504)
        except Exception as e:
            return JSONResponse(
                {"compiled": False, "kind": "error", "reason": str(e)}, status_code=502
            )

        if res.policy is None:
            # Not an error. Two readings at temperature 0 disagreed, or the
            # compiler needs something it was not told, and it declined rather
            # than guessing at what someone may spend.
            return JSONResponse({
                "compiled": False,
                "kind": "declined",
                "reason": "the compiler would not commit to a single reading of that",
                "questions": [q.model_dump(mode="json") for q in (res.questions or [])],
            })

        sbx_policy = to_sandbox_policy(res.policy)

        try:
            token, claims = sbx_pool.claim_token(pub_hex)
        except PoolExhausted:
            return JSONResponse(
                {"error": "sandbox_unavailable", "detail": "no sandbox tokens remain"},
                status_code=503,
            )

        session_manager.create_session(token, claims, policy=sbx_policy)

        return JSONResponse({
            "compiled": True,
            "token": token,
            "jti": claims.jti,
            "mandate_id": sbx_policy.mandate_id,
            "policy_hash": policy_hash(sbx_policy),
            # Said plainly and in the payload, not only in the interface copy. A
            # client reading this API has to be able to tell the two apart too.
            "signed": False,
            "signed_mandate_id": policy.mandate_id,
            "sign_command": SIGN_COMMAND,
            "source_text": sbx_policy.source_text,
            "expires_at": claims.exp,
            "constraints": [
                {"id": str(cid), "label": label_for(str(cid)), "spec": spec,
                 "source": _source(cid, sbx_policy)}
                for cid, spec in sbx_policy.constraints.items()
            ],
            "questions": [q.model_dump(mode="json") for q in (res.questions or [])],
            "sandbox_tokens_remaining": sbx_pool.available_count,
        })

    async def get_store_orders(req: Request) -> Response:
        """The customer's order history. Unauthenticated on purpose: it is the
        shop's own record of what it sold, and carries no token or capability."""
        raw = req.query_params.get("week")
        week = int(raw) if raw and raw.isdigit() else None

        etag = store.etag()
        if req.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})

        rows = store.orders(week=week)
        executed = [r for r in rows if r.status == "EXECUTED"]
        return JSONResponse({
            "week": week if week is not None else store.current_week,
            "weeks": [w.model_dump(mode="json") for w in store.weeks()],
            "family": store.week_family(week),
            "orders": [
                {**r.model_dump(mode="json"), "clause_label": label_for(r.clause_id)}
                for r in rows
            ],
            "totals": {
                "executed_paise": sum(r.amount_paise for r in executed),
                "executed_count": len(executed),
                "refused_count": sum(1 for r in rows if r.status == "REFUSED"),
            },
        }, headers={"ETag": etag})

    async def get_store_week(req: Request) -> JSONResponse:
        return JSONResponse({
            "week": store.current_week,
            "family": store.week_family(),
            "families": families.families,
            "corpus_hash": families.corpus_hash,
        })

    async def advance_store_week(req: Request) -> JSONResponse:
        """Start the next week. A week is a new mandate instance under the same
        signed policy, so this writes a label and touches no constraint."""
        _token, _claims, err_resp = _extract_and_verify_token(req)
        if err_resp is not None:
            return err_resp

        try:
            body = await req.json()
        except (ValueError, TypeError, json.JSONDecodeError):
            body = {}

        family = (body.get("family") or CLEAN).strip()
        if families.get(family) is None:
            # Labelling a week with an attack the corpus cannot load would leave
            # the page claiming a catalog nobody is shopping.
            return JSONResponse({"error": f"unknown family {family!r}",
                                 "families": families.families}, status_code=400)

        marker = store.advance_week(family=family)
        return JSONResponse({"week": marker.week, "family": marker.family})

    async def get_conformance(req: Request):
        conf_file = Path("results-conformance/conformance_results.json")
        if conf_file.exists():
            return JSONResponse(json.loads(conf_file.read_text()))
        return JSONResponse({"status": "no_conformance_file_found"}, status_code=404)

    async def get_ap2_mandate(req: Request):
        from mandate.ap2.render import render_ap2_mandate
        doc = render_ap2_mandate(policy)
        return JSONResponse(doc.model_dump(mode="json"))

    def _session_audit(req: Request):
        """Resolve the caller's per-session audit log, or an error response."""
        _token, claims, err_resp = _extract_and_verify_token(req)
        if err_resp is not None:
            return None, err_resp
        assert claims is not None
        session = session_manager.get_session(claims.jti)
        if session is None:
            return None, JSONResponse({"error": "no session for this token"}, status_code=404)
        return session.audit, None

    async def get_audit_head(req: Request):
        audit_log, err_resp = _session_audit(req)
        if err_resp is not None:
            return err_resp

        root = audit_log.get_merkle_root()
        size = len(audit_log.records())
        ts = datetime.now(UTC).isoformat()
        msg = f"{size}:{root}:{ts}".encode()

        if log_private_key_hex is None:
            return JSONResponse(
                {"error": "gateway holds no log signing key; run 'mandate keygen --log'"},
                status_code=503,
            )
        sig = sign_bytes(msg, log_private_key_hex)
        return JSONResponse({"size": size, "root": root, "ts": ts, "sig": sig})

    async def get_audit_proof(req: Request):
        audit_log, err_resp = _session_audit(req)
        if err_resp is not None:
            return err_resp
        try:
            seq = int(req.query_params.get("seq", 1))
            return JSONResponse(audit_log.get_inclusion_proof(seq))
        except (ValueError, IndexError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)

    async def get_audit_consistency(req: Request):
        audit_log, err_resp = _session_audit(req)
        if err_resp is not None:
            return err_resp
        try:
            from_cnt = int(req.query_params.get("from", 1))
            to_cnt = int(req.query_params.get("to", len(audit_log.records())))
            return JSONResponse(audit_log.get_consistency_proof(from_cnt, to_cnt))
        except (ValueError, IndexError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)


    async def list_agent_families(req: Request):
        return JSONResponse({
            "families": families.families,
            "calls_remaining_today": call_budget.remaining,
            "ceiling": call_budget.ceiling,
        })

    async def run_agent(req: Request):
        """Run a live model agent against this session's gateway, streaming each step.

        The agent is the same ShoppingAgent the sweep drives. It reaches the gateway
        through DirectClient, so every proposal still passes token verification,
        resolution and the nine clauses.
        """
        _token, claims, err_resp = _extract_and_verify_token(req)
        if err_resp is not None:
            return err_resp
        assert claims is not None

        try:
            body = await req.json()
        except (ValueError, TypeError, json.JSONDecodeError):
            body = {}

        intent = (body.get("intent") or "").strip()
        if not intent:
            return JSONResponse({"error": "intent is required"}, status_code=400)

        family = body.get("family") or CLEAN
        catalog = families.get(family)
        if catalog is None:
            return JSONResponse(
                {"error": f"unknown family {family!r}", "families": families.families},
                status_code=400,
            )

        mode = Mode.OBSERVE if body.get("mode") == "observe" else Mode.ENFORCE
        compromised = bool(body.get("compromised"))
        # The console sends no max_steps, so both arms take DEMO_MAX_STEPS and the
        # comparison stays honest. 30 remains the hard ceiling for an explicit caller.
        max_steps = min(int(body.get("max_steps") or DEMO_MAX_STEPS), 30)

        try:
            call_budget.reserve(max_steps)
        except CeilingReached as e:
            return JSONResponse(
                {"error": "daily_call_ceiling_reached", "detail": str(e),
                 "ceiling": call_budget.ceiling},
                status_code=429,
            )

        # One session is one run. Recreating it with the requested mode and the
        # selected catalog's price book means /v1/audit afterwards shows exactly
        # this run, and a hostile SKU resolves instead of failing closed.
        session = session_manager.create_session(
            _token, claims, mode=mode, pricebook=pricebook_for(catalog)
        )

        try:
            from mandate.llm import provider_for

            provider = provider_for()
        except Exception as e:  # any provider import or config failure is a 503
            call_budget.refund(max_steps)
            return JSONResponse({"error": "no_model_provider", "detail": str(e)},
                                status_code=503)

        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        sentinel = object()
        # Written by the producer thread, read by the refund. It must not be
        # derived from what the browser consumed: a judge who closes the tab
        # stops the stream, not the agent, and refunding calls the model went on
        # to make would let the ceiling be walked past a tab at a time.
        progress = {"steps": 0}

        def on_decision(decision) -> None:
            # Only the enforced arm reaches the customer's order history. An
            # OBSERVE row is a counterfactual shown beside the real one in the
            # console; filing it in the storefront would present money that
            # never moved as money that did.
            if mode is not Mode.ENFORCE:
                return
            store.record(
                decision=decision, audit_record=_audit_row_for(session, decision),
                jti=claims.jti, mandate_id=policy.mandate_id, source="agent",
            )

        def produce() -> None:
            try:
                for ev in run_agent_stream(
                    intent=intent, catalog=catalog,
                    client=TokenBoundClient(session.gateway, _token),
                    provider=provider, compromised=compromised, mode=mode,
                    max_steps=max_steps, on_decision=on_decision,
                ):
                    if ev.get("event") == "step":
                        progress["steps"] = int(ev.get("n") or progress["steps"])
                    loop.call_soon_threadsafe(queue.put_nowait, ev)
            # This is the error boundary for a worker thread. Anything the model,
            # the provider or the gateway raises has to reach the browser as an
            # `error` event, because a thread that dies silently hangs the stream.
            except Exception as e:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"event": "error", "mode": mode.value, "detail": f"{type(e).__name__}: {e}"},
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, sentinel)

        async def events():
            yield (
                "event: start\ndata: "
                + json.dumps({
                    "mode": mode.value, "family": family, "compromised": compromised,
                    "intent": intent, "jti": claims.jti, "max_steps": max_steps,
                })
                + "\n\n"
            )
            task = asyncio.create_task(asyncio.to_thread(produce))
            try:
                while True:
                    ev = await queue.get()
                    if ev is sentinel:
                        break
                    yield f"event: {ev['event']}\ndata: " + json.dumps(ev, default=str) + "\n\n"
            finally:
                try:
                    await task
                finally:
                    # The reservation is the worst case; most runs stop long before
                    # it. Give back what was not spent, or a console press costs the
                    # ceiling 2 x max_steps however short the run was. One call per
                    # step plus the one that answered "nothing further" -- transient
                    # provider retries are not counted back, so this under-refunds
                    # rather than over-refunds.
                    call_budget.refund(max(0, max_steps - (progress["steps"] + 1)))

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # One gateway session per MCP connection per week. Keying on the week means
    # advancing it claims a fresh token and fresh accumulators, which is the
    # whole of "a week is a new mandate instance under the same signed policy".
    mcp_sessions: dict[tuple[str, int], str] = {}

    def _week_catalog() -> Catalog:
        """The catalog the storefront is currently serving.

        A hostile week serves a poisoned catalog from the frozen corpus. The
        agent reads seller text from it and can do nothing with what it reads,
        because create_order takes a SKU and a quantity.
        """
        return families.get(store.week_family()) or cat

    def _week_pricebook() -> PriceBook:
        """The service's configured price book in a clean week.

        Only a hostile week derives one from its catalog, and it must: a poisoned
        SKU the book does not carry would be denied on `pricebook` before any
        clause ran, so the attack would never reach the thing being tested.
        """
        family = store.week_family()
        if family == CLEAN:
            return pb
        catalog = families.get(family)
        return pricebook_for(catalog) if catalog is not None else pb

    def _session_for(headers):
        """Resolve the caller's gateway session, claiming a pool token lazily.

        The token never reaches the model. An MCP client asks for an order and
        the credential is attached on this side of the boundary, which is the
        property the whole thing rests on. An explicit bearer overrides, so a
        judge can drive this surface with a token they minted themselves.
        """
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth.split(" ", 1)[1].strip()
            claims = verify_agent_token(token, pub_hex)
            return (session_manager.get_session(claims.jti)
                    or session_manager.create_session(
                        token, claims, pricebook=_week_pricebook()))

        # No session id means a non-HTTP transport or an in-process call. One
        # walk-up session is the honest answer for a single-instance demo.
        key = (headers.get("mcp-session-id") or "_walkup", store.current_week)
        jti = mcp_sessions.get(key)
        if jti is not None:
            existing = session_manager.get_session(jti)
            if existing is not None:
                return existing

        token, claims = pool.claim_token(pub_hex)
        mcp_sessions[key] = claims.jti
        return session_manager.create_session(
            token, claims, pricebook=_week_pricebook())

    mcp_server = build_mcp_server(
        session_for=_session_for,
        catalog_for=_week_catalog,
        store=store,
        policy=policy,
        headroom_fn=_compute_headroom,
        policy_hash=pol_hash,
    )
    # Called for its side effect: it builds the StreamableHTTP session manager.
    # The Starlette app it returns is discarded, because Starlette does not run
    # a mounted sub-app's lifespan and the manager would never start. The ASGI
    # handler is mounted directly and the manager runs from this app's lifespan.
    #
    # DNS-rebinding protection is off deliberately. Left on, it defaults to
    # allowing localhost Host and Origin headers only, which rejects every
    # request on Cloud Run. The bearer token is what authorises a caller here.
    mcp_server.streamable_http_app(
        streamable_http_path="/mcp",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False),
    )
    mcp_asgi = StreamableHTTPASGIApp(mcp_server.session_manager)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        async with mcp_server.session_manager.run():
            yield

    middleware = [
        Middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )
    ]

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/v1/sessions", create_session, methods=["POST"]),
        Route("/v1/catalog", get_catalog, methods=["GET"]),
        Route("/v1/policy", get_policy, methods=["GET"]),
        Route("/v1/mandate/ap2", get_ap2_mandate, methods=["GET"]),
        Route("/v1/orders", create_order, methods=["POST"]),
        Route("/v1/payments/capture", capture_payment, methods=["POST"]),
        Route("/v1/audit", get_audit, methods=["GET"]),
        Route("/v1/audit/head", get_audit_head, methods=["GET"]),
        Route("/v1/audit/proof", get_audit_proof, methods=["GET"]),
        Route("/v1/audit/consistency", get_audit_consistency, methods=["GET"]),
        Route("/v1/headroom", get_headroom, methods=["GET"]),
        Route("/v1/revoke", revoke_token, methods=["POST"]),
        Route("/v1/compile", compile_policy, methods=["POST"]),
        Route("/v1/sandbox", create_sandbox, methods=["POST"]),
        Route("/v1/conformance", get_conformance, methods=["GET"]),
        Route("/v1/store/orders", get_store_orders, methods=["GET"]),
        Route("/v1/store/week", get_store_week, methods=["GET"]),
        Route("/v1/store/advance", advance_store_week, methods=["POST"]),
        # A non-function endpoint leaves `methods` unset, so GET, POST and
        # DELETE all reach the MCP handler. Registered before the SPA mount.
        Route("/mcp", endpoint=mcp_asgi),
        Route("/v1/agent", run_agent, methods=["POST"]),
        Route("/v1/agent/families", list_agent_families, methods=["GET"]),
    ]

    if static_dir and Path(static_dir).exists():
        routes.append(Mount("/", SPAStaticFiles(directory=str(static_dir), html=True)))

    return Starlette(routes=routes, middleware=middleware, lifespan=lifespan)
