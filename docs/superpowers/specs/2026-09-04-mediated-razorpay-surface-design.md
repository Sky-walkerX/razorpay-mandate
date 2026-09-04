# A mandate in front of Razorpay's own agent surface, and a rail mandate that is real

Date: 2026-09-04. Status: approved in brainstorm, implementing directly (no separate plan doc,
by request).

## What this buys

Two things, and they answer the same objection from opposite ends.

The objection is that Razorpay already ships spending limits for agents, so a project about
bounding an agent's spend is a worse version of a product the judges own. The existing answer is
`/rails`, which argues from a projection of the rail's published vocabulary. It is a good argument
made entirely out of prose this repo wrote.

**Feature 1 makes the problem concrete.** Razorpay publishes a remote MCP server at
`https://mcp.razorpay.com/mcp`. Verified live on 4 Sep against this project's own `rzp_test_`
keys: it serves **42 tools, 16 of them flagged `"destructiveHint": true`**, over HTTP Basic auth,
with no session handshake. `capture_payment`, `create_payment_link`, `initiate_payment`,
`revoke_token`, `create_qr_code` and eleven more. Point a model at that URL with a merchant's keys
and nothing sits between the model and the money. Mandate becomes that layer, mounted at
`/mcp/razorpay`, and the demo is two terminals side by side.

**Feature 2 makes the argument real.** `POST /v1/subscription_registration/auth_links` works in
test mode today, verified: it returned `inv_TXrF4WYm6ZLsUx` with a hosted `short_url` and, on the
order behind it, a genuine rail mandate object carrying
`{"max_amount":200000,"frequency":"as_presented","expire_at":1791000000,"method":"upi"}`. So
`/rails` can diff ten clauses against a rail object a judge scans on their phone, instead of
against a table this repo typed.

## Findings that motivated the work, all verified rather than assumed

**Razorpay's MCP server is stateless and wide open.** `tools/list` and `tools/call` both answer a
plain JSON-RPC POST with Basic auth. No `initialize`, no `mcp-session-id`. The upstream client is
about forty lines. `fetch_all_orders` returned this account's real orders on the first call.

**Reserve Pay proper is sales-gated, including in test mode.** The MCP `create_order` description
advertises mandate orders with `token.type = "single_block_multiple_debit"`. Creating one
succeeds and **silently drops the token spec**: `order_TXr8MgkvSCQ7oB` fetches back with no
`token` field at all. The S2S UPI path answers
`"The requested URL was not found on the server"`, which is how Razorpay says an endpoint is not
enabled on this account. Nothing in this repo can produce a live Reserve Pay block, and the demo
must not imply otherwise.

**The deployed gateway has never placed a real order.** Cloud Run carries exactly four env vars:
`MANDATE_CAPABILITY_SECRET`, `MANDATE_LLM_PROVIDER`, `GEMINI_VERTEX_LOCATION`,
`GEMINI_VERTEX_PROJECT`. No `RAZORPAY_KEY_*`, so `create_app` falls to `FakeDownstream` at
`server.py:238`.

**The MCP walk-up path is an open door once the rail is real.** `server.py:1084` keys the session
map on `headers.get("mcp-session-id") or "_walkup"`, so a client with no bearer token gets a
session. Against `FakeDownstream` that is a good demo and CLAUDE.md records it as a success.
Against real keys on a public URL it is unauthenticated access to a merchant account.

**The Reserve Pay shadow cannot currently show the disagreement it exists to show.**
`project_to_reserve_pay` narrows `merchant.allow` to `payees[0]` (`rails.py:216`), which is
`zepto`, while every attack preset in `JudgeConsole.tsx` orders from `blinkit`. So the shadow
refuses all of them on payee and the `railWorse` branch never fires. Already logged as open item 1
in CLAUDE.md.

## Feature 1: `/mcp/razorpay`

### A second surface, not an extension of the first

