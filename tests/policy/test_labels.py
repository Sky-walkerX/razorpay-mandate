"""One label per clause, in one place.

The labels used to be retyped in four: `harness/evidence.py`, twice in
`service/server.py`, and once more as JudgeConsole's offline fallback. Three of
those were subsets of the first, and one had already drifted -- server.py filed
the expiry clause under `time_window` while the policy, the audit log and the
evidence payload all call it `time.window`. Nothing compared them, so the web
would have shown a raw identifier for that one clause and a label for the other
nine, which is exactly the class of bug this module exists to make impossible.
"""
import re
from pathlib import Path

import pytest

from mandate.policy.labels import LABELS, PART_LABELS, label_for
from mandate.policy.models import ConstraintId

SRC = Path(__file__).resolve().parents[2] / "src" / "mandate"

# Everything `Decision.clause_id` can carry. The ten constraints, plus the seven
# refusals the gateway raises before or after the constraint evaluator runs.
NON_CONSTRAINT_CLAUSES = [
    "authentication",
    "pricebook",
    "idempotency",
    "downstream",
    "rail.divergence",
    "capture.binding",
    "capture.replay",
]


def test_every_constraint_the_policy_defines_has_a_label():
    for cid in ConstraintId:
        assert label_for(str(cid)) != str(cid), f"{cid} falls back to its own identifier"


def test_every_clause_a_refusal_can_name_has_a_label():
    """A visitor sees `clause_id`, not just the ten constraints.

    `authentication`, `pricebook` and the two capture clauses reach the same
    refusal banner the budget clauses do. A label map covering only the policy
    would leave those reading as identifiers on the one path where something has
    already gone wrong.
    """
    for cid in NON_CONSTRAINT_CLAUSES:
        assert label_for(cid) != cid, f"{cid} falls back to its own identifier"


def test_part_labels_covers_every_constraint_exactly_once():
    assert sorted(p["key"] for p in PART_LABELS) == sorted(str(c) for c in ConstraintId)


def test_the_reading_order_is_frozen():
    """A clause's position in this list is its Part number.

    "Stopped by Part 4" on the failure cards means velocity because velocity is
    fourth. The same numbers are baked into `evidence.json`, cited in every
    refusal and spoken in the pitch video, so reordering the list silently
    renumbers all of them. Pinned here so it has to be a deliberate edit.
    """
    assert [p["key"] for p in PART_LABELS] == [
        "budget.total",
        "budget.per_transaction",
        "budget.per_item",
        "velocity",
        "quantity.max_per_item",
        "merchant.allow",
        "category.deny",
        "time.window",
        "item.deny_recent",
        "afa.required",
    ]


def test_an_unknown_clause_returns_itself_rather_than_inventing_a_name():
    """Fails visibly. A made-up label for a clause nobody registered would read
    as though the gateway had a rule it does not have."""
    assert label_for("nonsense.clause") == "nonsense.clause"


def test_no_label_is_itself_an_identifier():
    for key, label in LABELS.items():
        assert not re.fullmatch(r"[a-z_]+(\.[a-z_]+)*", label), f"{key} labelled {label!r}"


@pytest.mark.parametrize("module", ["harness/evidence.py", "service/server.py"])
def test_no_module_retypes_a_label(module):
    """The drift guard. Both modules import the map; neither may hand-type a
    label literal beside a clause id again."""
    text = (SRC / module).read_text()
    for label in LABELS.values():
        assert f'"{label}"' not in text, f"{module} retypes the label {label!r}"
