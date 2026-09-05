"""Check a signed policy against the regulation, and name what it does not do.

This asks the opposite question from `rails.py`, and the two must not be merged.

    rails.py    clause -> rail.   "Can AP2 hold budget.per_item?"  It cannot.
    this file   requirement -> us. "RBI requires a pre-debit notice. Do we send one?"

Merging them would let one word, "held", mean two different things in two columns:
there, a rail carrying our clause; here, us carrying a regulator's obligation. The
second is the one a compliance reader cares about and the one it is tempting to
overstate, so it gets its own vocabulary:

    held         the requirement is met, by a named mechanism in this codebase
    partial      something related exists and does not go the whole way
    gap          the requirement applies to this component and is not met
    out_of_scope the obligation lands on the issuer or the bank, not on a gateway

`gap` and `out_of_scope` are different claims and the difference is the honest part.
A gap is work not done. Out of scope is work that was never ours: this project is a
policy gateway sitting between an agent and a PSP, not a card issuer, so it cannot
authenticate a cardholder or run a grievance desk. Filing our own gaps under
"out of scope" is the failure mode this file exists to avoid, so every out_of_scope
row has to say whose obligation it is instead.

Every requirement carries its source. Nothing here is remembered; see CITATIONS.
"""
from pydantic import BaseModel

from mandate.policy.models import ConstraintId as C
from mandate.policy.models import Policy

# Sourced 2 Sep 2026. The framework is real and recent, so the citation travels with
# the claim rather than living in a commit message.
CITATIONS: dict[str, dict[str, str]] = {
    "rbi_emandate_2026": {
        "title": "Reserve Bank of India, Digital Payments – E-mandate Framework, 2026",
        "issued": "21 April 2026",
        "note": "Consolidates the earlier circulars on recurring payments over cards, "
                "PPIs and UPI, domestic and cross-border.",
        "checked": "2 September 2026",
    },
    "npci_uap": {
        "title": "NPCI, Unified Agent Protocol",
        "issued": "announced, not published",
        "note": "Expected at the Global Fintech Fest, Mumbai, 9–11 September 2026.",
        "checked": "2 September 2026",
    },
    "upi_reserve_pay": {
        "title": "UPI Reserve Pay",
        "issued": "live",
        "note": "One-time consent blocking an amount against one merchant, revocable. "
                "Razorpay and NPCI announced agentic payments on it in February 2026.",
        "checked": "2 September 2026",
    },
}


class Requirement(BaseModel):
    """One obligation, and what this codebase does about it."""

    key: str
    source: str
    requirement: str
    status: str
    mechanism: str
    clause: str | None = None


STATUSES = ("held", "partial", "gap", "out_of_scope")

#: The AFA threshold in paise. RBI's e-mandate framework processes recurring
#: transactions up to Rs 15,000 without an additional factor and requires one above
#: it. The framework allows Rs 1 lakh for insurance premiums, mutual fund
#: subscriptions and card bills; a grocery mandate takes the Rs 15,000 floor.
AFA_THRESHOLD_PAISE = 1_500_000

#: What every mandate carries because a regulator requires it, whatever the person
#: dictating the intent said or did not say.
#:
#: This exists because the floor used to live in one hand-written `policies/policy.yaml`
#: and in nothing else. The compiler emits neither of these clauses -- it never hears
#: them, correctly, because a statutory obligation is not something a user states --
#: so every mandate compiled by `mandate compile`, `/v1/compile` or `/v1/sandbox` came
#: out without them. Measured on a live sandbox session before the fix: a visitor
#: mandate authorising Rs 50,000 an order executed Rs 18,600 straight to the rail with
#: the clause reading `constraint not in policy`.
#:
#: `time.window` is `{}` because the validity period lives on `Policy.expires`; the
#: clause is the marker that a period is required at all.
REGULATORY_FLOOR: dict[C, dict] = {
    C.AFA_REQUIRED: {"threshold": AFA_THRESHOLD_PAISE},
    C.TIME_WINDOW: {},
}

