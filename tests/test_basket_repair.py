"""The line that links a refusal to what the agent did next.

Pure logic, so it is tested rather than eyeballed in a browser. Node runs the
TypeScript directly, the same way the Merkle parity test does.

The wording matters as much as the diff. The gateway names the limit that stopped
the order; what the agent does about it is the model's choice. A row implying the
gateway steered the repair would be the wrong story about the wrong component.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

CASES = [
    # (before, after, expected)
    (
        {"items": [{"sku": "a", "qty": 2, "title": "Olive Oil"}]},
        {"items": []},
        "dropped Olive Oil",
    ),
    (
        {"items": [{"sku": "a", "qty": 5, "title": "Olive Oil"}]},
        {"items": [{"sku": "a", "qty": 2, "title": "Olive Oil"}]},
        "cut Olive Oil from 5 to 2",
    ),
    (
        {"items": [{"sku": "a", "qty": 1, "title": "Olive Oil"}]},
        {"items": [{"sku": "a", "qty": 1, "title": "Olive Oil"},
                   {"sku": "b", "qty": 3, "title": "Toor Dal"}]},
        "added 3 × Toor Dal",
    ),
    # A SKU the price book does not carry has no title, and the row still reads.
    (
        {"items": [{"sku": "sku_0009", "qty": 1}]},
        {"items": []},
        "dropped sku_0009",
    ),
    # Two changes join with "and", three with commas.
    (
        {"items": [{"sku": "a", "qty": 2, "title": "Oil"}, {"sku": "b", "qty": 4, "title": "Dal"}]},
        {"items": [{"sku": "b", "qty": 1, "title": "Dal"}]},
        "dropped Oil and cut Dal from 4 to 1",
    ),
    (
        {"merchant": "zepto", "items": [{"sku": "a", "qty": 1, "title": "Oil"}]},
        {"merchant": "blinkit", "items": [{"sku": "a", "qty": 1, "title": "Oil"}]},
        "moved to blinkit",
    ),
    # An unchanged retry is a real thing an agent does. Saying "changed nothing"
    # would read as a repair that failed rather than as a repeat.
    (
        {"items": [{"sku": "a", "qty": 1, "title": "Oil"}]},
        {"items": [{"sku": "a", "qty": 1, "title": "Oil"}]},
        None,
    ),
    # A step with no basket at all yields nothing rather than a half-sentence.
    ({"items": [{"sku": "a", "qty": 1}]}, {}, None),
    # More than three changes is more than a row carries legibly.
    (
        {"items": [{"sku": c, "qty": 1, "title": c.upper()} for c in "abcde"]},
        {"items": []},
        "dropped A, dropped B and dropped C, and 2 more changes",
    ),
]

SCRIPT = """
import { describeRepair } from './basket.ts';
let raw = '';
process.stdin.on('data', (c) => { raw += c; });
process.stdin.on('end', () => {
  const cases = JSON.parse(raw);
  console.log(JSON.stringify(cases.map(([b, a]) => describeRepair(b, a))));
});
"""


def test_the_repair_line_names_what_actually_changed():
    if shutil.which("node") is None:
        pytest.skip("node is not installed; the TypeScript helper cannot be checked")

    scratch = REPO / "web" / "src" / "lib" / "__basket_check.mts"
    scratch.write_text(SCRIPT, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["node", str(scratch)],
            input=json.dumps([[b, a] for b, a, _ in CASES]),
            capture_output=True, text=True, timeout=60, check=False,
        )
    finally:
        scratch.unlink(missing_ok=True)
    if proc.returncode != 0:
        pytest.fail(f"node failed:\n{proc.stderr}")

    got = json.loads(proc.stdout.strip())
    for (before, _after, want), actual in zip(CASES, got, strict=True):
        assert actual == want, f"for {before}: wanted {want!r}, got {actual!r}"
