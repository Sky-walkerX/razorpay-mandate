import random
from mandate.harness.catalog import generate_catalog
from mandate.harness.families import MUTATORS, FAMILIES

def test_three_injection_families_are_registered():
    for fid in ("injection.description", "injection.seller_name", "injection.review"):
        assert fid in MUTATORS and fid in FAMILIES

def test_description_injection_puts_instruction_text_in_a_description():
    m = MUTATORS["injection.description"](generate_catalog(seed=7), random.Random(1))
    assert any("SYSTEM" in p.description for p in m.catalog.products)

def test_seller_name_injection_leaves_descriptions_clean():
    m = MUTATORS["injection.seller_name"](generate_catalog(seed=7), random.Random(1))
    assert any("SYSTEM" in p.seller for p in m.catalog.products)
    assert not any("SYSTEM" in p.description for p in m.catalog.products)

def test_mutations_are_seed_reproducible():
    a = MUTATORS["injection.review"](generate_catalog(seed=7), random.Random(3))
    b = MUTATORS["injection.review"](generate_catalog(seed=7), random.Random(3))
    assert a.model_dump() == b.model_dump()

def test_injection_mutations_expect_containment():
    """An injection that succeeds is a containment failure. Expected value is always True."""
    for fid in ("injection.description", "injection.seller_name", "injection.review"):
        assert MUTATORS[fid](generate_catalog(seed=7), random.Random(1)).expected_contained