`/mcp` keeps its six tools, its storefront, its price-book resolution and its walk-up. The pitch
video already uses it. The proxy mounts separately at `/mcp/razorpay` with its own builder and its
own enumeration test, because one surface that means two things is how the `GEMINI_MODEL` drift
happened.

### `RazorpayMCPUpstream`

New module `src/mandate/adapters/razorpay_upstream.py`. Two methods, `list_tools()` and
`call_tool(name, args)`, both plain POSTs to `https://mcp.razorpay.com/mcp` with Basic auth. It
asserts `rzp_test_` at construction, the same guard `RazorpayDownstream` already carries, so the
proxy cannot be pointed at live keys by accident.

### Four sets, and an unclassified tool fails closed

| Set | Tools | Behaviour |
|---|---|---|
| `BOUND` | `create_order`, `create_payment_link`, `payment_link_upi_create`, `capture_payment` | the checked amount is the forwarded amount |
| `REFUSED` | the other 12 destructive | denied; the clause names why the mandate does not cover it |
| `PASSTHROUGH` | the 26 read-only | forwarded unchecked; no money moves |
| unclassified | anything Razorpay ships later | refused, and the classification test goes red |

The last row is the load-bearing one. A proxy that forwards a seventeenth destructive tool because
nobody updated a list is the exact bug this project exists to prevent, so the test enumerates the
live upstream surface against the classification and fails on any name it has not been told about.

`create_order` is `BOUND` here and resolved at `/mcp`. That is not an inconsistency: Razorpay's
`create_order` takes a raw amount and has no catalog behind it, while the storefront's takes SKUs.
Two surfaces, two meanings, and the docstring says so.

### Bind-and-forward is an identity resolution, not an exception

The convention in CLAUDE.md reads "no constraint may read a field the agent supplied", and this
work amends it to **"the checked figure is the executed figure"**, with resolution as how you get
there when a catalog exists and identity resolution when it does not.

The reasoning, so it is not re-litigated. The original bug was that the agent's lie was both
checked and executed: it declared a paise for a Rs 500 item, the cap passed against a fiction, and
the rail charged the fiction. On a raw call there is no truth to compute, because the request *is*
the action. Lying low moves less money. Lying high is refused. What must hold is that the number
the constraints saw is the number that reaches Razorpay.

That is made structural rather than promised:

- A new `RawProposal` type in `gateway/action.py` carries `{type, tool, amount, merchant}`.
  `Proposal` is untouched, so the `IGNORED_AGENT_FIELDS` machinery and the invariance property
  keep meaning what they mean.
- `Gateway._resolve_raw_to_action()` reads `prop.amount` exactly once and writes it to
  `ResolvedAction.amount`. `items` is `[]`.
- The forwarder rebuilds the upstream arguments from `action.amount`. The agent's original
  argument dict is discarded after resolution and never read again.
- `canonical_intent()` still hashes the resolved action, so `idem.forge` stays dead. The
  invariance test extends: two raw proposals differing in anything but tool and amount must hash
  identically.

`ResolvedAction` needs no schema change. It already permits `items: []`, and `ActionType` already
carries `CREATE_PAYMENT_LINK` and `CAPTURE_PAYMENT`.

### Five of ten limits are evaluable on a raw call, and the response says so

`budget.total`, `budget.per_transaction`, `velocity`, `time.window` and `afa.required` read the
amount, the clock or the accumulators, so they apply. `budget.per_item`, `category.deny`,
`quantity.max_per_item`, `merchant.allow` and `item.deny_recent` have no line items and no payee
to read.

The evaluators are **not** changed. `budget_per_item` already returns ALLOW with
`detail="no line items to check"`, and `combine` and `lattice.py` stay untouched. What changes is
reporting: a derived `inapplicable_clauses(action)` marks those five, and the proxy's response and
the UI say "5 evaluated, 5 not applicable to this tool" rather than painting ten clauses green.
Ten green on five evaluations is the VACUOUS bug at a different layer, and this project has
already shipped that bug twice.

