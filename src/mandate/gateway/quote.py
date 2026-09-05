"""Ed25519 merchant-signed price quotes for dynamic pricing.

An agent may supply an Ed25519-signed quote from an allowlisted merchant to bind
the unit price of a SKU. The gateway verifies the merchant signature against an
authoritative public keyring before lattice evaluation.

The invariant:
A quote sets unit_price only. Title, existence, and category MUST come from the
gateway's PriceBook to prevent category laundering.
"""
import base64
import json
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from mandate.policy.crypto import sign_bytes, verify_bytes


class QuoteError(Exception):
    """Base exception for quote verification failures."""
    clause_id: str = "quote.error"
    observed: Any = None
    expected: Any = None

    def __init__(self, message: str, observed: Any = None, expected: Any = None) -> None:
        super().__init__(message)
        self.observed = observed
        self.expected = expected


class QuoteMalformed(QuoteError):
    clause_id = "quote.malformed"


class QuoteUnsigned(QuoteError):
    clause_id = "quote.unknown_merchant"


class QuoteSignatureInvalid(QuoteError):
    clause_id = "quote.signature"


class QuoteMerchantMismatch(QuoteError):
    clause_id = "quote.merchant_mismatch"


class QuoteSkuMismatch(QuoteError):
    clause_id = "quote.sku_mismatch"


class QuoteExpired(QuoteError):
    clause_id = "quote.expired"


class QuoteNotYetValid(QuoteError):
    clause_id = "quote.not_yet_valid"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _b64url_decode(s: str) -> bytes:
    pad = len(s) % 4
    if pad:
        s += "=" * (4 - pad)
    return base64.urlsafe_b64decode(s.encode())


class MerchantKeyring:
    """Public key ring for verified merchants.

    Carries public keys only. Exposes no private keys and no signing methods.
    """
    def __init__(self, keys_by_merchant: dict[str, list[str] | str] | None = None) -> None:
        self._keys: dict[str, list[str]] = {}
        if keys_by_merchant:
            for m, klist in keys_by_merchant.items():
                norm_m = m.strip().lower()
                if isinstance(klist, str):
                    self._keys[norm_m] = [klist.strip()]
                else:
                    self._keys[norm_m] = [k.strip() for k in klist if k.strip()]

    @classmethod
    def from_file(cls, path: Path | str | None) -> "MerchantKeyring":
        if path is None:
            return cls()
        p = Path(path)
        if not p.exists():
            return cls()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()
        # A file that parses but is not an object is a misconfiguration, not a
        # keyring. Returning an empty one refuses every quote, which is the safe
        # direction; falling off the end returned None and crashed the caller.
        return cls(data) if isinstance(data, dict) else cls()

    def get_keys(self, merchant: str) -> list[str]:
        return list(self._keys.get(merchant.strip().lower(), []))

    def has_merchant(self, merchant: str) -> bool:
        return bool(self._keys.get(merchant.strip().lower()))

    def add_key(self, merchant: str, public_key_hex: str) -> None:
        norm_m = merchant.strip().lower()
        keys = self._keys.setdefault(norm_m, [])
        if public_key_hex.strip() not in keys:
            keys.append(public_key_hex.strip())

    def to_dict(self) -> dict[str, list[str]]:
        return {k: list(v) for k, v in self._keys.items()}

    def save(self, path: Path | str) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self._keys, indent=2) + "\n", encoding="utf-8")


