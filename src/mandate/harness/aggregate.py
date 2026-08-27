"""Rebuild a run's aggregate from the per-item results it actually wrote.

The per-item result.json files are the durable evidence. results.jsonl is derived
from them, so a partial re-run can no longer destroy the record of a full one.
"""
from pathlib import Path

from mandate.harness.runner import ItemResult


class MixedRuns(Exception):
    """The tree holds more than one run and no run_id was named to pick between them."""


def collect(root: Path) -> list[ItemResult]:
    return [
        ItemResult.model_validate_json(p.read_text())
        for p in sorted(Path(root).glob("*/*/result.json"))
    ]


def select_run(results: list[ItemResult], run_id: str | None = None) -> list[ItemResult]:
    if run_id is not None:
        return [r for r in results if r.run_id == run_id]
    seen = {r.run_id for r in results}
    if len(seen) > 1:
        raise MixedRuns(
            "results/ holds more than one run: "
            + ", ".join(sorted(s or "<unstamped>" for s in seen))
            + ". Pass --run-id to choose one."
        )
    return list(results)


def write_jsonl(results: list[ItemResult], path: Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("".join(r.model_dump_json() + "\n" for r in results))
