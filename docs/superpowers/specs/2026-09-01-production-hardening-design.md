# Production hardening: AP2 export, a real Merkle log, and claims that cannot drift

Date: 2026-09-01. Status: approved in brainstorm, not yet planned.

## What this buys

Three of the four items below fix a claim the repo makes and cannot currently demonstrate. That
is the same failure this project has already caught twice, once when "signed policy" turned out
to be a SHA-256 hash with no key anywhere, and once when "0.2ms" turned out to be a number nobody
measured. The pattern repeats because nothing tests prose.

The fourth item, the AP2 export, is the only new capability. It exists because the README's
opening argument is that the payment rail speaks three scalars while people mean nine boundaries,
and that argument is stronger stated in the standard's own registry than in vocabulary this
project invented.

## Findings that motivated the work

**"Merkle" is not true.** `gateway/audit.py` is a hash chain. Each `AuditRecord` stores
`prev_hash` and `record_hash`, and `verify_chain()` replays every record from genesis. There is
no tree, no root, and no proof shorter than the whole log. The word appears in `README.md` lines
49, 66 and 79, four places in `ARCHITECTURE.md` (lines 5, 27, 103 and 131), and `cli.py:320`, which prints "Final Merkle
Hash" for what is a chain head. A hash chain is a good tamper-evident structure. Calling it a
Merkle tree promises logarithmic inclusion proofs that do not exist.

**`AuditLog.append()` is O(n squared).** It calls `self.records()` on every write, which reads and
pydantic-parses the entire log to find the previous hash and the next sequence number.

**AP2 moved to v0.2 and the README is on v0.1 vocabulary.** `README.md:27` says "AP2 Intent
Mandates". The current spec has a Checkout Mandate and a Payment Mandate, each in an open and a
closed stage, carried as SD-JWT verifiable digital credentials with a `vct` claim. Open Checkout
Mandates define exactly two constraint types, `checkout.allowed_merchants` and
`checkout.line_items`. AP2 v0.2 was donated to the FIDO Alliance.

**The latency sweep is unfinished.** `JudgeConsole.tsx` is clean; every `latency_ms` now comes
from `performance.now()`. Three residues remain. `HowItHolds.tsx:42` reads `< 0.4ms`, which is a
third invented number replacing the second, and the comment 328 lines below it already records
the measured 0.0075ms. `README.md:37` says "sub-millisecond code" while `README.md:64` gives the
honest breakdown. `ui/ruixen-bento-cards.tsx:102` carries stock "sub-millisecond execution"
boilerplate in a vendored component that nothing in `web/src` or `web/public` imports, so no page
renders it.

## Build order

Runway is two to three days. Estimates total about three, so the order is chosen for what
survives a cut.

| # | Work | Estimate | If cut |
|---|---|---|---|
| 1 | Honesty sweep plus the tests that lock each claim | 2h | Nothing. This is the floor. |
| 2 | AP2 export view | 1d | Drop whole. Nothing else depends on it. |
| 3 | Merkle tree, signed head, proofs | 1.5d | Retire the word instead. One hour, specified below. |
| 4 | CI workflow | 30m | Run the same commands locally, commit no YAML. |

Items 1 and 4 are the same job split in two. The tests that assert a README number matches a
generated artifact are written in item 1; the workflow that runs them on every push is item 4.

Item 3 is the designated cut. Its fallback is not "ship it half done" but a different, complete
change: rename the seven documentation sites and `cli.py:320` from "Merkle" to "hash-chained", and
add a paragraph to `ARCHITECTURE.md` saying a chain is tamper-evident but not efficiently
provable, because verifying one record means replaying all of them.

## 1. Honesty sweep

Four edits.

- `web/src/components/v2/HowItHolds.tsx:42`. `'< 0.4ms · no LLMs in payment path'` becomes
  `'0.0075 ms · no LLMs in payment path'`, the measured clause-evaluation median that the comment
  at line 370 already documents.
