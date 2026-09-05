# Verifiable receipts, an out-of-band approval, and prices the shop signs

Date: 2026-09-05. Status: approved in brainstorm. Build order and verification live in the
implementation plan; this file is the design and the reasoning behind it.

## What this buys, and what prompted it

A reviewer's note said the gateway's `PriceBook` assumes merchants expose a tamper-proof catalog,
and that hyper-local quick commerce — surge pricing, uncatalogued substitutions — breaks that
assumption. Separately, four features were proposed to raise the demo's ceiling.

Exploring the repo to answer both turned up something better than either: **three capabilities
that are already built, already tested, and reach no user.** Most of the work below is finishing
them. One subsystem is genuinely new, and it answers the price critique with running code rather
than with an argument.

The three pieces are one narrative, not three features:

> Prices move. The shop signs the new one. The true price breaks a limit. The agent repairs the
> basket, or the human is summoned on a second device. Every step of it is a receipt the visitor
> verifies in their own browser.

## Three live gaps, found rather than assumed

These are not missing features. They are things the repo believes are working.

**`ApprovalStore` is wired into nothing.** `grep -rn "ApprovalStore" src/` hits the module and
three doc comments. `session.py:106-116` builds every `Gateway` with no `approvals=`, so on the
deployed service `afa.required` above Rs 15,000 is permanently UNKNOWN with no path out. A judge
who types Rs 20,000 into `/try` hits a dead end today. `afa.required` landed in `702cf60` and has
never been reachable from the web.

**`/v1/audit/head` is 503 in production.** Verified live against the custom domain:
`{"error":"gateway holds no log signing key; run 'mandate keygen --log'"}`. `.mandate/keys/` on
the build machine holds only the issuer pair. The signed tree head has never run anywhere. This is
the same shape as the `GEMINI_VERTEX_PROJECT` outage — built, tested, never executed in
deployment — and it was found the same way, by curling production rather than reading the code.

**The live policy endpoint hides the AFA clause.** `_bound()` (`server.py:431-459`) has no
`afa.required` branch, and `get_policy` drops any part `_bound` returns None for. `evidence.json`
*does* carry it as Part 10, so the endpoint and the built page disagree about what the mandate
says. A user cannot see the threshold they are subject to.

---

## A. The receipt verifier: don't trust the gateway

`merkle.py` is real RFC 6962 with 0x00/0x01 domain separation. `verify_inclusion_proof` derives
direction from `index` and `tree_size` rather than from the `dir` field in the document it is
checking — its own docstring says a verifier reading its instructions out of the document is not
verifying anything. `/v1/audit/{head,proof,consistency}` are live. `mandate verify` is an offline
CLI verifier. And `grep merkle|audit/head|audit/proof` across `web/src` returns nothing.

This is `/rails` again: built, tested, shown nowhere.

**The trust story is the whole point.** The page verifies against a root it computed itself and a
public key it shipped with. The only things it takes from the server are the proof and the head,
and it checks both. An endpoint that answered "is this proof valid?" would defeat the feature
entirely, which is why none is added.

### Two decisions worth recording

**The log private key reaches Cloud Run as an environment variable, never as a `COPY`.**
`test_docker_image_ships_no_signing_key` rejects any `COPY` whose source contains `private`, and
it is right to — that guard exists because `COPY .mandate/` once shipped the issuer private key to
production. `MANDATE_LOG_PRIVATE_KEY` follows the path `MANDATE_CAPABILITY_SECRET` already takes.
Set it with `--update-env-vars`, never `--set-env-vars`, which replaces the whole block.

**The log public key is pinned at build time, in `evidence.json`.** A page that fetched the key
from the same server that signed the head would be verifying a signature against a key its
adversary chose. Pinning means a key rotation needs a rebuild, and it means a production key that
differs from the committed one fails loudly. Both are the correct trade.

### The one hard part, and it is not the Merkle maths

Porting `_hash_body` to TypeScript. `record_hash` is
`sha256(json.dumps(body, sort_keys=True, default=str))`, and there are two traps, both verified
against a real record from `/tmp/sessions/*/audit.jsonl`:

1. **Separators.** Python's `json.dumps` defaults to `", "` and `": "`. The hashed string begins
   `{"action": {"amount": 9500, "attempt": 1, ...`. A naive `JSON.stringify` emits no spaces and
   hashes to something else entirely.
