from datetime import UTC, datetime

from mandate.ap2.render import CONSTRAINT_AP2_MAPPING, render_ap2_mandate
from mandate.ap2.schema import AP2_VCT_CHECKOUT_OPEN
from mandate.policy.models import CompilerInfo, Policy, Provenance
from mandate.policy.models import ConstraintId as C


def test_every_constraint_is_mapped():
    """Assert each ConstraintId member appears in CONSTRAINT_AP2_MAPPING with a valid classification."""
    mapped_constraints = set(CONSTRAINT_AP2_MAPPING.keys())
    all_constraints = set(C)

    assert mapped_constraints == all_constraints, f"Missing constraint mappings: {all_constraints - mapped_constraints}"

    for cid, (cls_type, ap2_field) in CONSTRAINT_AP2_MAPPING.items():
        assert cls_type in {"native", "partial", "extension"}, f"Invalid classification {cls_type} for {cid}"
        assert ap2_field, f"Empty AP2 field mapping for {cid}"


def test_render_ap2_mandate():
    """Assert render_ap2_mandate renders policy into valid AP2 v0.2 structure."""
    policy = Policy(
        mandate_id="mnd_test_ap2",
        principal="user@example.com",
        agent="agent_v1",
        issued=datetime(2026, 9, 1, 0, 0, tzinfo=UTC),
        expires=datetime(2026, 9, 2, 0, 0, tzinfo=UTC),
        constraints={
            C.BUDGET_TOTAL: {"max": 200000},
            C.MERCHANT_ALLOW: ["blinkit", "zepto"],
            C.CATEGORY_DENY: ["alcohol"],
        },
        provenance=Provenance(stated=[C.BUDGET_TOTAL, C.MERCHANT_ALLOW, C.CATEGORY_DENY], inferred=[]),
        source_text="AP2 test policy",
        compiler=CompilerInfo(model="offline", temperature=0.0, version="1.0"),
    )

    doc = render_ap2_mandate(policy)

    assert doc.vct == AP2_VCT_CHECKOUT_OPEN
    assert doc.mandate_id == "mnd_test_ap2"
    assert doc.checkout.allowed_merchants == ["blinkit", "zepto"]
    assert doc.extensions.budget_total_paise == 200000
    assert doc.extensions.category_deny == ["alcohol"]