- `README.md:37`. Delete "sub-millisecond" from the solution sentence. Line 64 states the real
  breakdown and the two contradict each other 27 lines apart.
- `web/src/components/ui/ruixen-bento-cards.tsx`. Delete the file. Nothing in `web/src` or
  `web/public` imports it under any of its five exports, so the "sub-millisecond execution"
  string at line 102 is unrendered vendored boilerplate. Deleting it is cheaper than rewriting a
  claim on a component no page shows.
- `README.md:27`. "AP2 Intent Mandates" becomes the v0.2 vocabulary. Folded in here rather than
  into the AP2 item because it is a one-line correction that should land even if item 2 is cut.

`README.md:11`, the `<0.01ms` latency badge, is correct against the measured 0.0075ms and stays.

Three tests in `tests/test_docs.py`, following the pattern `tests/harness/test_evidence.py`
already set when it started comparing `evidence.json` against `policies/policy.yaml`.

`test_no_unmeasured_latency_in_web` greps `web/src/**/*.tsx` for millisecond literals, ignoring
Motion `duration`, `delay`, `transition` and easing values, and fails on anything outside an
allowlist holding only the two measured numbers. This test would have caught 0.2ms, then 0.38ms,
then 0.4ms.

`test_conformance_badge_matches_suite` parses `Conformance-9%2F9%20Blocked` out of `README.md:10`
and asserts the counts against the suite's own attack list.

`test_latency_badge_matches_architecture` ties `README.md:11` to the number in `ARCHITECTURE.md`
line 5, so the two cannot drift apart.

## 2. AP2 v0.2 export view

The AP2 credential sits alongside the native token. It does not replace it. `Gateway.propose()`,
`mint_agent_token()`, `verify_agent_token()`, the request path, and the 200 pre-minted pool tokens
are all untouched, so the 338 passing tests stay passing and the hostile-boundary work is not
disturbed.

New package `src/mandate/ap2/` with two modules. `schema.py` holds pydantic models mirroring the
v0.2 open Checkout Mandate. `render.py` turns a `Policy` into that document.

### The mapping

This table is the deliverable. Everything else in the item is plumbing.

| Constraint | AP2 v0.2 | Note |
|---|---|---|
| `merchant.allow` | `checkout.allowed_merchants` | Native. Direct translation. |
| `quantity.max_per_item` | `checkout.line_items` quantity | Partial. AP2 caps quantity across an acceptable-item set; this caps per SKU. Not the same predicate. |
| `budget.total` | none | Extension `mandate.budget.total` |
| `budget.per_transaction` | none | Extension `mandate.budget.per_transaction` |
| `budget.per_item` | none | Extension `mandate.budget.per_item` |
| `category.deny` | none | Extension `mandate.category.deny` |
| `item.deny_recent` | none | Extension `mandate.item.deny_recent` |
| `velocity` | none | Extension `mandate.velocity` |
| `time.window` | none | Extension `mandate.time.window` |

One native, one partial, seven with no type to map onto.

### Document shape and signing

`vct` is `mandate.checkout.open.1`. `iat` and `exp` come from `Policy.issued` and `Policy.expires`.
`checkout.line_items` draws its acceptable items from the price book, which is also the only place
the gateway trusts for prices, so the exported document and the enforced policy read the same
source.

Signing stays offline. `mandate ap2-export` signs with the issuer private key, the same key that
already signs policies and tokens. `GET /v1/mandate/ap2` serves the pre-signed artifact and never
holds a private key, because a gateway that could sign its own mandate would undo the boundary
this project spent step 4 of the last build order establishing.

Plain JWS, not SD-JWT selective disclosure. Selective disclosure is a documented non-goal for this
cycle, recorded in `ARCHITECTURE.md` so a reader does not mistake the omission for an oversight.

### Test

`test_every_constraint_is_mapped` asserts each of the nine `ConstraintId` members appears exactly
once in the rendered document and is classified native, partial or extension. A tenth constraint
fails this test until someone decides where it goes. `tests/policy/test_policy_covers_families.py`
already works this way.