# The RBI framework's obligations, in the order a reader meets them: register, then
# transact, then get out. Statuses are deliberately conservative; two of these are
# gaps and they are the reason this table is worth publishing.
RBI_REQUIREMENTS: list[Requirement] = [
    Requirement(
        key="afa_at_registration",
        source="rbi_emandate_2026",
        requirement="Registration of an e-mandate is validated with Additional Factor "
                    "Authentication, over and above the issuer's normal checks.",
        status="out_of_scope",
        mechanism="An issuer authenticates the cardholder; this gateway never sees the "
                  "customer or their factors. What it does instead is refuse to be the "
                  "authority: a mandate is signed offline by the issuer CLI with an "
                  "Ed25519 key the running service does not hold, so a compromised "
                  "gateway cannot mint itself a higher cap.",
    ),
    Requirement(
        key="afa_above_threshold",
        source="rbi_emandate_2026",
        requirement="Recurring transactions up to ₹15,000 may be processed without "
                    "AFA. Above it, AFA is required per transaction.",
        status="held",
        clause=str(C.AFA_REQUIRED),
        mechanism="Above the threshold the gateway answers UNKNOWN rather than DENY — "
                  "the order is not forbidden, it is unauthorised so far — and "
                  "withholds execution until an approval appears in ApprovalStore keyed "
                  "on the canonical intent hash of the resolved action, so approving one "
                  "basket cannot release a different basket of the same value. The "
                  "framework allows ₹1 lakh for insurance premiums, mutual fund "
                  "subscriptions and card bills; a grocery mandate takes the ₹15,000 "
                  "reading, which is the stricter one.",
    ),
    Requirement(
        key="validity_period",
        source="rbi_emandate_2026",
        requirement="Every e-mandate specifies a validity period.",
        status="held",
        clause=str(C.TIME_WINDOW),
        mechanism="policy.expires is signed into the mandate and time.window is evaluated "
                  "against the gateway's own clock on every proposal. Its provenance is "
                  "recorded as regulatory, not stated: no user says it, the compiler does "
                  "not infer it, and it is not the user's to decline.",
    ),
    Requirement(
        key="withdraw_any_time",
        source="rbi_emandate_2026",
        requirement="The customer can modify the validity period or withdraw the "
                    "e-mandate at any time.",
        status="held",
        mechanism="`mandate revoke` writes a jti or a mandate_id to the revocation list, "
                  "and the gateway checks it before anything else on every propose() and "
                  "capture_payment(). Revocation is immediate and offline; it does not "
                  "wait for the token to expire. replay.token in the conformance suite is "
                  "the test that a revoked token stops reaching the rail.",
    ),
    Requirement(
        key="opt_out_of_one_transaction",
        source="rbi_emandate_2026",
        requirement="The customer can opt out of a particular transaction or of the "
                    "e-mandate itself, validated by AFA, with an intimation sent.",
        status="partial",
        mechanism="A single transaction can be held: above the AFA threshold the gateway "
                  "escalates and will not execute without an approval. What is missing is "
                  "the other half — the approval is a record in ApprovalStore, not a "
                  "factor an issuer validated, and there is no channel that intimates the "
                  "customer. Held and denied orders are both written to the audit chain, "
                  "which is a record, not a notification.",
    ),
    Requirement(
        key="pre_debit_notification",
        source="rbi_emandate_2026",
        requirement="A pre-transaction notification reaches the customer at least 24 "
                    "hours before the debit, naming the merchant, the amount, the date "
                    "and time, the e-mandate reference and the reason.",
        status="gap",
        mechanism="Not implemented, and not partially implemented. The gateway decides "
                  "and calls the rail inside one request, so there is no 24-hour window "
                  "for a notice to sit in. Every field the notice needs does exist on the "
                  "resolved action and in the audit record — merchant, amount, "
                  "timestamp, mandate_id, and the clause that decided it — so this is "
                  "a missing delivery channel and a missing delay, not missing data.",
    ),
    Requirement(
        key="grievance_redressal",
        source="rbi_emandate_2026",
        requirement="The issuer runs a grievance redressal mechanism for complaints "
                    "about recurring transactions.",
        status="out_of_scope",
        mechanism="A desk an issuer staffs. What a gateway can contribute is the evidence "
                  "a complaint would be decided on: every decision is a hash-chained "
                  "audit record naming the clause, the resolved amount and the merchant, "
                  "and `mandate verify` proves any single record is in the chain.",
    ),
    Requirement(
        key="unauthorised_transaction_liability",
        source="rbi_emandate_2026",
        requirement="RBI's limited-liability rules for unauthorised electronic "
                    "transactions apply to recurring payments.",
        status="out_of_scope",
        mechanism="A liability allocation between a customer and their bank, which a "
                  "gateway is not party to. The relevant contribution is again the audit "
                  "chain: it records what was authorised, so a divergence between that "
                  "and what settled is answerable rather than arguable. rail.divergence "
                  "voids such an order rather than only detecting it.",
    ),
]


class RegulatoryPosture(BaseModel):
    mandate_id: str
    requirements: list[Requirement]
    held: int
    partial: int
    gaps: int
    out_of_scope: int
    citations: dict[str, dict[str, str]]
    uap_status: str


# Stated rather than mapped, on purpose. The protocol is announced and unpublished,
# so a clause-by-clause table against it would be invention, and inventing a
# compliance mapping is a worse failure than admitting there is nothing to map to.
UAP_POSTURE = (
    "NPCI's Unified Agent Protocol is expected at the Global Fintech Fest on "
    "9–11 September 2026. The specification is not published, so no clause in "
    "this policy is mapped onto it and none is claimed to survive it. What is public "
    "is that it is built on existing UPI rails including Reserve Pay, and that it "
    "means to let a customer set rule-based instructions for an agent covering when "
    "and how much to pay, with spending limits, audit trails and identity checks. "
    "Those three are what this project already produces and measures, which is a "
    "reason to expect the shapes to meet and not evidence that they do."
)


def posture(policy: Policy) -> RegulatoryPosture:
    """What the regulation asks of this component, and what it gets."""
    reqs = list(RBI_REQUIREMENTS)
    return RegulatoryPosture(
        mandate_id=policy.mandate_id,
        requirements=reqs,
        held=sum(1 for r in reqs if r.status == "held"),
        partial=sum(1 for r in reqs if r.status == "partial"),
        gaps=sum(1 for r in reqs if r.status == "gap"),
        out_of_scope=sum(1 for r in reqs if r.status == "out_of_scope"),
        citations=CITATIONS,
        uap_status=UAP_POSTURE,
    )


__all__ = [
    "CITATIONS",
    "RBI_REQUIREMENTS",
    "STATUSES",
    "UAP_POSTURE",
    "RegulatoryPosture",
    "Requirement",
    "posture",
]
