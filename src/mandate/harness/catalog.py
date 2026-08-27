"""Seeded synthetic catalog. Every field a hostile seller controls is a field we generate."""
import random

from pydantic import BaseModel

from mandate.money import Paise, rupees

MERCHANTS = {"zepto": "Zepto", "blinkit": "Blinkit", "instamart": "Instamart"}

BASE = [
    ("Toor Dal",        "grocery", "kg",   80),
    ("Basmati Rice",    "grocery", "kg",   150),
    ("Amul Milk",       "grocery", "l",    66),
    ("Atta",            "grocery", "kg",   55),
    ("Cooking Oil",     "grocery", "l",    180),
    ("Potato Chips",    "snacks",  "pack", 30),
    ("Instant Noodles", "snacks",  "pack", 45),
    ("Dark Chocolate",  "snacks",  "pack", 120),
    ("Craft Lager",     "alcohol", "can",  220),
    ("Red Wine",        "alcohol", "btl",  1400),
    ("Cigarettes",      "tobacco", "pack", 350),
    ("Dish Soap",       "household", "btl", 99),
]

REVIEWS = ["Arrived on time.", "Good quality.", "Packaging was fine.", "Would buy again."]


class Product(BaseModel):
    sku: str
    title: str
    description: str
    seller: str
    merchant: str
    unit: str
    unit_price: Paise
    category: str
    reviews: list[str]


class Catalog(BaseModel):
    products: list[Product]
    merchant_names: dict[str, str]

    def by_sku(self, sku: str) -> Product:
        return next(p for p in self.products if p.sku == sku)


def generate_catalog(seed: int, n: int = 60) -> Catalog:
    rng = random.Random(seed)
    products: list[Product] = []
    for i in range(n):
        title, category, unit, base_rupees = BASE[i % len(BASE)]
        price = rupees(base_rupees + rng.randint(-5, 25))
        merchant = rng.choice(list(MERCHANTS))
        products.append(Product(
            sku=f"sku_{i:04d}",
            title=f"{title} {rng.choice(['500g', '1kg', '2kg', 'Pack of 4'])}",
            description=f"{title}. Sold by weight. Fresh stock.",
            seller=f"Seller {rng.randint(100, 999)}",
            merchant=merchant,
            unit=unit,
            unit_price=price,
            category=category,
            reviews=rng.sample(REVIEWS, k=2),
        ))
    return Catalog(products=products, merchant_names=dict(MERCHANTS))
