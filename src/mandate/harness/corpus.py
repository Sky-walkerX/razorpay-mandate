"""Corpus assembly and freeze.

HELD_OUT families are never run during development. They are run once, on Day 13,
and reported separately. The gap between tuned and held-out containment is the finding.
"""
import hashlib
import json
import random
from pathlib import Path

from pydantic import BaseModel

from mandate.harness.catalog import generate_catalog
from mandate.harness.families import DEFAULT_INTENT, FAMILIES, MUTATORS, Mutation

# One from each mechanism: prompt trust, arithmetic, accumulation.
HELD_OUT = frozenset({"injection.review", "price.unit_confusion", "budget.salami"})


class CorpusFrozen(Exception):
    """The corpus file was edited after it was written."""


class CorpusItem(BaseModel):
    id: str
    family_id: str
    is_attack: bool
    held_out: bool
    mutation: Mutation


def build_corpus(seed: int, per_family: int = 12, n_legit: int = 60) -> list[CorpusItem]:
    items: list[CorpusItem] = []
    for fid in sorted(FAMILIES):
        for k in range(per_family):
            rng = random.Random(f"{seed}:{fid}:{k}")
            cat = generate_catalog(seed=seed + k)
            items.append(CorpusItem(
                id=f"{fid}#{k:03d}", family_id=fid, is_attack=True,
                held_out=fid in HELD_OUT, mutation=MUTATORS[fid](cat, rng)))
    for k in range(n_legit):
        rng = random.Random(f"{seed}:legit:{k}")
        cat = generate_catalog(seed=seed + 1000 + k)
        items.append(CorpusItem(
            id=f"legit#{k:03d}", family_id="legit", is_attack=False, held_out=False,
            mutation=Mutation(family_id="legit", item_seed=rng.randint(0, 2**31),
                              catalog=cat, clean_catalog=cat, intent=DEFAULT_INTENT,
                              expected_contained=True, note="clean catalog, ordinary intent")))
    return items


def corpus_hash(items: list[CorpusItem]) -> str:
    blob = json.dumps([i.model_dump(mode="json") for i in items], sort_keys=True)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


def save_corpus(items: list[CorpusItem], path: Path) -> None:
    raw_items = [i.model_dump(mode="json") for i in items]
    h = "sha256:" + hashlib.sha256(json.dumps(raw_items, sort_keys=True).encode()).hexdigest()
    path.write_text(json.dumps(
        {"corpus_hash": h,
         "items": raw_items}, indent=2, sort_keys=True))


def load_corpus(path: Path) -> list[CorpusItem]:
    body = json.loads(path.read_text())
    raw_hash = "sha256:" + hashlib.sha256(json.dumps(body["items"], sort_keys=True).encode()).hexdigest()
    if raw_hash != body["corpus_hash"]:
        raise CorpusFrozen("corpus file was edited after it was written")
    return [CorpusItem.model_validate(i) for i in body["items"]]
