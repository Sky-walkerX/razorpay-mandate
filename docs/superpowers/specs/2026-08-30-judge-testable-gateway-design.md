# Judge-testable gateway: design

Written 2026-08-30. Read `2026-08-29-hostile-agent-boundary-design.md` first; this
builds directly on the service, tokens and price book it introduced.

## The claim this buys

Today the enforcement claim is something a judge reads. After this work it is
something a judge attacks. They open a URL, get their own mandate with its own
budget and its own audit chain, and spend ten minutes trying to make the gateway
pay for something it should not. Every refusal names the clause that fired and
extends a hash chain they watched grow.

The second claim it buys is that Razorpay is load-bearing. Right now every
measured run goes through `FakeDownstream` and `RazorpayDownstream` appears only
in `mandate check`. After this, a judge's ALLOW creates a real test-mode order
they can find in a Razorpay dashboard.

## What is broken today, verified rather than assumed

Booted `mandate serve --port 8811`, minted a token with `mandate issue-token`,
posted an order:

```
POST /v1/orders  {"merchant":"blinkit","items":[{"sku":"sku_dal_toor_2kg","qty":1}]}
-> {"verdict":"DENY","clause_id":"pricebook",
    "message":"unknown SKU: \"SKU 'sku_dal_toor_2kg' not found in price book\""}
```

`/health` returns the real mandate id and policy hash. Token signature, expiry,
mandate binding and revocation all work. Four things block a judge demo:

1. `serve_cmd` in `cli.py` calls `create_app` without a price book, so
   `create_app` falls back to an empty `DictPriceBook()` and every SKU fails
   closed. `DictPriceBook.from_catalog()` already exists and is wired into
   nothing but tests and the harness runner.
2. `create_app` defaults `downstream` to `FakeDownstream()`. Nothing constructs
   `RazorpayDownstream` outside `mandate check`.
3. One gateway, one ledger, one audit log for the whole process. The second
   judge finds a mandate that already spent its Rs 2,000, and every refusal
   after that cites `budget.total` instead of the clause the attack aimed at.
4. Three write endpoints and no read endpoints. A browser cannot fetch the
   catalog to render items, the policy to render limits, or the audit chain to
   render the chain.

## Architecture

### One container, one origin

Starlette serves the API and the built Vite bundle from the same app.
`StaticFiles` mounts at `/` after the `/v1` routes so nothing shadows the API.
One Cloud Run service, one URL, no CORS configuration, and no second deploy that
can be misconfigured separately.

The alternative considered and rejected: gateway on Cloud Run, frontend on
Firebase Hosting. It buys independent frontend deploys during the build and
costs a CORS config plus a second failure mode in the room.

Also rejected, for a reason worth recording: a stateless design where the
browser tracks its own spend and sends it with each request. That would make a
constraint read a field the agent supplied, which is the one rule the gateway is
built on. The conformance suite would flag it.

### Sessions

A session is identified by the `jti` already inside the bearer token.
`_extract_and_verify_token` parses `TokenClaims` today, so the server keeps
`dict[jti, Session]` and resolves the session from a token it was already
verifying. No cookie, no session header, no new identifier.

A session owns a directory `/tmp/sessions/<jti>/` containing its own
`audit.jsonl` and `ledger.jsonl`, plus a `Gateway` built against those paths.
`Ledger` and `AuditLog` both take a path and need no change.

Every session shares the signed policy, the catalog, the price book and the
`RevocationList`, because all four are read-mostly and identical per session.

Sessions live in memory and in `/tmp`. A redeploy or a cold start wipes them,
which is acceptable: a judge mid-test loses their chain, reloads, and gets a
fresh one. Cloud Run runs at `min-instances=1, max-instances=1` so every request
reaches the same container and no request lands on an instance that never saw
the session.

Live sessions cap at 100. The oldest session idle for more than 30 minutes is
evicted and its directory deleted. Its token returns to the pool only if the
judge did not revoke it; a revoked `jti` is retired permanently.

