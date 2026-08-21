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
