import random

from mandate.harness.catalog import generate_catalog
from mandate.harness.corpus import build_corpus
from mandate.harness.families import FAMILIES, MUTATORS


def test_every_family_sets_the_clean_catalog():
    clean = generate_catalog(seed=7)
    for fid in sorted(FAMILIES):
        mut = MUTATORS[fid](clean, random.Random(f"t:{fid}"))
        assert mut.clean_catalog is not None, fid
        assert mut.clean_catalog.merchant_names == clean.merchant_names, fid


def test_clean_catalog_is_not_the_mutated_one_for_laundering():
    clean = generate_catalog(seed=7)
    mut = MUTATORS["category.laundering"](clean, random.Random("t"))
    alcohol = [p for p in mut.clean_catalog.products if p.category == "alcohol"]
    assert alcohol, "clean catalog must still carry true alcohol categories"
    laundered = {p.sku for p in mut.catalog.products if p.title.endswith("Kit")}
    for sku in laundered:
        assert mut.clean_catalog.by_sku(sku).category == "alcohol"


def test_legit_items_carry_a_clean_catalog():
    items = build_corpus(seed=20260901, per_family=1, n_legit=2)
    for i in items:
        assert i.mutation.clean_catalog is not None, i.id
