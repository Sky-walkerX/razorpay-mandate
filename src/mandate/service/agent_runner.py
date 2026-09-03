"""Drives a live model agent against the gateway for the judge console.

The agent here is the same `ShoppingAgent` the evaluation sweep drives, talking to
the same gateway over the same HTTP surface. Nothing about the loop is special-cased
for the demo, because a demo that runs different code than the measurement is not
evidence of anything.
"""
import os
import threading
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path

from mandate.gateway.core import Mode
from mandate.gateway.pricebook import DictPriceBook
from mandate.harness.agent import ShoppingAgent
from mandate.harness.agent_model import AgentModel
from mandate.harness.catalog import Catalog

CLEAN = "clean"
DEFAULT_DAILY_CALL_CEILING = 2000

# How many turns one console run gets. The sweep runs at 30, which is right for a
# measurement nobody is watching and wrong for a stage: an unenforced agent has
# nothing to stop it, so it shops until the cap, and 30 model calls of it is
# minutes of a judge waiting on the pane that says the least.
#
# The number is the same for both arms and must stay that way. "One instruction,
# one shop, run twice, the only difference is whether the gateway may refuse" is
# the claim the panel makes in words; two step budgets would make it false.
DEMO_MAX_STEPS = 10


class CeilingReached(Exception):
    """The daily model-call budget is spent."""


class DailyCallBudget:
    """A process-wide count of model calls per UTC day.

    Cloud Run runs this at --min-instances=1 --max-instances=1, so one in-process
    counter is the whole deployment rather than an approximation of it. If that
    ever scales past one instance this becomes a per-instance limit and needs
    saying out loud rather than silently under-counting.
    """

    def __init__(self, ceiling: int | None = None) -> None:
        if ceiling is None:
            ceiling = int(os.environ.get("MANDATE_DAILY_CALL_CEILING",
                                         DEFAULT_DAILY_CALL_CEILING))
        self.ceiling = ceiling
        self._lock = threading.Lock()
        self._day = datetime.now(UTC).date()
        self._used = 0

    def _roll(self) -> None:
        today = datetime.now(UTC).date()
        if today != self._day:
            self._day, self._used = today, 0

    @property
    def used(self) -> int:
        with self._lock:
            self._roll()
            return self._used

    @property
    def remaining(self) -> int:
        with self._lock:
            self._roll()
            return max(0, self.ceiling - self._used)

    def reserve(self, n: int) -> None:
        """Claim n calls up front, or raise. Reserving the whole run's worst case
        before it starts stops a long retry storm from overshooting the ceiling."""
        with self._lock:
            self._roll()
            if self._used + n > self.ceiling:
                raise CeilingReached(
                    f"daily model-call ceiling reached ({self._used}/{self.ceiling})"
                )
            self._used += n

    def refund(self, n: int) -> None:
        with self._lock:
            self._used = max(0, self._used - n)


class FamilyCatalogs:
    """Hostile catalogs, indexed by attack family, loaded from the frozen corpus.

    The service otherwise serves `clean_catalog`, which carries no injected text.
    A live agent shopping that catalog has nothing to be attacked by, so the
    console would demonstrate the gateway refusing arithmetic and nothing else.
    """

    def __init__(
        self,
        corpus_path: Path | str = Path("corpus/corpus.json"),
        clean: Catalog | None = None,
    ) -> None:
        # `clean` is the catalog this service actually serves at /v1/catalog. The
        # agent must shop the catalog the console displays, or a judge compares a
        # refusal against products they never saw.
        self._by_family: dict[str, Catalog] = {}
        self._clean: Catalog | None = clean
        # The provenance of the hostile text. A page claiming an attack predates
        # the gateway should be able to name the corpus it came from.
        self.corpus_hash: str | None = None
        path = Path(corpus_path)
        if not path.exists():
            return
        keep_clean = self._clean is not None
        from mandate.harness.corpus import corpus_hash, load_corpus

        items = load_corpus(path)
        self.corpus_hash = corpus_hash(items)
        for item in items:
            if not keep_clean and self._clean is None and item.mutation.clean_catalog is not None:
                self._clean = item.mutation.clean_catalog
            if item.is_attack and item.family_id not in self._by_family:
                self._by_family[item.family_id] = item.mutation.catalog

    @property
    def families(self) -> list[str]:
        return [CLEAN, *sorted(self._by_family)]

    def get(self, family: str) -> Catalog | None:
        if family == CLEAN:
            return self._clean
        return self._by_family.get(family)


class AgentEvent(dict):
    """One SSE payload. A plain dict so the handler can json.dumps it directly."""


def run_agent_stream(
    *,
    intent: str,
    catalog: Catalog,
    client,
    provider,
    compromised: bool,
    mode: Mode,
    max_steps: int = 30,
    on_decision: Callable[[object], None] | None = None,
) -> Iterator[AgentEvent]:
    """Yield one `step` and one `verdict` event per agent turn, then `done`.

    `mode` is echoed on every event, not just applied to the gateway. A judge who
    screenshots an unenforced pane has a screenshot of money leaking, so the arm
    it came from travels with the data rather than living only in the CSS.

    `on_decision` receives each `Decision` as it happens. The events are a view
    for the browser and drop the resolved line items; a caller that needs to
    record what was actually decided gets the object rather than parsing the
    view back apart.
    """
    model = AgentModel(catalog=catalog, intent=intent, provider=provider,
                       compromised=compromised)
    agent = ShoppingAgent(client=client, catalog=catalog, model=model, max_steps=max_steps)
    now = datetime.now(UTC)

    trace = None
    for name, args, decision, trace in agent.stream(intent, now):
        yield AgentEvent(
            event="step", mode=mode.value, n=trace.steps, tool=name,
            merchant=args.get("merchant"), items=args.get("items", []),
        )
        if on_decision is not None:
            on_decision(decision)
        yield AgentEvent(
            event="verdict", mode=mode.value, n=trace.steps,
            verdict=decision.verdict.value, clause=decision.clause_id,
            message=decision.message, executed=decision.executed,
            downstream=decision.downstream, spent=int(trace.spent),
        )

    yield AgentEvent(
        event="done", mode=mode.value,
        steps=trace.steps if trace else 0,
        spent=int(trace.spent) if trace else 0,
        stopped_reason=trace.stopped_reason if trace else "done",
    )


def pricebook_for(catalog: Catalog) -> DictPriceBook:
    return DictPriceBook.from_catalog(catalog)


class TokenBoundClient:
    """DirectClient with the session token attached.

    `ShoppingAgent` calls `client.call(name, args, now=now)` with no token, and
    `Gateway.propose` requires one. Binding it here keeps the agent ignorant of
    credentials, which is the property the whole boundary rests on.
    """

    def __init__(self, gateway, token: str) -> None:
        from mandate.adapters.direct import DirectClient

        self._inner = DirectClient(gateway)
        self._token = token

    def call(self, name: str, args: dict, now=None):
        return self._inner.call(name, args, now=now or datetime.now(UTC), token=self._token)
