# What broke

## Day 1, 22 Aug

Nothing broke in the money type or the fake downstream. Two things did break in getting
`make check` to prove the wiring:

**`.env.example` is a real risk, not a template, if you're not careful.** It's tracked in git
and not gitignored (only `.env` is). Real Razorpay test keys got pasted into it once, which
would have committed live-testable secrets into history on the next `git add`. Caught before
commit by diffing against HEAD and moving the values to `.env`. Recording this because it will
happen again to someone reading this repo: don't paste real values into `.env.example`.

**`mandate check` fails today; bare `mandate` doesn't.** `cli.py` has exactly one registered
Typer command (`check`). Typer collapses a single-command app so it runs without a subcommand
name, and errors on `check` as an unexpected extra argument instead. The underlying wiring is
proven either way — `mandate` alone created a real test-mode order and read it back — but
`make check`, which literally invokes `mandate check`, fails until a second command exists.
Task 5 adds `corpus build`, at which point Typer stops collapsing and `mandate check` starts
working exactly as written. Left `cli.py` alone rather than patching around a bug that fixes
itself in three days.

Razorpay test keys must be generated from the dashboard in test mode specifically; the live
keys are visually near-identical and the only guard is the `rzp_test_` prefix, which is why
that assertion is in the constructor rather than in config validation.

## Day 3, 24 Aug

**A fixed-seed RNG draw picked the one payload that didn't match its own test.**
`injection.description` and `injection.seller_name` each draw one of three `INJECTION_PAYLOADS`
with `rng.choice`. At `random.Random(1)`, both draw the third payload, and only the first two
contained the literal string `"SYSTEM"` — the marker both tests check for. Confirmed
deterministically rather than assumed flaky: reran the exact draw outside pytest and got the
same payload every time. Fixed by prefixing the third payload with `SYSTEM:` too, so all three
read as the same class of injected instruction and the marker check holds regardless of which
one the RNG draws.

## Day 6-8, 27-29 Aug

Three plan/test mismatches, all caught by running the tests rather than trusting the plan text:

**`ALL_EVALUATORS` order named the wrong clause on a double violation.** An action that breaches
both `budget.total` and `budget.per_transaction` at once denied on whichever evaluator runs
first. The original order checked `budget_total` before `budget_per_transaction`, so a single
oversized purchase got blamed on the coarser total-budget clause instead of the more specific
per-transaction one — technically correct (both are violated), but the wrong clause to show a
human. Reordered so per-transaction, the more specific constraint, is checked first.

**`fmt()`'s Indian digit grouping broke a substring assertion in the denial message.** The gateway's
`_explain()` used `fmt()` to render amounts in denial messages, which inserts commas
(`₹2,000.00`). A test asserting `"2000" in message` failed because `"2000"` is not a substring of
`"2,000"`. `_explain()` now formats amounts without grouping; `fmt()` itself is untouched since
its grouping is correct everywhere else it's used.

**Task 17's test imports a helper Task 15 didn't build for reuse.** `test_idem_integration.py`
calls `_act(rupees(99), sku=f"s{i}")` importing `_act` from `test_core.py`, but that `_act` took
only `amount` and hardcoded `sku="s1"`. Added a `sku="s1"` default parameter — matches the pattern
Task 16's own `_act` already used, so this was a one-helper omission rather than a design
disagreement.

None of these were logic bugs in the constraint evaluators themselves — the nine evaluators, the
lattice, the ledger, and the audit chain all passed on the first implementation. The breakage was
entirely in the glue: evaluator ordering, message formatting, and test-helper signatures drifting
from what a later task's test expected.

## Day 10, 31 Aug

**`Policy.constraints` was typed too narrowly to hold what the compiler emits.** The field was
`dict[ConstraintId, dict]`, which is correct for `budget.total`'s `{"max": ...}` shape but wrong
for `merchant.allow` and `category.deny`, which are lists (`["alcohol"]`). Task 11's tests never
caught this because they mutated `ctx.policy.constraints[cid]` directly on an already-built
`Policy` object, bypassing Pydantic validation entirely. Task 20's compiler is the first thing
that actually constructs a `Policy` from raw JSON containing a list-valued constraint, and that's
where the too-narrow type surfaced. Widened to `dict[ConstraintId, dict | list]`.
