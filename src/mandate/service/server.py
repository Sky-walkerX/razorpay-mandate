"""Standalone Mandate Gateway HTTP Service.

Holds RAZORPAY_KEY_*, the price book, and the Issuer public key.
Enforces the process boundary: agents communicate with this service
via scoped bearer tokens over HTTP or MCP.
"""
import json
from datetime import UTC, datetime
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from mandate.downstream.fake import FakeDownstream
from mandate.gateway.action import ActionType, Proposal, ProposalItem
from mandate.gateway.audit import AuditLog
from mandate.gateway.core import Gateway, Mode, verify_capture_capability
from mandate.gateway.idem import Ledger
from mandate.gateway.pricebook import DictPriceBook
from mandate.gateway.revocation import RevocationList
from mandate.gateway.tokens import (
    TokenError,
    TokenExpired,
    TokenMalformed,
    verify_agent_token,
)
from mandate.policy.canonical import policy_hash
from mandate.policy.crypto import SignatureInvalid
from mandate.policy.loader import load as load_policy


def create_app(
    policy_path: Path | str = Path("policies/policy.yaml"),
    public_key_path: Path | str | None = None,
    revocations_path: Path | str = Path("revocations.jsonl"),
    audit_path: Path | str = Path("results/audit.jsonl"),
    ledger_path: Path | str = Path("results/ledger.jsonl"),
    pricebook=None,
    downstream=None,
    capability_secret: str = "mandate_gateway_service_secret_2026",
) -> Starlette:
    pub_hex = None
    if public_key_path and Path(public_key_path).exists():
        pub_hex = Path(public_key_path).read_text().strip()

    policy = load_policy(Path(policy_path), public_key_hex=pub_hex)
    audit = AuditLog(Path(audit_path))
    ledger = Ledger(Path(ledger_path))
    revocations = RevocationList(Path(revocations_path))
    down = downstream if downstream is not None else FakeDownstream()
    pb = pricebook if pricebook is not None else DictPriceBook()

    gateway = Gateway(
        policy=policy,
        downstream=down,
        audit=audit,
        mode=Mode.ENFORCE,
        ledger=ledger,
        pricebook=pb,
        capability_secret=capability_secret,
    )

    def _extract_and_verify_token(req: Request):
        auth_hdr = req.headers.get("Authorization", "")
        if not auth_hdr.startswith("Bearer "):
            return None, JSONResponse({"error": "missing_or_invalid_bearer_token"}, status_code=401)
        token = auth_hdr.removeprefix("Bearer ").strip()

        if pub_hex is not None:
            try:
                claims = verify_agent_token(token, pub_hex)
            except TokenExpired as e:
                return None, JSONResponse({"error": "token_expired", "detail": str(e)}, status_code=403)
            except (SignatureInvalid, TokenMalformed, TokenError) as e:
                return None, JSONResponse({"error": "invalid_token_signature", "detail": str(e)}, status_code=403)

            if revocations.is_revoked(claims.jti) or revocations.is_revoked(claims.mandate_id):
                return None, JSONResponse({"error": "token_revoked", "detail": f"jti {claims.jti} is revoked"}, status_code=403)

            if claims.mandate_id != policy.mandate_id:
                return None, JSONResponse({"error": "mandate_mismatch", "detail": f"token for {claims.mandate_id}, server is {policy.mandate_id}"}, status_code=403)

            return claims, None
        return None, None

    async def health(req: Request):
        return JSONResponse({
            "status": "ok",
            "mandate_id": policy.mandate_id,
            "policy_hash": policy_hash(policy),
        })

    async def create_order(req: Request):
        claims, err_resp = _extract_and_verify_token(req)
        _claims, err_resp = _extract_and_verify_token(req)
        if err_resp:
            return err_resp

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
        except Exception as e:
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return JSONResponse({"error": "malformed_proposal", "detail": str(e)}, status_code=400)

        now = datetime.now(UTC)
        dec = gateway.propose(prop, now=now)
        return JSONResponse(dec.model_dump(mode="json"))

    async def capture_payment(req: Request):
        claims, err_resp = _extract_and_verify_token(req)
        _claims, err_resp = _extract_and_verify_token(req)
        if err_resp:
            return err_resp

        try:
            body = await req.json()
            order_id = body["order_id"]
            amount = int(body["amount"])
            cap = body["capability"]
            idem_key = body["idem_key"]
        except Exception as e:
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            return JSONResponse({"error": "malformed_capture_request", "detail": str(e)}, status_code=400)


        if not verify_capture_capability(cap, idem_key, amount, order_id, capability_secret):
            return JSONResponse({
                "error": "invalid_capture_capability",
                "detail": "Capture capability signature invalid or amount does not match authorized order.",
            }, status_code=403)

        res = down.capture_payment(order_id, amount)
        return JSONResponse({"status": "captured", "result": res})

    routes = [
        Route("/health", health, methods=["GET"]),
        Route("/v1/orders", create_order, methods=["POST"]),
        Route("/v1/payments/capture", capture_payment, methods=["POST"]),
    ]

    return Starlette(routes=routes)