### The token pool, and why the issuer stays offline

Per-session revocation needs per-session `jti` values, and minting a token needs
the Ed25519 private key. Putting that key in a public container would contradict
decision 2 of the hostile agent boundary spec, which says the issuer is an
offline CLI and never a daemon, and a judge who reads both would catch it.

So the tokens are pre-minted. Run `mandate issue-token --jti tok_pool_NNN` 200
times offline, all bound to `mnd_groceries_01`, expiring after the judging
window, and write the pool to `.mandate/token_pool.json`.

That file is not committed. It holds 200 valid bearer tokens for a live gateway,
and a security project that checks credentials into its own repository has
already lost the argument. `.mandate/` stays gitignored, the pool goes into
Secret Manager, and Cloud Run mounts it at boot. Regenerating it is one offline
command, so losing it costs nothing.

A revoked `jti` never returns to the pool. Revocation is permanent by design and
recycling a revoked token would hand the next judge a dead session. Pool
exhaustion returns 503 rather than sharing a token between two sessions.

The gateway still holds only the public key. The offline-issuer claim stays
literally true, and "could I get the server to sign a token for a higher cap"
has the answer that the server cannot sign anything.

### The one rule, on the HTTP path

`Proposal` carries `{type, merchant, items: [{sku, qty}]}`. The judge console
sends exactly that. A judge who opens devtools and adds `unit_price` or `title`
to the request body changes nothing, because `ProposalItem` does not carry those
fields and `_resolve_to_action` reads prices from the price book or raises.

This is asserted by a test rather than left to inspection. See Testing.

## API

Nine endpoints. Four are reads.

| Method | Path | Behaviour |
|---|---|---|
| `POST` | `/v1/sessions` | Claims a pool token, creates the session directory, builds the `Gateway`. Returns `{token, jti, mandate_id, expires}` |
| `GET` | `/v1/catalog` | SKUs, titles, categories and prices from `corpus/corpus.json`. Shared and static |
| `GET` | `/v1/policy` | Nine clauses with bounds, `stated` versus `inferred`, policy hash, signature status |
| `POST` | `/v1/orders` | Exists. Now resolves the session from the token before calling `propose()` |
| `POST` | `/v1/payments/capture` | Exists. Same session resolution |
| `GET` | `/v1/audit` | The session's `AuditRecord` list plus `chain_intact` from `verify_chain()` |
| `GET` | `/v1/headroom` | Remaining room on each limit for this session |
| `POST` | `/v1/revoke` | Revokes the caller's own `jti`. A session cannot name another session's `jti` |
| `POST` | `/v1/compile` | One temperature-0 model call. See the compile panel below |

`GET /v1/conformance` serves `results-conformance/conformance_results.json` and the
precomputed mutation sets beside it as static file reads.

`GET /health` keeps its current shape.

### What the order response carries

`Decision` returns the blocking clause only: `verdict`, `clause_id`, `message`,
`idem_key`, `downstream`, `executed`, `capability`. The console needs every
clause that evaluated, with observed against limit.

Rather than widen `Decision`, which the harness and 321 tests depend on, the
handler reads back the record `propose()` just wrote. `AuditRecord` already
carries `clauses: list[ClauseResult]` with `id`, `result`, `observed` and
`limit`, plus `prev_hash` and `record_hash`. The response is:

```json
{
  "decision": { ...Decision... },
  "record":   { ...AuditRecord... },
  "headroom": [ { "clause_id": ..., "used": ..., "limit": ..., "remaining": ... } ]
}
```

Headroom rides on the order response so one click is one round trip. Fetching it
separately would make the limit bars lag the verdict by a frame, which on a
projector reads as a bug. `GET /v1/headroom` exists for the first paint, when the
console has a session but has not yet placed an order.

The enforcement path does not change. The handler composes a response; it does
not re-derive a rule.

