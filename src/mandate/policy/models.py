"""The policy document. Nine constraint types, closed set, no user-defined predicates."""
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


class Provenance(BaseModel):
    stated: list[ConstraintId] = Field(default_factory=list)
    inferred: list[ConstraintId] = Field(default_factory=list)


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
        declared = set(self.provenance.stated) | set(self.provenance.inferred)
        both = set(self.provenance.stated) & set(self.provenance.inferred)
        if both:
            raise ValueError(f"constraints in both stated and inferred: {sorted(both)}")
        missing = set(self.constraints) - declared
        if missing:
            raise ValueError(f"constraints absent from provenance: {sorted(missing)}")
        return self
