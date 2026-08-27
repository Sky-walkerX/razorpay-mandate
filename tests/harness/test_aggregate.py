import pytest

from mandate.harness.aggregate import MixedRuns, collect, select_run, write_jsonl
from mandate.harness.runner import ItemResult
from mandate.money import Paise


def _res(**over) -> ItemResult:
    body = {
        "item_id": "x#000",
        "family_id": "x",
        "arm": "enforce",
        "is_attack": True,
        "held_out": False,
        "contained": True,
        "spent": Paise(0),
        "executed_amount": Paise(0),
        "model": "qwen-flash",
        "run_id": "run_a",
    }
    body.update(over)
    return ItemResult(**body)


def _write(root, res):
    d = root / res.arm / res.item_id.replace("#", "_")
    d.mkdir(parents=True, exist_ok=True)
    (d / "result.json").write_text(res.model_dump_json(indent=2))


def test_collect_reads_every_per_item_result(tmp_path):
    _write(tmp_path, _res(item_id="a#000", arm="baseline"))
    _write(tmp_path, _res(item_id="a#001", arm="enforce"))
    assert {r.item_id for r in collect(tmp_path)} == {"a#000", "a#001"}


def test_select_run_keeps_only_the_named_run(tmp_path):
    rows = [_res(item_id="a#000", run_id="run_a"), _res(item_id="a#001", run_id="run_b")]
    assert [r.item_id for r in select_run(rows, "run_b")] == ["a#001"]


def test_select_run_refuses_to_guess_when_runs_are_mixed(tmp_path):
    rows = [_res(item_id="a#000", run_id="run_a"), _res(item_id="a#001", run_id="run_b")]
    with pytest.raises(MixedRuns):
        select_run(rows)


def test_write_jsonl_round_trips(tmp_path):
    rows = [_res(item_id="a#000"), _res(item_id="a#001")]
    p = tmp_path / "results.jsonl"
    write_jsonl(rows, p)
    assert len(p.read_text().strip().splitlines()) == 2