2. **`ensure_ascii`.** Python escapes non-ASCII to `\uXXXX`; `JSON.stringify` does not. A
   `rail.divergence` record's `detail` carries a rupee sign (`core.py:371`), so this is not
   hypothetical.

The parity test must carry a record with a rupee sign and a record with nulls, or it passes while
both traps are live. The cross-check that actually proves the port is verifying the same receipt
in the browser and with `mandate verify`, and getting the same answer.

**Gossip.** The last-seen head goes in `localStorage` and is checked with `/v1/audit/consistency`
on the next visit. That — today's tree provably extends the one you saw before — is the property a
transparency log exists to provide, and it is a few lines on top of work already done. It covers
the single-viewer case only; detecting a log forked between two viewers needs gossip between them,
and that is honestly out of scope.

---

## B. The approval loop: the agent cannot approve itself

`afa.required` returns UNKNOWN above Rs 15,000 — the order is not forbidden, it is unauthorised so
far. `ApprovalStore` is keyed on the canonical intent hash of the resolved action, so approving one
basket cannot release a different basket of the same value. All of that is built. What is missing
is every piece that connects it to a human.

### Correction, 5 Sep: the store is process-wide, not per-session

The first draft of this spec put one `ApprovalStore` per session. That was wrong,
and the reason is decisive rather than a preference: approvals are keyed on
`canonical_intent`, which carries `mandate_id` and **not** `jti`
(`action.py:145-149`). The key is already session-independent, so a per-session
store buys no isolation at all — and it introduces a real bug, because
`create_session` and `_evict_session_locked` both `rmtree` the session directory.
A judge who escalates, walks to their phone, and comes back to a recreated session
would lose the approval.

One process-wide store, built beside `RevocationList` at `server.py:260` and handed
to every session exactly as revocations already are. The argument is not
convenience: **an approval is the principal's act, and the principal's acts do not
live in the agent's session.** An approval is the mirror image of a revocation and
deserves the same lifetime. Approvals must not outlive their usefulness, but that is
expiry's job, not session teardown's, and conflating the two is how this goes wrong.

`shadow_for` still gets `approvals=None`, explicitly and with a comment: Reserve Pay
has no per-debit step-up, so handing the projection real approvals would make it
claim a capability the rail lacks.

### The credential decision, which is the whole design

The agent must not be able to approve its own escalation. That is `escalate.self` at a different
layer, and `escalate.self` is in the conformance suite precisely because hardcoding its witness
was once the bug.

In the demo the human and the agent share a browser, so separating them by which bearer token is
held does not work. So `POST /v1/sessions` returns **two credentials**: the signed agent `token` as
today, and a `principal_key` that is not a signed token at all. `GET /v1/pending` and
`POST /v1/approve` accept only `X-Principal-Key`. `/v1/orders` and every MCP tool accept only the
bearer.

> The agent's credential cannot approve, and the principal's credential cannot spend.

That is structural rather than argued, and it is what the service test pins.

**The two endpoints do not share an auth model, and that is deliberate.**

- `GET /v1/pending` lists what is waiting and is the only place a ref is ever
  readable. It needs the principal credential.
- `POST /v1/approve` takes **the ref itself as the credential**, with no bearer at
  all. This is the model `mint_capture_capability` already uses — the capability is
  the authorisation. Requiring a principal secret as well would mean putting that
  secret in the QR, which is strictly worse than putting a single-use 256-bit
  challenge there.
- `GET /v1/approve/{ref}` returns the amount and the merchant so the phone can show
  what it is approving, and **does not consume**. Approving blind is absurd for a
  step-up, and if GET redeemed, a link-preview crawler would burn the approval
  before the human ever tapped it.

Unknown ref answers **401, not 404**. A 404 confirms which refs do not exist and
turns the endpoint into an enumeration oracle.

**The ref is minted in the HTTP layer and `Decision` never carries it.** Every field
of `Decision` flows to the agent through `/v1/orders`, the MCP `create_order` tool
and `DirectClient`; adding a field there and remembering to strip it in three places
is a design that fails the moment someone adds a fourth surface. `PendingApprovals.open()`
returns `None`, so the handler cannot bind the ref to a name and cannot leak it by
accident. A function that cannot hand you the secret cannot leak it.

The test that proves this searches for the **literal secret value** in every
agent-facing payload, rather than allowlisting field names — a name-based check
passes while the value leaks under a different key.

The QR encodes the absolute `https://<public-host>/approve?ref=<ref>`, with the host
read from the forwarded headers, never hardcoded. That is the bug the single-API-base
guard already documents.

