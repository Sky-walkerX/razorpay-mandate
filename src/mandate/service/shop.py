"""The shop, which signs prices. Not the gateway, which verifies them.

`GET /v1/quote` is the *shop* speaking, served by the same process as the gateway
because a demo cannot run three daemons on a stage. They are separated by the key,
not by the process, and that separation is the only thing that makes the quote
attacks mean anything:

  - The gateway holds `MerchantKeyring`, which carries public keys only and exposes
    no signing method at all.
  - The shop holds the private half, loaded here and reachable from nowhere on the
    gateway's path.

`test_the_gateway_never_reads_a_merchant_private_key` pins the half that matters. It
is the same honesty as the `FakeDownstream` framing: the demo plays two roles and
says which one is speaking.

The surge factor is published in every answer rather than hidden in the price. A shop
that quietly marks up is a different demo from one that says "we are at 1.7x right
now", and only the second lets a visitor check the arithmetic against the list price
they can already see on `/store`.
"""
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from mandate.gateway.pricebook import PriceBook
from mandate.gateway.quote import mint_quote

#: How long a quote the shop hands out stays good for. The gateway applies its own
#: 15-minute ceiling on top of this, so a shop stamping a year out buys nothing.
QUOTE_TTL = timedelta(minutes=10)

#: The shop's markup right now. 1.0 is the list price, which makes the feature look
#: like it does nothing -- so the default surges, and the number is in the response.
DEFAULT_SURGE = 1.7


class ShopUnavailable(Exception):
    """The shop holds no signing key, so it cannot quote a price."""


class Shop:
    """A merchant that signs its own prices with its own key."""

    def __init__(
        self,
        private_keys: dict[str, str] | None = None,
        surge: float = DEFAULT_SURGE,
        ttl: timedelta = QUOTE_TTL,
    ) -> None:
        self._private_keys = {
            m.strip().lower(): k.strip()
            for m, k in (private_keys or {}).items()
            if k and k.strip()
        }
        self.surge = surge
        self.ttl = ttl

    @classmethod
    def from_environment(
        cls, key_path: Path | str | None = Path(".mandate/keys/shop_private.json")
    ) -> "Shop":
        """File first, then environment, matching the log signing key.

        Locally the key you just generated wins over a stale exported variable, and
        the deployment is unaffected because it has no file to prefer. The image
        cannot carry this file: `test_docker_image_ships_no_signing_key` rejects any
        COPY whose source contains "private", which is exactly the guard that should
        stop a merchant's signing key being baked into a container.
        """
        keys: dict[str, str] = {}
        if key_path and Path(key_path).exists():
            try:
                loaded = json.loads(Path(key_path).read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    keys = {str(m): str(k) for m, k in loaded.items()}
            except (json.JSONDecodeError, OSError):
                keys = {}
        if not keys and os.environ.get("MANDATE_SHOP_PRIVATE_KEYS", "").strip():
            try:
                loaded = json.loads(os.environ["MANDATE_SHOP_PRIVATE_KEYS"])
                if isinstance(loaded, dict):
                    keys = {str(m): str(k) for m, k in loaded.items()}
            except json.JSONDecodeError:
                keys = {}

        try:
            surge = float(os.environ.get("MANDATE_SHOP_SURGE", "").strip() or DEFAULT_SURGE)
        except ValueError:
            surge = DEFAULT_SURGE
        return cls(private_keys=keys, surge=surge)

    def can_quote(self, merchant: str) -> bool:
        return merchant.strip().lower() in self._private_keys

    @property
    def merchants(self) -> list[str]:
        return sorted(self._private_keys)

    def quote(
        self,
        merchant: str,
        sku: str,
        pricebook: PriceBook,
        now: datetime | None = None,
    ) -> dict:
        """Sign this shop's current price for one SKU it actually stocks.

        The caller names the item, never the price. A shop that signed whatever
        figure it was handed would be a signing oracle rather than a merchant, and
        the four quote attacks would be testing nothing -- an agent could mint its
        own Rs 1,900 quote through the front door instead of forging one.
        """
        norm = merchant.strip().lower()
        key = self._private_keys.get(norm)
        if key is None:
            raise ShopUnavailable(f"no signing key held for merchant {norm!r}")

        item = pricebook.lookup(sku)   # KeyError for a SKU this shop does not stock
        list_paise = int(item.unit_price)
        signed_paise = round(list_paise * self.surge)

        issued = now or datetime.now(UTC)
        raw = mint_quote(
            merchant=norm,
            sku=sku,
            unit_price_paise=signed_paise,
            private_key_hex=key,
            issued=issued,
            expires=issued + self.ttl,
        )
        return {
            "merchant": norm,
            "sku": sku,
            "title": item.title,
            "list_price_paise": list_paise,
            "unit_price_paise": signed_paise,
            "surge_factor": self.surge,
            "issued": issued.isoformat(),
            "expires": (issued + self.ttl).isoformat(),
            "quote": raw,
        }
