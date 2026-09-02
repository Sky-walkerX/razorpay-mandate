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


def test_docker_image_ships_no_signing_key():
    """The gateway holds the issuer public key only, and the image must match.

    `COPY .mandate/ ./.mandate/` shipped issuer_private.key to Cloud Run, so the
    deployed container could mint itself a higher cap. That is the one property
    the offline issuer exists to provide, and nothing failed when it was broken.
    Keys are named file by file now; this asserts nobody re-widens the copy.
    """
    dockerfile = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8")

    copied = [
        line.split()[1]
        for line in dockerfile.splitlines()
        if line.startswith("COPY ") and "--from=" not in line
    ]

    # A directory copy of .mandate/ or of a keys dir sweeps the private key in.
    wildcards = [src for src in copied if src.rstrip("/").endswith((".mandate", "keys"))]
    assert not wildcards, (
        f"Dockerfile copies key directories wholesale: {wildcards}. "
        "Name each key file instead, so a new private key is not shipped by default."
    )

    assert not [src for src in copied if "private" in src], (
        "Dockerfile copies a private key into the image"
    )


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


def test_no_tsx_claims_a_rail_holds_a_clause_it_does_not():
    """`GapAndParts.tsx` hand-types `onRail` on each of its twelve conditions, and
    that is a compliance claim about UPI Reserve Pay sitting in a component where
    nothing compares it to `rails.py`.

    The assertion is one-directional on purpose. A condition marked `onRail: false`
    is finer-grained than its clause — "nothing from a merchant I have never used"
    compiles to merchant.allow, which Reserve Pay does carry, but not that reading
    of it — so a false there is a legitimate narrowing. Claiming a rail holds
    something it cannot is never legitimate, and that is the direction tested.
    """
    import re

    from mandate.harness.evidence import PART_LABELS
    from mandate.policy.rails import HELD, RESERVE_PAY_CARRIES

    src = (REPO_ROOT / "web/src/components/v2/GapAndParts.tsx").read_text(encoding="utf-8")
    conditions = re.findall(r"part:\s*(\d+),\s*onRail:\s*(true|false)", src)
    assert conditions, "GapAndParts.tsx no longer declares CONDITIONS as expected"

    key_of = {i: m["key"] for i, m in enumerate(PART_LABELS, start=1)}
    overclaimed = []
    for part, on_rail in conditions:
        if on_rail != "true":
            continue
        key = key_of[int(part)]
        kind, _ = RESERVE_PAY_CARRIES.get(key, ("none", ""))
        if kind not in HELD:
            overclaimed.append(f"part {part} ({key}) claims onRail, rails.py says {kind!r}")

    assert not overclaimed, "web claims a rail carries a clause it cannot:\n" + "\n".join(overclaimed)
