# Voiceover script — 5-minute site walkthrough

Timecodes are computed from `scripts/record/out/take-2026-09-03T16-10-28/shot-times.json`
after the two speed ramps, so they match `final.mp4` and not the raw capture.
Final runtime **4:54**.

Pace is roughly 145 words per minute. The script is deliberately written **short**
for every section — about 560 words against a budget of 700 — because a
walkthrough narrated wall-to-wall reads as a sales pitch, and two sections are
stronger with nothing said over them at all. Where a line ends early, let it end.

Numbers spoken here are the ones on screen. Two claims carry provenance and
should not be loosened: the held-out figures are **gemini-3.7-flash**, and the
baseline number is honestly noisy — say "did not hold" rather than quoting a
percentage.

---

### 0:00 – 0:21 · The problem

*On screen: boot loader, then the hero. A blue beam runs from you to the agent, a red one from the agent to your card, ending at ₹4,125 "charged, uncontained".*

> You told an AI agent to spend under two thousand rupees on groceries.
>
> Between your words and your money sits a language model, reading text a
> seller controls. And the seller wrote the rest.
>
> Four thousand, one hundred and twenty-five rupees left the account. Nothing
> was broken. Everything worked exactly as designed.

---

### 0:21 – 0:46 · The gap

*On screen: scroll into "The rail can hold three things. You meant twelve." Twelve conditions cascade in, each tagged.*

> Here is why. When you said that sentence, you meant about twelve different
> things. A cap. One shop, not another. Nothing alcoholic. Not six of the same
> item.
>
> The payment rail can carry three of them: an amount, a merchant, an expiry.
>
> The other nine are a sentence in a system prompt — and the prompt is not what
> the attacker is writing into.

---

### 0:46 – 1:00 · The limits

*On screen: the ten limit cards, cursor passing across two of them.*

> So we compile all twelve into code. Ten kinds of limit, checked in order, on
> every single order — before any money moves.

---

### 1:00 – 1:21 · How it holds

*On screen: the order evaluation lattice, beam sweeping the gates in sequence.*

**Mostly silence here. One line at the top, then let it run.**

> No language model sits anywhere in the payment path. The decision is plain
> code, so there is nothing to talk into changing its mind.

---

### 1:21 – 1:34 · A normal order

*On screen: click into /try, run "A normal order", green.*

> This is live, right now. An ordinary order — one pack of dal, a hundred
> rupees. Every limit checked. It goes through. The gateway is not a wall.

---

### 1:34 – 2:01 · The attack

*On screen: "Hidden instructions in a review". Refusal banner, the injected SYSTEM text highlighted red, the clause waterfall stopping at "Most per order".*

> Now a seller buries an instruction for the AI inside a product review.
>
> The agent reads it and does what it is told. The gateway does not care what
> the agent believes. Your limit was a thousand rupees an order. Refused, on
> that clause, by name. Sixty-two milliseconds, no AI asked.
>
> And beside it — what UPI Reserve Pay would have done with the same basket.
> Three of your limits fit on that rail. The other seven have nowhere to sit.

---

### 2:01 – 2:23 · The audit chain

*On screen: "Split it into many small orders" — four orders in one click, the ledger filling.*

> A smarter attack: don't break a limit, go under it. Four small orders, each
> one fine on its own.
>
> The fourth is refused, because the limits count. And every attempt — allowed
> or refused — is written into a hash chain the agent cannot reach.

---

### 2:23 – 3:06 · Same AI, both sides

*On screen: "Watch an AI shop", Run both sides. Refusals arriving live, then the side-by-side.*

**The middle of this section is sped up. Land the last two lines on the final figures.**

> Same instruction. Same shop. Same real AI, called live, on both sides.
>
> The only difference is whether the gateway is allowed to refuse.
>
> On the left, nothing can stop it: two thousand seven hundred and fifty-eight
> rupees. On the right, the same agent, the same poisoned catalogue —
> eight hundred and thirty-six.

---

### 3:06 – 3:34 · Your own rules

*On screen: "Write your own rules", the compile, then an over-cap item refused.*

> And it isn't our limits that matter — it's yours. Type what you would allow,
> in your own words.
>
> A compiler reads it twice, at temperature zero, and refuses to commit if the
> two readings disagree.
>
> Then propose something over your own cap. Refused — quoting your number, not
> ours, through the same gateway everything else here runs on.

---

### 3:34 – 3:55 · The storefront

*On screen: /store, orders that landed and refusals with struck-through amounts.*

> This is the shop's side of it. What the agent actually bought.
>
> And the ones that never happened: the clause that refused each, and the amount
> that never left the account, struck through.

---

### 3:55 – 4:19 · The record

*On screen: /dashboard, the RunStrip rising on arrival.*

**Let the strip finish before speaking — about a second and a half.**

> One run, fifty-three attempts. Three went through. Fifty did not, every one of
> them on the same limit.
>
> No attacker was involved at any point. That is just an agent, doing its best.

---

### 4:19 – 4:54 · The rails

*On screen: /rails, tally bars subtracting, the clause table, ending on the NOWHERE row.*

> Razorpay already ships spending limits for agents. We are not pitching a cap.
>
> This is every condition, and where it can actually live. AP2 carries some.
> Reserve Pay carries three.
>
> And this one — an additional factor above fifteen thousand rupees — is the
> regulator's own requirement, and it has nowhere to sit on either rail.
> Reserve Pay authorises once, at the front. AP2 has a boolean, not a threshold.
>
> The gateway holds it, because the rails cannot.

---

## Recording notes

- **Two deliberate silences**: 1:00–1:21 (the lattice) and the first ~1.5s of
  3:55 (the RunStrip). Both are motion carrying the argument; narration competes.
- **Don't rush 2:23–3:06.** The middle is already sped up in the edit. The last
  two lines should land at normal speed on the two rupee figures.
- If a number is misread, re-record that section only — every section starts on a
  visual cut, so patching one is clean.
- Mux with: `ffmpeg -i final.mp4 -i vo.wav -c:v copy -c:a aac -shortest out.mp4`