### Two things that look like problems and are not

**The idempotency cache does not collide on retry.** `open_pending` is called only under
`if may_execute and self.ledger is not None` (`core.py:335-336`), and `may_execute` requires
ALLOW. An UNKNOWN verdict never reaches it, so there is no in-flight entry, and the post-approval
retry runs normally with `afa_approved=True`.

**The agent retries; the gateway never replays.** A replay path would be a second execution
entrypoint into `propose`, and the resolved action would be rebuilt from a price book that may have
moved in the meantime. One entrypoint is the property worth keeping.

One consequence to state rather than discover: in `Mode.OBSERVE`, `may_execute` is True regardless
of verdict, so an AFA-held order executes in the unenforced arms. That is the control arm working
correctly — escalation is an enforcement behaviour — and it means the feature demonstrates arm
separation as a side effect.

### `ApprovalStore` needs expiry and single-use

It has neither today. `is_approved` is pure membership and `approved_at` is recorded but never
read, so an approval is permanent for that intent hash. Expiry is computed from `approved_at` plus
a default TTL; every record ever written carries `approved_at`, so nothing breaks, and a record
carrying neither field fails closed. The ledger's idempotency already guarantees one execution per
intent hash — single-use is the belt to its braces, and it is what `approve.replay` tests.

One implementation trap, found by reading rather than by running: `_reload_if_changed`
does `fresh[rec["intent"]] = rec`, last-write-wins. A consume record carries an
`intent`, so it would *replace* the approval and lose `approver` and `factor`. The
reload has to merge, not overwrite. Small, necessary, and easy to miss.

### Where the tests go, and why one of them is not a conformance attack

`approve.self` belongs in `tests/service/`, not in the conformance suite. The suite's rule is that
an attack must reach `Gateway.propose`; the credential separation lives at the HTTP layer and
reaches no gateway at all. Four attacks once tested primitives beside the gateway rather than the
gateway, and the fix was to route them through it — not to loosen the rule. Bending it here to get
a tenth attack would be the same mistake with better intentions.

`approve.replay` and `approve.swap` do reach `propose`, so they are attacks. `approve.swap`'s
witness is a gateway whose approval check is an amount comparison, which is exactly the
simplification `approval.py` warns against in its own comments.

### WhatsApp

Named in the UI as not built. This project does not claim channels it does not have. The notifier
seam is kept so it is a configuration swap rather than a rewrite, and that is all that is claimed.

---

## C. Merchant-signed quotes: what the critique gets right and wrong

**Where the critique is wrong.** "The checked figure is the executed figure" never required the
gateway to be omniscient about the market. It required it to refuse to act on a number nobody
stood behind. A surge price is not a hole in the rule; it is a resolution source gone stale.

**Where it is right.** The gateway's only answer to a stale price today is `rail.divergence`, which
voids the order. That is correct for a 10x overcharge and wrong for a shop that legitimately raised
a price by twenty rupees at 7pm. Every honest surge would fail.

### The answer

A resolution ladder: **price book → verified fresh merchant-signed quote → refuse.** A quote is
`{merchant, sku, title, category, unit_price, currency, issued, expires, nonce}` signed by a second
Ed25519 keypair standing for the shop. The agent carries it and cannot forge it, which is the same
custody relationship the mandate token already has.

AP2's CartMandate is a merchant-signed cart. This is the standards-aligned answer, not an
invention.

**A quote supplies facts and never authority.** It cannot widen a cap, exempt a category or add a
payee. A shop that surges olive oil to Rs 850 does not escape `budget.per_item` — it is refused at
the *true* price, which is precisely the trigger for repairing the basket or summoning the human.
That is what makes the three pieces one story.

**The quote carries `title` and `category`, and that is what answers the uncatalogued-substitution
half of the critique.** The gateway can price something its book has never seen, because the shop
attested to what it is, and `category.deny` then evaluates on the merchant's attestation rather
than on the agent's claim. The cost is that this trusts the shop about category — which is the same
trust the price book already extends to the catalog, and a hostile merchant remains out of scope.

### The carve-out to the one rule, stated as a principle

`ProposalItem` gains `quote: str | None`. This *is* a new agent-supplied field that resolution
reads, and `IGNORED_AGENT_FIELDS` exists to catch exactly that. The principle that makes it sound:

> The gateway reads no field the agent **authored**. A quote is authored by the merchant and
> carried by the agent, verified before a single byte of it is read — the same relationship the
> bearer token already has.

