import re
from pathlib import Path

from mandate.conformance.suite import ATTACKS

REPO_ROOT = Path(__file__).resolve().parent.parent

# Latency numbers web/src may carry. Only 0.0075 is a live claim: pure 9-clause
# evaluate_all, measured over 2,000 warm calls on 31 Aug. (The full propose() path
# is ~4.9ms median / ~10ms p95; the gap is audit persistence and the downstream
# call, not the policy check, and no tile claims otherwise.)
#
# 0.38 and 1.4 are permitted only because they survive inside a comment that names
# them as the retired unmeasured figures. 0.2 was on this list and is not any more:
# it is the marketing number the repo documents as never measured, and allowlisting
# it here would have let it back onto the page silently.
ALLOWED_WEB_LATENCY_NUMBERS = {"0.0075", "0.38", "1.4"}

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


def test_the_web_has_exactly_one_api_base_and_it_is_not_hostname_sniffing():
    """The judge console posted to the visitor's own laptop on the custom domain.

    Three components each decided where the API lived, and they had drifted into
    two different rules. `JudgeConsole.tsx` enumerated the hosts it knew —
    port 8000, port 8811, `*.run.app` — and sent every other host to
    `http://127.0.0.1:8000`. That is correct on Cloud Run's own URL and wrong the
    moment a custom domain is put in front of it, which is exactly what happened:
    the page rendered perfectly on mandate.namankhandelwal.dev while every /v1
    call went to localhost. Nothing failed loudly enough to notice.

    The rule now lives in `web/src/lib/api.ts` and keys off `import.meta.env.DEV`,
    which knows nothing about hostnames. This test keeps it that way.
    """
    web_src = REPO_ROOT / "web" / "src"
    api_module = web_src / "lib" / "api.ts"
    assert api_module.exists(), "web/src/lib/api.ts is the single source for API_BASE"

    offenders = []
    for path in web_src.rglob("*.ts*"):
        if path == api_module:
            continue
        text = path.read_text(encoding="utf-8")
        if "const API_BASE" in text:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: defines its own API_BASE")
        if "run.app" in text:
            offenders.append(f"{path.relative_to(REPO_ROOT)}: branches on a hostname")

    assert not offenders, "\n".join(offenders)


def test_no_tsx_spells_out_how_many_limits_the_policy_carries():
    """The web said "nine" in eight places while rendering ten cards.

    Both numbers are real and they mean different things. `PART_LABELS` carries
    the ten constraint kinds the gateway implements, and this mandate sets nine
    of them — `item.deny_recent` is `source: "unset"`. So a screen that renders
    a card per kind shows ten while the prose beside it says nine, and a visitor
    counting the cards concludes the copy is wrong.

    Neither number may be typed. Both are one `.filter` off `PARTS`, which is
    already derived from `evidence.json`, so a policy that switches
    `item.deny_recent` on moves the prose without anyone editing a component.
    This is the same rule as the bounds: nothing about the signed policy is
    retyped into a `.tsx`.
    """
    import re

    web_src = REPO_ROOT / "web" / "src"

    # `(?<![\w-])` keeps "forty-nine more" — a run's own arithmetic, not a claim
    # about the policy — out of the net.
    noun = re.compile(
        r"(?<![\w-])(nine|ten)\b[^.<>{}]{0,24}?\b(clause|part|limit|kind)s?\b",
        re.IGNORECASE,
    )
    bare = re.compile(r"(?<![\w-])\b(all|the)\s+(nine|ten)\b(?!\s*[-\w]*\s*(more|of))", re.IGNORECASE)

    offenders = []
    for path in sorted(web_src.rglob("*.tsx")):
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            hit = noun.search(line) or bare.search(line)
            if hit:
                rel = path.relative_to(REPO_ROOT)
                offenders.append(f"{rel}:{line_no}: {hit.group(0)!r}")

    assert not offenders, (
        "a component states how many limits the policy has instead of counting them.\n"
        "Use PARTS.length (kinds the gateway checks) and the count of parts whose\n"
        "source is not 'unset' (kinds this mandate sets):\n" + "\n".join(offenders)
    )


# Where rendering an identifier is the point rather than a leak: the ledger row
# and the decision feed exist to be reconciled against the signed document, and
# the clause reference table's whole subject is the vocabulary of the policy.
IDENTIFIERS_BELONG_HERE = {
    "components/v2/GapAndParts.tsx",
    "components/dashboard/DecisionFeed.tsx",
    "components/dashboard/LedgerChain.tsx",
}


def test_a_rendered_clause_id_goes_through_the_label_lookup():
    """`budget.per_transaction` is a log line, not a sentence.

    Every clause carries two names. The identifier belongs in the audit chain
    and the policy contract view; everywhere else a first-time visitor should
    read "Most per order". The API sends both, so a component that renders the
    id straight is one that never asked for the label -- which is how the
    sandbox and the storefront came to print identifiers while the console
    beside them printed names.

    The rule is the lookup, not the absence: a clause id passed into
    `clauseLabel` is exactly right. Holding one is fine too -- a table keyed by
    clause id is a table, and an attack preset carrying a payload has to carry
    it. Printing one raw is the regression.
    """
    web_src = REPO_ROOT / "web" / "src"
    # A JSX interpolation in a text position. Not `key={...}` or any other prop,
    # and not a `${...}` inside a template literal, both of which are preceded
    # by a character this excludes.
    rendered = re.compile(r"(?<![=$\w])\{[^{}]*\.clause_id\b[^{}]*\}")

    offenders = []
    for path in sorted(web_src.rglob("*.tsx")):
        if path.relative_to(web_src).as_posix() in IDENTIFIERS_BELONG_HERE:
            continue
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            hit = rendered.search(line)
            if hit and "clauseLabel" not in line:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{line_no}: {hit.group(0)!r}")

    assert not offenders, (
        "a visitor-facing component renders a clause identifier raw.\n"
        "Pass it through clauseLabel(id, served) from web/src/lib/plain.ts:\n"
        + "\n".join(offenders)
    )


def test_only_one_module_maps_clause_ids_to_labels():
    """The web-side label table lives in `lib/plain.ts` and nowhere else.

    Server-side the same map had drifted into four copies, one of which spelled
    the expiry clause `time_window` against the policy's `time.window`, so the
    web could not match that one row to a label. A second copy on the web is the
    same bug with a shorter fuse.
    """
    web_src = REPO_ROOT / "web" / "src"
    holders = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in sorted(web_src.rglob("*.ts*"))
        if "'Most per order'" in p.read_text(encoding="utf-8")
    ]
    assert holders == ["web/src/lib/plain.ts"], (
        "the clause label table is duplicated: " + ", ".join(holders)
    )
