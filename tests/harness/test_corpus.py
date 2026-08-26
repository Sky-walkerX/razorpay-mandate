import pytest
from pathlib import Path
from mandate.harness.corpus import (build_corpus, corpus_hash, save_corpus, load_corpus,
                                    HELD_OUT, CorpusFrozen)

def test_held_out_has_three_families_spanning_different_mechanisms():
    assert len(HELD_OUT) == 3
    assert HELD_OUT == {"injection.review", "price.unit_confusion", "budget.salami"}

def test_corpus_is_seed_reproducible():
    assert corpus_hash(build_corpus(seed=5)) == corpus_hash(build_corpus(seed=5))

def test_corpus_contains_attacks_and_legitimate_items():
    items = build_corpus(seed=5)
    assert any(i.is_attack for i in items)
    assert any(not i.is_attack for i in items)

def test_legitimate_items_are_never_held_out():
    assert all(not i.held_out for i in build_corpus(seed=5) if not i.is_attack)

def test_held_out_flag_matches_the_family_set():
    for i in build_corpus(seed=5):
        if i.is_attack:
            assert i.held_out == (i.family_id in HELD_OUT)

def test_every_family_is_represented():
    from mandate.harness.families import FAMILIES
    fams = {i.family_id for i in build_corpus(seed=5) if i.is_attack}
    assert fams == set(FAMILIES)

def test_saved_corpus_is_frozen_against_edits(tmp_path: Path):
    f = tmp_path / "corpus.json"
    save_corpus(build_corpus(seed=5), f)
    f.write_text(f.read_text().replace('"repeat": 1', '"repeat": 2', 1))
    with pytest.raises(CorpusFrozen):
        load_corpus(f)
