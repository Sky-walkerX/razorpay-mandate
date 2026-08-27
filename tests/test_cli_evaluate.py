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
    assert (out / "results.jsonl").exists()
    scores = json.loads((out / "scores.json").read_text())
    assert set(scores) == {"baseline", "compromised", "enforce", "enforce_compromised"}
    assert (out / "README-results.md").exists()


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
        for p in out.glob("*/*/result.json")
    ]
    assert rows and len({r["run_id"] for r in rows}) == 1
    assert all(r["run_id"].startswith("run_") for r in rows)


