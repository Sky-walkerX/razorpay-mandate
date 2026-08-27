import json

from typer.testing import CliRunner

from mandate.cli import app
from mandate.harness.corpus import build_corpus, save_corpus
from mandate.policy.loader import dump
from tests.gateway.test_core import _pol

runner = CliRunner()


def test_evaluate_writes_results_and_scores(tmp_path, monkeypatch):
    corpus_p, policy_p, out = tmp_path / "c.json", tmp_path / "p.yaml", tmp_path / "out"
    save_corpus(build_corpus(seed=5, per_family=1, n_legit=2), corpus_p)
    dump(_pol(), policy_p)
    monkeypatch.setenv("MANDATE_SCRIPTED", "1")  # avoid live model calls in tests
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
    assert res.exit_code == 0
    assert (out / "results.jsonl").exists()
    scores = json.loads((out / "scores.json").read_text())
    assert set(scores) == {"enforce", "baseline"}
    assert (out / "README-results.md").exists()
