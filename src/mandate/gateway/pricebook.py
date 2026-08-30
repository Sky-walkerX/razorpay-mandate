"""PriceBook interface for gateway ground-truth SKU resolution.

The gateway dereferences reality from its own authoritative price book.
The agent sends references ({sku, qty}); the price book resolves facts.
"""
from dataclasses import dataclass
from typing import Protocol

from mandate.money import Paise


@dataclass(frozen=True)
class PriceBookItem:
    sku: str
    title: str
    unit_price: Paise
    category: str
    merchant: str


class PriceBook(Protocol):
    def lookup(self, sku: str) -> PriceBookItem:
        ...

    def has_sku(self, sku: str) -> bool:
        ...


class DictPriceBook:
    """In-memory PriceBook backed by a dictionary or Catalog."""

    def __init__(self, items: dict[str, PriceBookItem] | None = None) -> None:
        self._items = dict(items or {})

    @classmethod
    def from_catalog(cls, catalog) -> "DictPriceBook":
        mapping = {}
        for p in catalog.products:
            mapping[p.sku] = PriceBookItem(
                sku=p.sku,
                title=p.title,
                unit_price=Paise(int(p.unit_price)),
                category=p.category,
                merchant=p.merchant,
            )
        return cls(mapping)

    def lookup(self, sku: str) -> PriceBookItem:
        if sku not in self._items:
            raise KeyError(f"SKU {sku!r} not found in price book")
        return self._items[sku]

    def has_sku(self, sku: str) -> bool:
        return sku in self._items
