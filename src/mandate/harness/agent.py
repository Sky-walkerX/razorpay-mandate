"""The shopping agent under test. Deliberately not hardened.

Hardening it would confound the measurement: the question is how much the gateway
contains, not how much a careful prompt contains.
"""
from collections.abc import Iterator
from datetime import datetime

from pydantic import BaseModel

from mandate.gateway.core import Decision
from mandate.gateway.state import Verdict
from mandate.harness.catalog import Catalog
from mandate.money import Paise


class AgentTrace(BaseModel):
    steps: int = 0
    decisions: list[Decision] = []
    spent: Paise = Paise(0)
    stopped_reason: str = "done"
    model_notes: list[str] = []


class ShoppingAgent:
    def __init__(self, client, catalog: Catalog, model, max_steps: int = 30) -> None:
        self.client, self.catalog, self.model, self.max_steps = client, catalog, model, max_steps

    def stream(self, intent: str, now: datetime) -> Iterator[tuple[str, dict, Decision, AgentTrace]]:
        """Yield (tool_name, args, decision, trace) after each step.

        `run` drains this, so the loop exists once. A second copy of the loop for
        streaming would be a second place for the sweep's behaviour to drift.
        """
        trace = AgentTrace()
        while trace.steps < self.max_steps:
            call = self.model.next_call(trace)
            if call is None:
                trace.stopped_reason = "done"
                return
            name, args = call
            decision = self.client.call(name, args, now=now)
            trace.decisions.append(decision)
            trace.steps += 1
            if decision.executed and decision.downstream:
                trace.spent = Paise(int(trace.spent) + int(decision.downstream["amount"]))
            if decision.verdict is Verdict.UNKNOWN:
                trace.model_notes.append(f"escalated: {decision.message}")
            yield name, args, decision, trace
        trace.stopped_reason = "max_steps"

    def run(self, intent: str, now: datetime) -> AgentTrace:
        trace = AgentTrace()
        for _name, _args, _decision, trace in self.stream(intent, now):
            pass
        return trace
