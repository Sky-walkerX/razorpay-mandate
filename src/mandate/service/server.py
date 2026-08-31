"""Standalone Mandate Gateway HTTP Service.

Holds RAZORPAY_KEY_*, the price book, and the Issuer public key.
Enforces the process boundary: agents communicate with this service
via scoped bearer tokens over HTTP or MCP.
"""
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from mandate.downstream.fake import FakeDownstream
from mandate.gateway.action import ActionType, Proposal, ProposalItem
from mandate.gateway.audit import AuditChainBroken
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
from mandate.policy.crypto import SignatureInvalid
from mandate.policy.loader import load as load_policy
from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Policy
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
            "label": "Total budget",
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
            "label": "Max per order",
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
            "label": "Max per item",
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
            "label": "Orders per mandate",
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
            "label": "Max qty per item",
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
    catalog: Catalog | None = None,
    static_dir: Path | str | None = None,
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

    pb = pricebook
    if pb is None:
        if cat is not None:
            pb = DictPriceBook.from_catalog(cat)
        else:
            pb = DictPriceBook()

    pool = token_pool if token_pool is not None else TokenPool([])

    session_manager = SessionManager(
        policy=policy,
        pricebook=pb,
        downstream=down,
        capability_secret=capability_secret,
        issuer_public_key=pub_hex,
        revocations=revocations,
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

    async def get_policy(req: Request):
        # Human-readable parts
        parts = []
        c = policy.constraints
        # 1. Total budget
        if C.BUDGET_TOTAL in c:
            val = c[C.BUDGET_TOTAL]
            lim = int(val["max"]) if "max" in val else 200000
            parts.append({
                "n": 1, "key": "budget.total", "label": "Total budget",
                "kind": "limit", "bound": f"₹{lim/100:,.2f}", "max": lim,
                "source": "heard" if C.BUDGET_TOTAL in policy.provenance.stated else "inferred",
            })
        # 2. Max per order
        if C.BUDGET_PER_TRANSACTION in c:
            val = c[C.BUDGET_PER_TRANSACTION]
            lim = int(val["max"]) if "max" in val else 100000
            parts.append({
                "n": 2, "key": "budget.per_transaction", "label": "Max per order",
                "kind": "limit", "bound": f"₹{lim/100:,.2f}", "max": lim,
                "source": "heard" if C.BUDGET_PER_TRANSACTION in policy.provenance.stated else "inferred",
            })
        # 3. Max per item
        if C.BUDGET_PER_ITEM in c:
            val = c[C.BUDGET_PER_ITEM]
            lim = int(val["max"]) if "max" in val else 50000
            parts.append({
                "n": 3, "key": "budget.per_item", "label": "Max per item",
                "kind": "limit", "bound": f"₹{lim/100:,.2f}", "max": lim,
                "source": "heard" if C.BUDGET_PER_ITEM in policy.provenance.stated else "inferred",
            })
        # 4. Orders per mandate
        if C.VELOCITY in c:
            val = c[C.VELOCITY]
            lim = int(val["max_actions"]) if "max_actions" in val else 3
            parts.append({
                "n": 4, "key": "velocity", "label": "Orders per mandate",
                "kind": "limit", "bound": f"{lim} per mandate", "max": lim,
                "source": "heard" if C.VELOCITY in policy.provenance.stated else "inferred",
            })
        # 5. Max qty per item
        if C.QUANTITY_MAX_PER_ITEM in c:
            val = c[C.QUANTITY_MAX_PER_ITEM]
            lim = int(val["max"]) if "max" in val else 5
            parts.append({
                "n": 5, "key": "quantity.max_per_item", "label": "Max qty per item",
                "kind": "limit", "bound": f"{lim} per item", "max": lim,
                "source": "heard" if C.QUANTITY_MAX_PER_ITEM in policy.provenance.stated else "inferred",
            })
        # 6. Allowed sellers
        if C.MERCHANT_ALLOW in c:
            sellers = c[C.MERCHANT_ALLOW]
            parts.append({
                "n": 6, "key": "merchant.allow", "label": "Allowed sellers",
                "kind": "rule", "bound": ", ".join(s.title() for s in sellers), "max": None,
                "source": "heard" if C.MERCHANT_ALLOW in policy.provenance.stated else "inferred",
            })
        # 7. Blocked categories
        if C.CATEGORY_DENY in c:
            cats = c[C.CATEGORY_DENY]
            parts.append({
                "n": 7, "key": "category.deny", "label": "Blocked categories",
                "kind": "rule", "bound": ", ".join(ct.title() for ct in cats), "max": None,
                "source": "heard" if C.CATEGORY_DENY in policy.provenance.stated else "inferred",
            })
        # 8. Valid until
        if C.TIME_WINDOW in c or policy.expires:
            parts.append({
                "n": 8, "key": "time_window", "label": "Valid until",
                "kind": "rule", "bound": policy.expires.strftime("%-d %b %Y") if policy.expires else "Session", "max": None,
                "source": "heard" if C.TIME_WINDOW in policy.provenance.stated else "inferred",
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
                session = session_manager.create_session(token, claims)
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

        # Read back audit record
        records = session.audit.records()
        rec_json = None
        if records and records[-1].idem_key == dec.idem_key:
            rec_json = records[-1].model_dump(mode="json")

        # Compute updated headroom
        headroom = _compute_headroom(policy, session.gateway._state())

        return JSONResponse({
            "decision": dec_json,
            "record": rec_json,
            "headroom": headroom,
            # Backwards compatibility top-level fields
            "verdict": dec_json["verdict"],
            "clause_id": dec_json["clause_id"],
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
                        {"id": str(cid), "spec": spec, "source": "heard" if cid in compiled_pol.provenance.stated else "inferred"}
                        for cid, spec in compiled_pol.constraints.items()
                    ],
                    "fallback": False,
                    "binding_policy_hash": pol_hash,
                })
            else:
                raise ValueError("Compiler produced ambiguous readings or questions")
        except Exception as e:
            # Honest fallback
            return JSONResponse({
                "prompt": prompt,
                "mandate_id": policy.mandate_id,
                "policy_hash": pol_hash,
                "constraints": [
                    {"id": str(cid), "spec": spec, "source": "heard" if cid in policy.provenance.stated else "inferred"}
                    for cid, spec in policy.constraints.items()
                ],
                "fallback": True,
                "fallback_reason": str(e),
                "binding_policy_hash": pol_hash,
            })

    async def get_conformance(req: Request):
        conf_file = Path("results-conformance/conformance_results.json")
        if conf_file.exists():
            return JSONResponse(json.loads(conf_file.read_text()))
        return JSONResponse({"status": "no_conformance_file_found"}, status_code=404)

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
        Route("/v1/orders", create_order, methods=["POST"]),
        Route("/v1/payments/capture", capture_payment, methods=["POST"]),
        Route("/v1/audit", get_audit, methods=["GET"]),
        Route("/v1/headroom", get_headroom, methods=["GET"]),
        Route("/v1/revoke", revoke_token, methods=["POST"]),
        Route("/v1/compile", compile_policy, methods=["POST"]),
        Route("/v1/conformance", get_conformance, methods=["GET"]),
    ]

    if static_dir and Path(static_dir).exists():
        routes.append(Mount("/", SPAStaticFiles(directory=str(static_dir), html=True)))

    return Starlette(routes=routes, middleware=middleware)
