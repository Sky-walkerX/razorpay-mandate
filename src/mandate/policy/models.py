"""The policy document. Ten constraint types, closed set, no user-defined predicates."""
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ConstraintId(StrEnum):
    BUDGET_TOTAL = "budget.total"
    BUDGET_PER_TRANSACTION = "budget.per_transaction"
    BUDGET_PER_ITEM = "budget.per_item"
    MERCHANT_ALLOW = "merchant.allow"
    CATEGORY_DENY = "category.deny"
    ITEM_DENY_RECENT = "item.deny_recent"
    VELOCITY = "velocity"
    TIME_WINDOW = "time.window"
    QUANTITY_MAX_PER_ITEM = "quantity.max_per_item"
    AFA_REQUIRED = "afa.required"


class Provenance(BaseModel):
    """Where each clause came from, kept in three separate buckets.

    `stated` is in the user's own sentence. `inferred` is the compiler's guess and
    is the only bucket the read-back asks the user to confirm. `regulatory` is a
    floor imposed by law, which the user never said and the compiler never guessed:
    RBI's Digital Payments E-mandate Framework, 2026 requires an additional factor
    above Rs 15,000 whether or not anyone asked for it. Filing that under `inferred`
    would credit the model for a rule it did not produce.
    """

    stated: list[ConstraintId] = Field(default_factory=list)
    inferred: list[ConstraintId] = Field(default_factory=list)
    regulatory: list[ConstraintId] = Field(default_factory=list)


class CompilerInfo(BaseModel):
    model: str
    temperature: float
    version: str


class Policy(BaseModel):
    version: int = 1
    mandate_id: str
    principal: str
    agent: str
    issued: datetime
    expires: datetime
    constraints: dict[ConstraintId, dict | list]
    provenance: Provenance
    source_text: str
    compiler: CompilerInfo

    @model_validator(mode="after")
    def _check(self) -> "Policy":
        if self.issued.tzinfo is None or self.expires.tzinfo is None:
            raise ValueError("issued and expires require an explicit timezone")
        if self.expires <= self.issued:
            raise ValueError("expires must be after issued")
        buckets = {
            "stated": set(self.provenance.stated),
            "inferred": set(self.provenance.inferred),
            "regulatory": set(self.provenance.regulatory),
        }
        declared = set().union(*buckets.values())
        names = sorted(buckets)
        for i, a in enumerate(names):
            for b in names[i + 1:]:
                if (both := buckets[a] & buckets[b]):
                    raise ValueError(f"constraints in both {a} and {b}: {sorted(both)}")
        missing = set(self.constraints) - declared
        if missing:
            raise ValueError(f"constraints absent from provenance: {sorted(missing)}")
        return self
