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
    assert len(Path("BREAKAGE.md").read_text().split("## Day")) > 2
