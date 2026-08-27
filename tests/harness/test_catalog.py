from mandate.harness.catalog import generate_catalog


def test_same_seed_gives_identical_catalog():
    a, b = generate_catalog(seed=7), generate_catalog(seed=7)
    assert a.model_dump() == b.model_dump()

def test_different_seed_gives_different_catalog():
    assert generate_catalog(seed=7).model_dump() != generate_catalog(seed=8).model_dump()

def test_catalog_contains_restricted_items():
    cats = {p.category for p in generate_catalog(seed=7).products}
    assert "alcohol" in cats and "grocery" in cats

def test_every_product_has_a_known_merchant():
    c = generate_catalog(seed=7)
    assert all(p.merchant in c.merchant_names for p in c.products)

def test_prices_are_paise_integers():
    assert all(isinstance(p.unit_price, int) for p in generate_catalog(seed=7).products)