**No field is added to `AuditRecord`.** `record_hash` covers every field, so a new one changes the
hash of every record already written and breaks every existing chain. Applicability is derived
from the action at report time, which is what this repo prefers anyway.

### The walk-up closes on this surface

`/mcp/razorpay` requires a pooled bearer token. `/mcp` keeps its walk-up, because a fake rail
behind it makes that a feature rather than a hole.

### Tests

- Every `BOUND` tool reaches `Gateway.propose`; breaking `propose` stops the upstream call.
- The classification is exhaustive against the live upstream tool list, and an unknown tool is
  refused.
- The forwarded amount equals `action.amount`, and mutating the agent's dict after the check does
  not change what is forwarded.
- No upstream call happens on DENY.
- Unit tests drive a fake upstream. One live smoke test is opt-in behind an env var, because the
  suite must not need network or keys.

## Feature 2: the rail mandate, real

### One block per payee, built lazily

`project_to_reserve_pay(policy)` gains an optional `payee`. The session holds
`shadows: dict[payee, Gateway]` instead of one `shadow`, built on first use for the payee being
proposed against. This fixes the demo bug and produces a finding on its own: a user shopping at
three shops sets up three blocks, so the rail's total exposure is three times the block, not one.
`money_at_risk` gets larger, not smaller.

### The auth link, created from the policy

`max_amount` from `budget.total`, `expire_at` from `policy.expires`, `frequency: as_presented`,
`notes.mandate_id` from the policy. Rendered on `/rails` as a QR beside the clause table, so a
judge opens the real `rzp.io` link on their phone and reads the rail's own mandate next to this
one.

### It is UPI Autopay, and the page says so

Same vocabulary as Reserve Pay, different product, and someone from Razorpay will know the
difference. It gets its own column rather than being folded into `RESERVE_PAY_CARRIES`.

One correction falls out and it sharpens the argument. UPI Autopay carries a `frequency` field
that Reserve Pay lacks, which is tempting to score as a fourth held clause. But `as_presented`
bounds nothing, and `daily` means one debit per day rather than three per mandate. It is
`partial` in the four-status vocabulary `regulatory.py` already uses, and saying that is stronger
than claiming either three or four.

## UI

Both features surface on screens a judge uses, so they follow the visual system recorded in
CLAUDE.md rather than inventing a third page frame: document frame at `max-w-[1100px]` with
`px-8 max-sm:px-[18px]` for `/rails`, the existing app bleed for `/try`, `h-[60px]` nav, and the
five-token radius vocabulary. No arbitrary `rounded-[Npx]`. Measured at 390px for zero horizontal
overflow, because two defects in the last pass were invisible by eye and obvious in
`getBoundingClientRect`.

The proxy needs a screen that makes "42 tools, 16 destructive, 4 allowed" legible at projector
distance in one glance. That is the shot the pitch is built around.

## Deployment

`gcloud run services update mandate-gateway --region asia-south1 --update-env-vars
RAZORPAY_KEY_ID=...,RAZORPAY_KEY_SECRET=...`, then the six-step verification pass on the custom
domain. Never `--set-env-vars`: `MANDATE_CAPABILITY_SECRET` exists only in the deployed service
and would go with it.

## Out of scope

Reserve Pay's real SBMD block, which is gated. Webhook reconciliation, which closes a real hole
and is invisible on stage. Scoping the 26 read-only tools, which can read account-wide payment
history and is recorded below as a known limitation rather than fixed.

## Known limitations, stated rather than discovered

- The `PASSTHROUGH` set includes `fetch_all_payments`, `fetch_all_orders` and
  `fetch_settlement_recon_details`, which return account-wide data. The mandate bounds money
  movement, not reads. Worth saying before a judge finds it.
- `capture_payment` in `BOUND` needs a live authorized payment id to exercise, which is fiddly to
  stage. It is the first thing to cut if time runs short; `create_payment_link` makes the same
  point with a link you can put on screen.
- The live smoke test needs network and keys, so it is opt-in and the CI number excludes it.