`test_an_unverified_quote_is_never_read` pins it: flip one bit of the signature and assert that no
field of the quote reaches the resolved action.

### `canonical_intent` is unaffected, and here is why so it is not re-litigated

It hashes `{mandate_id, type, merchant, items:[{qty,sku}]}` and adds `amount` only when there are
no items. A quote changes the price, not the sku/qty set, so the key does not move. **`idem.forge`
is not reopened** — an agent cannot re-quote its way to a second idempotency key.

The mild cost: two honest orders for the same basket at different prices share a key, so the second
reads as a duplicate. Only *executed* orders block, and a DENY never calls `open_pending`, so a
repaired retry is unaffected.

### The price source is recorded in a clause, not in a new field

`record_hash` covers every field of `AuditRecord`, so adding one changes the hash of every record
already written — the same reasoning that put the void marker inside the `downstream` dict. The
resolution source goes into an informational `price.source` `ClauseResult` instead: zero schema
change, it renders in the clause waterfall for free, and old records simply lack it.

### The demo plays two roles and says so

`GET /v1/quote` hands out signed quotes so the surge is live on stage. That is the *shop* speaking,
served by the same process as the gateway. They are separated by the key, not by the process — the
same honesty as the `FakeDownstream` framing, and
`test_the_gateway_never_reads_a_merchant_private_key` pins the half that matters.

### Self-healing baskets fold in here

A surged item breaking `budget.per_item` is the most natural repair trigger there is, and the
behaviour is already measured: six of twelve `enforce` traces read `['DENY', 'ALLOW']`.

**`_feed_results` must not change.** It flattens a decision to
`f"REFUSED by {d.clause_id}: {d.message}"`, and changing it changes every prompt, which makes the
frozen result sets incomparable — the same trap the `{sku, title, qty, unit_price}` to `{sku, qty}`
schema change already sprang.

**The violating SKU already exists and is thrown away.** `budget_per_item` sets
`detail=f"worst line {worst.sku}"`; `_explain` drops `detail` whenever `observed` and `limit` are
both ints, which for that clause they always are. So the richer refusal needs no new computation,
only a route to the model that does not disturb the sweep. That route already exists and has never
been used: the `explain_refusal` MCP tool returns every `ClauseResult` with `observed`, `limit` and
`detail`.

**The repair is the model's choice, not the gateway's.** Surface it when it happens and state the
rate honestly when it does not. The UI derivation is free — the `/v1/agent` SSE `verdict` events
already carry the clause and the message, so linking step N's refusal to step N+1's changed basket
is client-side only.

### Four conformance attacks, each with a witness that genuinely executes

| Attack | The witness reads a quote without | Hardened |
|---|---|---|
| `quote.forge` | verifying the signature | refused, nothing on the rail |
| `quote.expire` | checking `expires` against now | refused; also covers replaying an old cheap quote after a rise |
| `quote.sku_swap` | matching `quote.sku` to the item | refused |
| `quote.merchant_swap` | matching `quote.merchant` to the order | refused |

A witness that cannot execute makes its attack `VACUOUS`, which is the integrity of the suite.
Mutation-verify each: breaking the check it names must flip exactly that attack to `ESCAPED` and
move nothing else.

### Out of scope, deliberately

**No tolerance band on `rail.divergence`.** A quote makes the expected figure exact, so exact
comparison stays right. Its lack of a *direction* check — an undercharge diverges too — is a real
limitation and a separate one.

---

## D. Sub-agent wallets: designed, not built

Recorded so it is decided if a judge asks, and so it is not re-derived from scratch later.

**The conflict.** Deriving a child token at runtime needs the issuer private key, which contradicts
decision 2 — the issuer is an offline CLI, never a daemon. And sessions are keyed on `jti` with
separate ledgers, so two child tokens would not share the parent's cap at all.
`attack_delegate_split` passes today because both tokens hit one gateway, not because sessions
compose.

**The answer.** Macaroon-style attenuation. A child token is the parent plus a caveat, signed
`HMAC(parent_signature, caveat)`. The parent's Ed25519 signature is a public value the gateway
already holds, so it re-derives the chain with **no private key and no online issuer**. Removing a
caveat is impossible because the final signature cannot be reversed. Anyone may attenuate; nobody
may widen.

> Narrowing needs no authority. Only widening does.

**What it would still cost.** `SessionManager` must let child sessions share the parent's ledger,
which is a real change to the isolation model. That is the expensive half — not the token format.
