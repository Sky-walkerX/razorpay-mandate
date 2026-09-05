"""The witness architecture for protocol conformance testing.

Every attack runs twice: once against `UnhardenedGateway`, once against the real
`Gateway`. The first run is the witness, and its only job is to prove the attack
is real. An attack whose witness does not fire is VACUOUS and counts as nothing.

`UnhardenedGateway` mirrors the real gateway's API on purpose, so an attack is one
piece of code pointed at two objects rather than two pieces of code that drift.
It is Mandate as it stood before this cycle: it trusts agent-supplied prices, it
hashes agent-controlled fields into the idempotency key, it never verifies a
token, it reserves nothing atomically, and it captures whatever amount it is
asked for. Every one of those is a vulnerability recorded in the design spec.

Keeping it exploitable is load-bearing. If it is quietly fixed, every witness goes
vacuous and the suite stops testing anything, which is why
`tests/conformance/test_unhardened_gateway_is_exploitable.py` asserts that it can
still be broken.
"""
import base64
import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from mandate.gateway.action import Proposal, ProposalItem
from mandate.gateway.state import Verdict
from mandate.money import Paise


class ConformanceOutcome(StrEnum):
    BLOCKED = "BLOCKED"   # witness executed, hardened denied (the claim)
    ESCAPED = "ESCAPED"   # witness executed, hardened executed (a real hole)
    VACUOUS = "VACUOUS"   # witness did not execute (attack unproven; counts as nothing)


@dataclass(frozen=True)
class AttackResult:
    attack_id: str
    outcome: ConformanceOutcome
    witness_executed: bool
    hardened_executed: bool
    detail: str = ""

    @staticmethod
    def judge(
        attack_id: str,
        witness_executed: bool,
        hardened_executed: bool,
        detail: str = "",
    ) -> "AttackResult":
        """The tri-state, decided in one place so no attack can decide it its own way.

        The witness gate comes first and is not overridable: an attack that could
        not be carried out against the unhardened gateway is VACUOUS whatever the
        hardened gateway did.
        """
        if not witness_executed:
            return AttackResult(
                attack_id, ConformanceOutcome.VACUOUS, witness_executed, hardened_executed,
                f"VACUOUS: the witness did not execute, so this attack is unproven. {detail}".strip(),
            )
        outcome = (
            ConformanceOutcome.ESCAPED if hardened_executed else ConformanceOutcome.BLOCKED
        )
        return AttackResult(attack_id, outcome, witness_executed, hardened_executed, detail)


@dataclass
class UnhardenedDecision:
    verdict: Verdict
    executed: bool
    amount: int = 0
    downstream: dict | None = None
    idem_key: str = ""
    capability: str | None = None
    message: str = ""


@dataclass
class UnhardenedGateway:
    """Mandate before the hostile-agent boundary. Deliberately, permanently broken.

    Do not fix anything in this class. Each weakness below is the witness for one
    named attack in the suite.
    """
    policy: object
    downstream: object
    # jtis seen, recorded but never enforced -- the token replay witness
    seen_jtis: set = field(default_factory=set)
    # keyed by the agent-steerable idempotency key
    committed: dict = field(default_factory=dict)
    # per-token budgets, which is what makes delegation splitting work
    spent_by_token: dict = field(default_factory=dict)
    order_count: int = 0

    @staticmethod
    def _stated_price(item: ProposalItem, prices: dict[str, int]) -> int:
        if getattr(item, "quote", None):
            try:
                parts = item.quote.split(".")
                pad = len(parts[0]) % 4
                s = parts[0] + ("=" * (4 - pad) if pad else "")
                payload = json.loads(base64.urlsafe_b64decode(s).decode("utf-8"))
                return int(payload.get("unit_price_paise", prices.get(item.sku, 0)))
            except (json.JSONDecodeError, ValueError, TypeError, KeyError):
                pass
        return prices.get(item.sku, 0)

    # -- the agent-steerable idempotency key -------------------------------
    def naive_intent(self, prop: Proposal, unit_prices: dict[str, int]) -> str:
        """Hashes agent-controlled fields, so perturbing one mints a fresh key."""
        body = {
            "type": str(prop.type),
            "merchant": prop.merchant,
            "attempt": prop.attempt,            # agent-controlled
            "items": [
                {"sku": i.sku, "qty": i.qty,
                 "unit_price": self._stated_price(i, unit_prices)}   # agent-controlled
                for i in prop.items
            ],
        }
        return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()

    def propose(
        self,
        proposal: Proposal,
        now: datetime | None = None,
        token: str | None = None,
        unit_prices: dict[str, int] | None = None,
    ) -> UnhardenedDecision:
        """No token check, agent-supplied prices, no lock, per-token budget."""
        prices = unit_prices or {}
        idem = self.naive_intent(proposal, prices)

        if idem in self.committed:
            return UnhardenedDecision(
                Verdict.ALLOW, executed=False, idem_key=idem,
                downstream=self.committed[idem], message="duplicate suppressed by luck",
            )

        # The witness reads the quote's stated price without checking a signature.
        # This is the vulnerability the hardened gateway removes. Do not fix it.
        amount = sum(self._stated_price(i, prices) * i.qty for i in proposal.items)

        # Budget is tracked per token, not per mandate: two tokens, two budgets.
        key = token or "anonymous"
        cap = self._budget_cap()
        # Read-then-write with no lock. This is the race. The sleep does not create
        # the bug, it only widens the window so the witness fires deterministically
        # instead of depending on how the interpreter happens to schedule threads:
        # a witness that fires one run in fifty would report VACUOUS and hide a real
        # attack behind flakiness.
        already = self.spent_by_token.get(key, 0)
        time.sleep(0.001)
        if cap is not None and already + amount > cap:
            return UnhardenedDecision(Verdict.DENY, executed=False, idem_key=idem,
                                      message="over the per-token budget")

        if token:
            self.seen_jtis.add(token)   # recorded, never enforced
        self.order_count += 1
        self.spent_by_token[key] = already + amount

        body = self.downstream.create_order(
            Paise(amount),
            receipt=f"naive_{self.order_count}",
            notes={"mandate_id": getattr(self.policy, "mandate_id", "mnd_naive")},
            skus=[i.sku for i in proposal.items],
        )
        self.committed[idem] = body
        return UnhardenedDecision(Verdict.ALLOW, executed=True, amount=amount,
                                  downstream=body, idem_key=idem,
                                  capability="", message="allowed")

    def _budget_cap(self) -> int | None:
        constraints = getattr(self.policy, "constraints", {}) or {}
        for cid, cfg in constraints.items():
            if str(cid) == "budget.total" and isinstance(cfg, dict):
                return cfg.get("max")
        return None

    # -- no capture binding -------------------------------------------------
    def capture_payment(self, order_id: str, amount: int, capability: str = "",
                        **_kw) -> UnhardenedDecision:
        """Captures whatever it is asked for. This is price.flip#004."""
        res = self.downstream.capture_payment(order_id, Paise(int(amount)))
        return UnhardenedDecision(Verdict.ALLOW, executed=True, amount=int(amount),
                                  downstream=res if isinstance(res, dict) else {"result": res})
