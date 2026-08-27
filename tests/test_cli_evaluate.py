import json

from typer.testing import CliRunner

from mandate.cli import _model_factory, app
from mandate.harness.corpus import build_corpus, save_corpus
from mandate.policy.loader import dump
from tests.gateway.test_core import _pol

runner = CliRunner()


def test_evaluate_writes_results_and_scores(tmp_path, monkeypatch):
    corpus_p, policy_p, out = tmp_path / "c.json", tmp_path / "p.yaml", tmp_path / "out"
    save_corpus(build_corpus(seed=5, per_family=1, n_legit=2), corpus_p)
    dump(_pol(), policy_p)
    monkeypatch.setenv("MANDATE_FAKE_MODEL", "1")  # avoid live model calls in tests
    res = runner.invoke(
        app,
        [
            "evaluate",
            "--corpus",
            str(corpus_p),
            "--policy",
            str(policy_p),
            "--out",
            str(out),
            "--seed",
            "5",
            "--allow-scripted",
        ],
    )
    assert res.exit_code == 0
    assert (tmp_path / "out-scripted" / "results.jsonl").exists()


def test_evaluate_refuses_fake_model_without_allow_scripted(tmp_path, monkeypatch):
    corpus_p, policy_p, out = tmp_path / "c.json", tmp_path / "p.yaml", tmp_path / "out"
    save_corpus(build_corpus(seed=5, per_family=1, n_legit=2), corpus_p)
    dump(_pol(), policy_p)
    monkeypatch.setenv("MANDATE_FAKE_MODEL", "1")
    res = runner.invoke(
        app,
        [
            "evaluate",
            "--corpus",
            str(corpus_p),
            "--policy",
            str(policy_p),
            "--out",
            str(out),
            "--seed",
            "5",
        ],
    )
    assert res.exit_code != 0


def test_scripted_factory_reads_the_catalog_it_is_given(monkeypatch):
    """The old scripted stub hardcoded one sku and ignored the attack entirely."""
    monkeypatch.setenv("MANDATE_FAKE_MODEL", "1")
    from mandate.harness.catalog import generate_catalog

    cat = generate_catalog(seed=3)
    model = _model_factory(1)(cat, "buy groceries", False, None)
    name, args = model.next_call(None)
    assert name == "create_order"
    skus = {i["sku"] for i in args["items"]}
    assert skus <= {p.sku for p in cat.products}
    assert args["merchant"] in cat.merchant_names


def test_scripted_results_are_tagged_as_scripted(monkeypatch):
    monkeypatch.setenv("MANDATE_FAKE_MODEL", "1")
    model = _model_factory(1)(
        __import__("mandate.harness.catalog", fromlist=["generate_catalog"]).generate_catalog(
            seed=3
        ),
        "buy",
        False,
        None,
    )
    assert getattr(model, "model", None) == "scripted"


def test_evaluate_fails_fast_when_the_model_is_unreachable(tmp_path, monkeypatch):
    corpus_p, policy_p, out = tmp_path / "c.json", tmp_path / "p.yaml", tmp_path / "out"
    save_corpus(build_corpus(seed=5, per_family=1, n_legit=1), corpus_p)
    dump(_pol(), policy_p)
    monkeypatch.delenv("MANDATE_FAKE_MODEL", raising=False)

    def _boom(*a, **k):
        raise RuntimeError("403 Forbidden")

    monkeypatch.setattr("mandate.cli.preflight_model", _boom)
    res = runner.invoke(
        app,
        [
            "evaluate",
            "--corpus",
            str(corpus_p),
            "--policy",
            str(policy_p),
            "--out",
            str(out),
            "--seed",
            "5",
            "--model",
            "qwen3.7-flash",
        ],
    )
    assert res.exit_code != 0
    assert not (out / "results.jsonl").exists()


def test_evaluate_stamps_one_run_id_on_every_row(tmp_path, monkeypatch):
    corpus_p, policy_p, out = tmp_path / "c.json", tmp_path / "p.yaml", tmp_path / "out"
    save_corpus(build_corpus(seed=5, per_family=1, n_legit=1), corpus_p)
    dump(_pol(), policy_p)
    monkeypatch.setenv("MANDATE_FAKE_MODEL", "1")
    res = runner.invoke(
        app,
        [
            "evaluate",
            "--corpus",
            str(corpus_p),
            "--policy",
            str(policy_p),
            "--out",
            str(out),
            "--seed",
            "5",
            "--allow-scripted",
        ],
    )
    assert res.exit_code == 0, res.output
    rows = [
        json.loads(p.read_text())
        for p in (tmp_path / "out-scripted").glob("*/*/result.json")
    ]
    assert rows and len({r["run_id"] for r in rows}) == 1
    assert all(r["run_id"].startswith("run_") for r in rows)


def test_scripted_run_never_writes_into_the_real_results_dir(tmp_path, monkeypatch):
    corpus_p, policy_p, out = tmp_path / "c.json", tmp_path / "p.yaml", tmp_path / "out"
    save_corpus(build_corpus(seed=5, per_family=1, n_legit=2), corpus_p)
    dump(_pol(), policy_p)
    monkeypatch.setenv("MANDATE_FAKE_MODEL", "1")
    res = runner.invoke(
        app,
        [
            "evaluate",
            "--corpus",
            str(corpus_p),
            "--policy",
            str(policy_p),
            "--out",
            str(out),
            "--seed",
            "5",
            "--allow-scripted",
        ],
    )
    assert res.exit_code == 0
    assert not out.exists()
    assert (tmp_path / "out-scripted").exists()


def test_aggregate_rebuilds_reports_from_per_item_results(tmp_path):
    from mandate.harness.runner import ItemResult
    from mandate.money import Paise

    out = tmp_path / "results"
    for i, (arm, contained) in enumerate(
        [("baseline", False), ("baseline", False), ("enforce", True), ("enforce", True)]
    ):
        r = ItemResult(
            item_id=f"f#{i:03d}",
            family_id="f",
            arm=arm,
            is_attack=True,
            held_out=False,
            contained=contained,
            spent=Paise(0),
            executed_amount=Paise(0),
            model="qwen-flash",
            run_id="run_a",
        )
        d = out / arm / f"f_{i:03d}"
        d.mkdir(parents=True, exist_ok=True)
        (d / "result.json").write_text(r.model_dump_json(indent=2))

    res = runner.invoke(app, ["aggregate", "--out", str(out), "--run-id", "run_a"])
    assert res.exit_code == 0, res.output
    scores = json.loads((out / "scores.json").read_text())
    assert scores["baseline"]["containment"] == 0.0
    assert scores["enforce"]["containment"] == 1.0
    assert (out / "README-results.md").exists()
    assert len((out / "results.jsonl").read_text().strip().splitlines()) == 4




