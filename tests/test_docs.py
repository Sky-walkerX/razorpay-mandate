import json
import re
from pathlib import Path


def test_readme_has_no_pending_placeholders():
    """Day 13 filled these in from a real run. If any survive, the README lies.

    Matched on a word boundary. A bare substring also fires on "overspending",
    which is prose, not a placeholder.
    """
    text = Path("README.md").read_text().lower()
    assert not re.search(r"\b(pending|tbd|todo|xx+)\b", text)


def test_architecture_covers_the_four_required_topics():
    t = Path("ARCHITECTURE.md").read_text().lower()
    for topic in ("request path", "pending", "resolution", "observe"):
        assert topic in t


def test_breakage_log_has_more_than_the_seed_entry():
    p = Path("docs/breakage.md") if Path("docs/breakage.md").exists() else Path("BREAKAGE.md")
    assert len(p.read_text().split("## Day")) > 2


def test_web_console_claims_no_synthetic_run():
    """The console carried "the four-arm sweep has not been run" long after it had.

    A stale disclaimer on a project whose whole claim is honest measurement is
    worse than no disclaimer. These strings were true once; if one comes back,
    either the evidence is gone or someone retyped a number.
    """
    stale = re.compile(r"synthetic run|has not run|has not been run|seeded synthetic")
    for f in Path("web/src").rglob("*.tsx"):
        text = f.read_text()
        # The comment in TestChip explains why the phrase was removed, and says so
        # in prose the interface never renders.
        body = "\n".join(
            ln for ln in text.splitlines() if not ln.lstrip().startswith(("*", "/*", "//"))
        )
        assert not stale.search(body.lower()), f"{f} still claims a synthetic run"


def test_web_data_modules_read_evidence_rather_than_literals():
    """Bounds are read from the signed policy. Retyping them is how the console
    came to claim a max quantity of 4 against a policy that says 5."""
    for name in ("policy.ts", "decisions.ts"):
        src = Path("web/src/data") / name
        assert "evidence.json" in src.read_text(), f"{name} no longer reads evidence.json"
    ev = json.loads(Path("web/src/data/evidence.json").read_text())
    assert ev["source"]["containment_run"] and ev["source"]["false_block_run"]