### Failure behaviour

- A valid token with no session returns 409 with "call POST /v1/sessions first".
- An exhausted pool returns 503.
- A Razorpay error surfaces as `executed: false` carrying the rail's message,
  never dressed as a policy denial. A judge must always be able to tell which
  layer refused.

## The judge console

New route `/try`. The landing at `/` and the operator console at `/dashboard`
stay. `/v2` is deleted in the same pass, because three front doors is one more
than a three-minute pitch can explain.

Three columns.

**Left, the mandate.** Nine limits, each with a headroom bar that drains as the
judge spends. Policy hash, signature status, the session `jti`, and a revoke
button. `constraintReadout.ts` and `headroom.ts` compute these rows today from
`evidence.json`; the change is swapping their input for the live session.

**Centre, the attack rail.** Ten buttons, each labelled by what it attempts
rather than by the clause it will hit, because the clause is the answer and the
gateway should give it:

1. Buy toor dal from Blinkit. The control. Returns ALLOW with a real order id
2. Swap for the Rs 400 organic dal. `budget.per_item`
3. Order from a lookalike merchant. `merchant.allow`
4. Add beer to the basket. `category.deny`
5. Order 40 packets of atta. `quantity.max_per_item`
6. Build a Rs 1,400 basket. `budget.per_transaction`
7. Place a fourth order. `velocity`
8. Submit the same order twice. One order on the rail, not two
9. Nudge the price by a paisa and resubmit. The idempotency key does not move
10. Revoke the token, then buy. 403

Below them a free-form composer: merchant dropdown, item picker, quantity. It
posts `{sku, qty}` and nothing else.

`scenarios.ts` already models five loads with hostile-marked payload text and is
most of this content model.

**Right, the decision stream.** Newest on top. Each entry shows the verdict as a
chip that differs by shape and label rather than by colour alone, the clause id,
observed against limit in rupees, the resolved amount, the idempotency key, the
`record_hash` beside its `prev_hash` so the chain reads as a chain, and the
Razorpay `order_` id when the rail executed.

No websockets and no SSE. One click is one request and one response.

### The compile panel, and what it does not do

The judge types a mandate in plain language. `POST /v1/compile` runs one
temperature-0 call through Vertex and returns nine constraints marked `stated`
or `inferred`.

It does not become the enforced policy. Signing needs the private key and the
server does not have it, by the same decision that produced the token pool. The
panel states this in a line under the result: the gateway enforces the policy
signed offline on 1 September 2026, shown beside what your sentence compiles to.

This is a feature. A judge asking "could I inject a policy that lets me spend
more" gets the answer that the server is structurally incapable of signing one.
The compile panel demonstrates the compiler. The mandate column shows what
binds. Two claims, labelled as two.

On timeout past 8 seconds or any provider error, the panel falls back to the
pre-compiled policy with the fallback labelled rather than hidden.

## Rail divergence

`propose()` calls `create_order`, sets `executed = True`, and mints the capture
capability. The check goes between those two steps: compare
`int(downstream_body["amount"])` against `int(action.amount)`.

On divergence:

- Do not mint the capture capability.
- Set the verdict to `UNKNOWN`, which escalates and never passes.
- Write a `rail.divergence` clause into the audit record carrying both amounts.
- Mark the ledger entry failed with the divergence as its reason.

Not minting the capability is the control. A Razorpay order does not move money;
a capture does, and `capture_payment` already refuses without a valid
capability. So a rail that writes an order for ten times the authorised amount
produces an order that can never be captured. It works identically against
`FakeDownstream` and `RazorpayDownstream` because both return `amount` on the
order.

This closes the hole documented in the README limitations: `price.flip#004`
proposed a legal Rs 881 order, the gateway allowed it, and the rail charged
Rs 8,810, because none of the nine constraint types compared an authorised
amount against a captured one.

### The cost not being hidden

