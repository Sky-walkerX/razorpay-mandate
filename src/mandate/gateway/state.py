"""Accumulated state and the evaluation context. No I/O lives here."""
from datetime import datetime
from enum import StrEnum
from pydantic import BaseModel, Field
from mandate.money import Paise
from mandate.gateway.action import Action
from mandate.policy.models import Policy, ConstraintId


class Verdict(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    UNKNOWN = "UNKNOWN"


class ClauseResult(BaseModel):
    id: ConstraintId | str
    result: Verdict
    observed: int | str | None = None
    limit: int | str | None = None
    detail: str = ""


class AccumulatedState(BaseModel):
    committed: Paise = Field(default=0)
    pending: Paise = Field(default=0)
    action_count: int = 0
    recent_skus: set[str] = Field(default_factory=set)
    actions_in_window: int = 0

    @property
    def spent(self) -> Paise:
        """Committed plus pending. Never committed alone."""
        return Paise(int(self.committed) + int(self.pending))


class EvalContext(BaseModel):
    action: Action
    policy: Policy
    state: AccumulatedState
    now: datetime
    resolved_merchant: str | None = None
    resolved_categories: dict[str, str | None] = Field(default_factory=dict)
