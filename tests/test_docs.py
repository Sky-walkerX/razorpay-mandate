import re
from pathlib import Path

from mandate.conformance.suite import ATTACKS

REPO_ROOT = Path(__file__).resolve().parent.parent

# Allowlisted measured latency numbers in web/src (benchmarked numbers only)
ALLOWED_WEB_LATENCY_NUMBERS = {"0.0075", "0.2", "0.38", "1.4"}

def test_no_unmeasured_latency_in_web():
    """Ensure web/src files only reference measured benchmarked latency numbers."""
    web_src = REPO_ROOT / "web" / "src"
    pattern = re.compile(r'(\d+(?:\.\d+)?)\s*ms\b', re.IGNORECASE)

    violations = []
    for filepath in web_src.rglob("*.tsx"):
        content = filepath.read_text(encoding="utf-8")
        for line_no, line in enumerate(content.splitlines(), start=1):
            # Skip motion duration/delay/transition props
            if "duration" in line or "delay" in line or "transition" in line:
                continue
            for match in pattern.finditer(line):
                val = match.group(1)
                if val not in ALLOWED_WEB_LATENCY_NUMBERS:
                    violations.append(f"{filepath.relative_to(REPO_ROOT)}:{line_no}: '{match.group(0)}'")

    assert not violations, "Found unmeasured latency numbers in web/src:\n" + "\n".join(violations)


def test_conformance_badge_matches_suite():
    """Assert README.md conformance badge matches the actual conformance suite attack count."""
    readme_path = REPO_ROOT / "README.md"
    readme_text = readme_path.read_text(encoding="utf-8")

    match = re.search(r'Conformance-(\d+)%2F(\d+)%20Blocked', readme_text)
    assert match, "Could not find Conformance badge in README.md"

    blocked_count = int(match.group(1))
    total_count = int(match.group(2))

    assert total_count == len(ATTACKS), f"README badge total {total_count} != suite attacks {len(ATTACKS)}"
    assert blocked_count == len(ATTACKS), f"README badge blocked {blocked_count} != suite attacks {len(ATTACKS)}"


def test_latency_badge_matches_architecture():
    """Assert README.md latency badge matches the measured latency in ARCHITECTURE.md."""
    readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    arch_text = (REPO_ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")

    match_readme = re.search(r'img.shields.io/badge/9--Clause%20Evaluation-([^-\s]+)-', readme_text)
    assert match_readme, "Could not find Latency badge in README.md"

    badge_latency = match_readme.group(1).replace("%3C", "<")
    assert "<0.01ms" in badge_latency or "0.01ms" in badge_latency

    assert "0.0075" in arch_text or "< 0.01ms" in arch_text, "ARCHITECTURE.md missing measured 0.0075ms / < 0.01ms benchmark"