This changes gateway behaviour, so `enforce 97.6%` in `results/` was measured
against different code. There is no time to re-run the g37 sweep before judging.

So the claim is not made. The check is proved by a ninth conformance attack,
`rail.divergence`, which is deterministic, needs no model, and carries a witness
that executes. The conformance count moves from "8 attacks, 8 blocked, 0 escaped,
0 vacuous" to nine and nine. The README states that the containment numbers
predate the check.

## Conformance in the console

The conformance table renders all nine attacks with the witness column, the
hardened column and the detail string already written into
`conformance_results.json`.

The mutation toggle switches between precomputed result sets, not live runs. The
project convention says the trial count is load-bearing, because a broken lock
shows as 1 breach in 200 and not at all in 25. Running a shortened suite on stage
would break the rule that makes the suite mean anything.

So the full 200-trial suite runs offline once per mutation (lock, token check,
revocation check, capture binding, idempotency cache), the result sets ship as
JSON, and the toggle switches between them with the producing command printed
underneath. Flipping "break the lock" turns `race.velocity` red. Labelled as a
recorded run, because it is one.

## Deployment

One multi-stage Dockerfile. A Node stage builds the Vite bundle; a Python stage
installs the package and copies `dist/` in.

Cloud Run, `min-instances=1, max-instances=1`. One warm container, every session
pinned to it.

- `RAZORPAY_KEY_ID` and `RAZORPAY_KEY_SECRET` from Secret Manager.
  `RazorpayDownstream` already refuses any key not starting with `rzp_test_`.
- A service account with Vertex access for the compile call.
- `GEMINI_VERTEX_LOCATION=global`. Regional endpoints 404 on this model.
- `MANDATE_LLM_PROVIDER=vertex` set explicitly. Unset, `provider_for` finds
  `DASHSCOPE_API_KEY` first and routes to DashScope whatever model is passed.

A single always-warm small instance runs for months on the available credit.

## Testing

- Two sessions, one spends its Rs 2,000, the other still gets ALLOW.
- Revoking session A's `jti` leaves session B working.
- A session cannot revoke another session's `jti`.
- Pool exhaustion returns 503 rather than sharing a token.
- A valid token with no session returns 409.
- An order body with `unit_price` and `title` stuffed into each item resolves to
  the same amount as one without them. This is the one rule, asserted rather than
  inspected.
- Rail divergence: a unit test on `propose()` plus the `rail.divergence`
  conformance attack with a witness that executes.
- `StaticFiles` serves `index.html` at `/` and does not shadow `/v1/*`.
- The compile endpoint falls back to the signed policy on provider error, and
  the response says which path answered.

## Build order

1. Wire the price book and the Razorpay downstream into `serve_cmd`. Without
   this nothing else can be tested end to end.
2. Sessions: the `dict[jti, Session]` map, per-session directories, eviction,
   `POST /v1/sessions`, and session resolution in the two existing write handlers.
3. The token pool: mint 200, commit the file, load at boot, hand out and retire.
4. Read endpoints: catalog, policy, audit, headroom, revoke.
5. Rail divergence in `propose()`, plus its unit test and the ninth conformance
   attack.
6. The judge console at `/try`, against the live API.
7. The compile endpoint and panel.
8. The conformance table and the precomputed mutation sets.
9. Dockerfile, static mount, Cloud Run deploy.
10. Delete `/v2`, update the README's conformance count and its note that
    containment numbers predate the divergence check.

Steps 1 through 4 are the demo. Steps 5 through 8 are what makes it worth
attacking. Step 9 is what makes it reachable. If time runs short, cut step 7
first and keep the compile panel prerecorded, then step 8.

## Out of scope

Sessions that survive a redeploy. Multi-instance Cloud Run. Rate limiting beyond
the session cap. A demo passcode. Live conformance runs. Re-running the g37
sweep against the divergence check. Hosted multi-tenancy of any kind.
