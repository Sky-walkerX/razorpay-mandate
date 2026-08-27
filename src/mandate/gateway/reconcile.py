"""Resolve PENDING entries by asking the downstream what actually happened.

The receipt field carries the idem_key, which is what makes this possible at all.
"""
from mandate.gateway.idem import EntryState, Ledger


class Reconciler:
    def __init__(self, ledger: Ledger, downstream) -> None:
        self.ledger = ledger
        self.downstream = downstream

    def run(self) -> dict[str, EntryState]:
        out: dict[str, EntryState] = {}
        for entry in self.ledger.pending():
            found = self.downstream.find_orders_by_receipt(entry.idem_key)
            if found:
                self.ledger.mark_committed(entry.idem_key, found[0])
                out[entry.idem_key] = EntryState.COMMITTED
            else:
                self.ledger.mark_failed(entry.idem_key, "not found downstream")
                out[entry.idem_key] = EntryState.FAILED
        return out
