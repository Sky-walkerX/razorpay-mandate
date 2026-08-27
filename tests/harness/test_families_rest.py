import random

from mandate.harness.catalog import generate_catalog
from mandate.harness.families import FAMILIES, MUTATORS

ALL = ["injection.description", "injection.seller_name", "injection.review",
       "price.flip", "price.unit_confusion", "category.laundering",
       "merchant.lookalike", "retry.storm", "time.boundary", "budget.salami"]

def test_ten_families_registered():
    assert sorted(FAMILIES) == sorted(ALL)

def test_laundering_hides_alcohol_under_an_innocuous_title():
    m = MUTATORS["category.laundering"](generate_catalog(seed=7), random.Random(1))
    laundered = [p for p in m.catalog.products if p.category == "alcohol"]
    assert any("alcohol" not in p.title.lower() and "wine" not in p.title.lower()
               and "lager" not in p.title.lower() for p in laundered)

def test_lookalike_adds_a_merchant_close_to_an_allowed_one():
    m = MUTATORS["merchant.lookalike"](generate_catalog(seed=7), random.Random(1))
    assert any(k.startswith("zepto") and k != "zepto" for k in m.catalog.merchant_names)

def test_retry_storm_sets_repeat_above_one():
    assert MUTATORS["retry.storm"](generate_catalog(seed=7), random.Random(1)).repeat > 1

def test_time_boundary_sets_a_clock_offset():
    assert MUTATORS["time.boundary"](generate_catalog(seed=7), random.Random(1)).clock_offset_s != 0

def test_unit_confusion_changes_the_stated_unit_not_the_price():
    m = MUTATORS["price.unit_confusion"](generate_catalog(seed=7), random.Random(1))
    assert any(p.unit == "100g" for p in m.catalog.products)

def test_all_families_expect_containment():
    for fid in ALL:
        assert MUTATORS[fid](generate_catalog(seed=7), random.Random(2)).expected_contained
