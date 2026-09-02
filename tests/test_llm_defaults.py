"""Pin the default model.

`GEMINI_MODEL` is what every path runs on unless a caller names a model. The
sweeps pass --model explicitly, so they were unaffected when a 939-file commit
titled "docs: spec for the judge-testable hosted gateway" (0ca31a5) changed this
constant from 3.7 to 3.6. Everything that does not pass --model was affected, and
that is the judge-facing half: `mandate compile`, `/v1/compile` and `/v1/agent`.
The live console ran a different model from the one the README named, for three
days, and nothing compared them.

The GCP usage graph is what caught it, not the test suite. Hence this file.
"""
from pathlib import Path

from mandate.llm import GEMINI_MODEL
from mandate.policy.loader import load as load_policy

DOCUMENTED_MODEL = "gemini-3.7-flash"


def test_the_default_gemini_model_is_the_documented_one():
    assert GEMINI_MODEL == DOCUMENTED_MODEL


def test_the_signed_policy_records_the_model_that_compiled_it():
    """The policy was compiled at 9c94e82, when the default was already 3.7."""
    assert load_policy(Path("policies/policy.yaml")).compiler.model == DOCUMENTED_MODEL


def test_a_provider_with_no_model_named_takes_the_documented_default():
    """`compile_intent` and the two service endpoints all call `provider_for()`
    with no model, so this is the path a judge exercises on the live site."""
    import inspect

    from mandate.llm import VertexGeminiProvider

    sig = inspect.signature(VertexGeminiProvider.__init__)
    assert sig.parameters["model"].default == DOCUMENTED_MODEL


def test_the_harness_default_tracks_the_same_constant():
    """`mandate evaluate` with no --model carried its own copy of the literal, and
    it was still on 3.6 after llm.py was restored. The documented sweeps all pass
    --model, so it never showed up in a result row, but a second hand-typed copy of
    the same fact is how the first one drifted."""
    from mandate.harness.runner import DEFAULT_MODEL

    assert DEFAULT_MODEL == GEMINI_MODEL