def mint_quote(
    merchant: str,
    sku: str,
    unit_price_paise: int,
    private_key_hex: str,
    currency: str = "INR",
    issued: datetime | None = None,
    expires: datetime | None = None,
    nonce: str | None = None,
) -> str:
    """Mint an Ed25519-signed merchant quote."""
    now_dt = issued or datetime.now(UTC)
    exp_dt = expires or (now_dt + timedelta(minutes=15))
    payload = {
        "merchant": merchant.strip().lower(),
        "sku": sku,
        "unit_price_paise": int(unit_price_paise),
        "currency": currency,
        "issued": now_dt.isoformat(),
        "expires": exp_dt.isoformat(),
        "nonce": nonce or f"qnt_{uuid.uuid4().hex[:12]}",
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    sig_hex = sign_bytes(payload_bytes, private_key_hex)
    return f"{_b64url_encode(payload_bytes)}.{sig_hex}"


def verify_quote(
    raw_quote: str,
    expected_merchant: str,
    expected_sku: str,
    keyring: MerchantKeyring,
    now: datetime,
    max_age: timedelta | None = None,
) -> int:
    """Verify an Ed25519 merchant-signed quote and return the unit price in paise.

    Verification order is strictly load-bearing:
    1. Parse envelope -> QuoteMalformed
    2. Look up payload["merchant"] in keyring -> QuoteUnsigned
    3. Verify Ed25519 signature -> QuoteSignatureInvalid
    4. Merchant match -> QuoteMerchantMismatch
    5. SKU match -> QuoteSkuMismatch
    6. Currency match -> QuoteMalformed
    7. Freshness check -> QuoteExpired / QuoteNotYetValid
    """
    parts = raw_quote.strip().split(".")
    if len(parts) != 2:
        raise QuoteMalformed("quote must be <payload_b64url>.<sig_hex>", observed=raw_quote)

    b64_payload, sig_hex = parts
    try:
        payload_bytes = _b64url_decode(b64_payload)
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        raise QuoteMalformed(f"malformed quote payload: {e}", observed=raw_quote) from e

    if not isinstance(payload, dict):
        raise QuoteMalformed("quote payload must be a JSON object", observed=payload)

    quote_merchant = str(payload.get("merchant", "")).strip().lower()
    if not quote_merchant or not keyring.has_merchant(quote_merchant):
        # Deliberately does not list the known merchants. This string reaches the
        # agent verbatim and is written into the audit record, so naming them would
        # let a hostile caller enumerate the keyring one refusal at a time.
        raise QuoteUnsigned(
            f"no key held for merchant {quote_merchant!r}",
            observed=quote_merchant,
            expected="a merchant in the gateway's keyring",
        )

    # 3. Signature verification
    keys = keyring.get_keys(quote_merchant)
    valid_sig = any(verify_bytes(payload_bytes, sig_hex, k) for k in keys)
    if not valid_sig:
        raise QuoteSignatureInvalid("merchant signature invalid", observed=sig_hex)

    # 4. Merchant mismatch
    expected_m = expected_merchant.strip().lower()
    if quote_merchant != expected_m:
        raise QuoteMerchantMismatch(
            f"quote merchant {quote_merchant!r} does not match proposal merchant {expected_m!r}",
            observed=quote_merchant,
            expected=expected_m,
        )

    # 5. SKU match
    quote_sku = str(payload.get("sku", ""))
    if quote_sku != expected_sku:
        raise QuoteSkuMismatch(
            f"quote sku {quote_sku!r} does not match line item sku {expected_sku!r}",
            observed=quote_sku,
            expected=expected_sku,
        )

    # 6. Currency
    currency = payload.get("currency")
    if currency != "INR":
        raise QuoteMalformed(
            f"unsupported currency {currency!r}; only INR supported",
            observed=currency,
            expected="INR",
        )

    # 7. Freshness
    try:
        issued = datetime.fromisoformat(payload["issued"])
        expires = datetime.fromisoformat(payload["expires"])
    except (KeyError, ValueError) as e:
        raise QuoteMalformed(f"invalid timestamps in quote: {e}") from e

    if issued.tzinfo is None:
        issued = issued.replace(tzinfo=UTC)
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)

    if now < issued:
        raise QuoteNotYetValid(
            "quote is not yet valid",
            observed=now.isoformat(),
            expected=f">={issued.isoformat()}",
        )

    if now >= expires:
        raise QuoteExpired(
            "quote has expired",
            observed=now.isoformat(),
            expected=f"<{expires.isoformat()}",
        )

    if max_age is not None and (now - issued) > max_age:
        raise QuoteExpired(
            "quote exceeds max age",
            observed=(now - issued).total_seconds(),
            expected=max_age.total_seconds(),
        )

    try:
        price = int(payload["unit_price_paise"])
    except (KeyError, ValueError, TypeError) as e:
        raise QuoteMalformed(f"invalid unit_price_paise in quote: {e}") from e

    if price < 0:
        raise QuoteMalformed("unit_price_paise cannot be negative", observed=price)

    return price
