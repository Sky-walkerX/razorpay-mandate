"""The Witness Architecture for Protocol Conformance Testing.

Every attack runs against both an UnhardenedGateway and a HardenedGateway.
An attack ONLY counts as BLOCKED if its witness proved it executes against
the unhardened gateway first. If the witness fails, the outcome is VACUOUS.
"""
from dataclasses import dataclass
from enum import StrEnum


class ConformanceOutcome(StrEnum):
    BLOCKED = "BLOCKED"   # witness executed, hardened denied (the claim)
    ESCAPED = "ESCAPED"   # witness executed, hardened executed (real hole)
    VACUOUS = "VACUOUS"   # witness failed to execute (invalid/unproven attack)


@dataclass(frozen=True)
class AttackResult:
    attack_id: str
    outcome: ConformanceOutcome
    witness_executed: bool
    hardened_executed: bool
    detail: str = ""


class UnhardenedGateway:
    """Deliberately unhardened gateway fixture.

    Must remain genuinely vulnerable to token replay, price-lying,
    capture divergence, and concurrency races so witnesses can prove exploitability.
    """
    def __init__(self, policy, downstream):
        self.policy = policy
        self.downstream = downstream
        self.seen_jtis = set()
        self.order_count = 0
        self.budget_spent = 0

    def propose_naive(self, agent_amount: int, jti: str = "", skus: list[str] | None = None):
        from mandate.money import Paise
        self.order_count += 1
        self.budget_spent += agent_amount
        receipt = f"naive_rcpt_{self.order_count}_{jti}"
        res = self.downstream.create_order(
            Paise(agent_amount),
            receipt=receipt,
            notes={"mandate_id": getattr(self.policy, "mandate_id", "mnd_naive")},
            skus=skus or ["sku_01"],
        )
        return {"executed": True, "downstream": res, "verdict": "ALLOW"}

    def capture_naive(self, order_id: str, agent_amount: int):
        from mandate.money import Paise
        res = self.downstream.capture_payment(order_id, Paise(agent_amount))
        return {"executed": True, "result": res}