## 3. Merkle tree, signed head, and proofs

### The tree is derived, not stored

`AuditRecord` does not change. Its `record_hash` becomes leaf *i* of an RFC 6962 tree computed
over the existing log. No schema change, no migration, existing `audit.jsonl` files stay valid,
`tests/gateway/test_audit.py` passes untouched, and the eight `AuditLog` call sites across
`runner.py`, `failure_demo.py`, `demo.py`, `session.py`, `core.py` and `conformance/suite.py`
keep working with no edit.

New module `src/mandate/gateway/merkle.py`. RFC 6962 domain separation, so a leaf hashes under a
`0x00` prefix and an interior node under `0x01`, which stops an attacker presenting a leaf as a
node. Functions: `root(leaves)`, `inclusion_proof(i, n)`, `consistency_proof(m, n)`.

### Key custody, which has a non-obvious answer

The gateway holds no private key. It therefore cannot sign a tree head with the issuer key, and
handing it that key to make signing work would destroy the property that makes the issuer offline
in the first place.

Certificate Transparency answers this by giving the log its own keypair, distinct from the CA's.
Same here. `mandate keygen --log` mints a log keypair. The gateway holds the log private key; the
issuer key stays offline and unreachable from the service.

Be explicit in `ARCHITECTURE.md` about what this does and does not buy:

> A compromised gateway can sign a false tree head. What it cannot do is sign one consistent with
> a head someone already holds while having deleted a record. Consistency proofs catch a rewrite
> after the fact. They do not catch a log that lies from its first head, which needs clients
> gossiping heads to each other. We did not build that.

That paragraph matters more than the code. An unqualified "cryptographically verifiable audit
log" would be the third instance of the failure this whole document exists to stop.

### Surface

- `GET /v1/audit/head` returns `{size, root, ts, sig}`, signed with the log key.
- `GET /v1/audit/proof?seq=N` returns the inclusion path, log2(n) hashes.
- `GET /v1/audit/consistency?from=A&to=B` returns a proof that head B extends head A with no
  rewrite.
- `mandate verify <receipt> --head <head.json>` runs offline against the log public key, with no
  access to the server.

The offline CLI is the point of the item. An inclusion proof a third party can only check by
asking the gateway proves nothing about the gateway.

### Bundled fix

`AuditLog` caches `_leaves` and `_head` on the instance, loading once, so `append()` stops
re-reading the log on every write.

### Tests

- Inclusion proofs verify for every leaf at every tree size up to 200.
- Editing or deleting any record makes its inclusion proof fail against the recorded root.
- A consistency proof between two heads fails when a record between them was rewritten.
- `mandate verify` rejects a head signed by the wrong key.

## 4. CI

`.github/workflows/ci.yml`, one job: `ruff check src tests`, `pytest`, `mandate conformance`. No
secrets, no network, no model calls. Conformance carries no `model` field by design and needs
none.

One thing to check during implementation rather than assume. `race.velocity` and `race.budget` run
200 trials each, and `CLAUDE.md` records that the trial count is load-bearing, because a broken
lock shows as one breach in 200 and not at all in 25. If the suite pushes CI past a few minutes,
raise the timeout. Do not lower the trial count.

## Out of scope

SD-JWT selective disclosure. AP2 closed Checkout Mandates and Payment Mandates, both of which need
a merchant-signed checkout object this project has no merchant to produce. Rail-side verification
of the exported credential. Gossip or external witnessing of tree heads. Per-token rate limiting,
structured logging and metrics, which are real production gaps but buy nothing a judge will read
in three days. An OWASP ASI01-ASI10 coverage matrix, considered and cut for runway; worth adding
if item 3 finishes early.

## Consequences for CLAUDE.md

Two conventions to add once this lands.

No prose claim about a measured quantity ships without a test tying it to the artifact that
measures it. The latency badge, the conformance badge and the web tiles are the first three.

The audit log's structure and its guarantee are described in the same sentence. "Merkle" alone is
what let a hash chain carry the word for weeks.
