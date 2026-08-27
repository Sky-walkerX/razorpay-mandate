from pathlib import Path


def test_readme_has_no_pending_placeholders():
    """Day 13 filled these in from a real run. If any survive, the README lies."""
    assert "pending" not in Path("README.md").read_text().lower()


def test_architecture_covers_the_four_required_topics():
    t = Path("ARCHITECTURE.md").read_text().lower()
    for topic in ("request path", "pending", "resolution", "observe"):
        assert topic in t


def test_breakage_log_has_more_than_the_seed_entry():
    assert len(Path("BREAKAGE.md").read_text().split("## Day")) > 2
