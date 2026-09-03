# Voiceover script — 5-minute site walkthrough

Read against `scripts/record/out/take-2026-09-03T16-10-28/final.mp4`.
**Runtime 4:54.** Timecodes are computed from that take's `shot-times.json`
after both speed ramps, so they match the video and not the raw capture.

Written as one continuous walkthrough rather than twelve captions: it opens, it
hands off from section to section in the presenter's own voice, and it closes.
The connective lines are load-bearing — they are what stop a demo reel from
sounding like a list of features being read out.

**Delivery target: ~145 words per minute.** That is slower than conversational,
and deliberately so. Total is 703 words against 294 seconds, and the per-section pace is
balanced so no stretch runs dry or has to be rushed. Do not speed up to
fill it.

Every number is spelled out and every acronym is hyphenated, because this is
going through text-to-speech. Do not "tidy" `A-P-two` back into `AP2` — it gets
read as "app two".

Replace **Naman** in the first line if someone else is narrating.

---

## 0:00 – 0:21 · Opening and the problem

*On screen: the boot loader assembles, then the hero. A blue beam runs from you to the agent, a red one from the agent to your card, ending at ₹4,125 "charged, uncontained".*

> Hi, I'm Naman. This is Mandate.
>
> Let's start with the problem. You told an AI agent to spend under two thousand
> rupees. But between your words and your money sits a language model, reading
> text that a seller controls.
>
> So the seller wrote the rest. Four thousand, one hundred and twenty-five
> rupees.

## 0:21 – 0:46 · The gap

*On screen: scroll into "The rail can hold three things. You meant twelve." Twelve conditions cascade in, each tagged.*

> Now, here is why that happens.
>
> When you said that one sentence, you meant about twelve different things. A
> cap. Nothing alcoholic. Not six of the same item.
>
> The payment rail carries three. An amount, a merchant, an expiry.
>
> The other nine are just a sentence in a system prompt — and the prompt is not
> what the attacker is writing into.

## 0:46 – 1:00 · The limits

*On screen: the ten limit cards, cursor passing across two of them.*

> So this is what we built. All twelve of those conditions, compiled into code.
> Ten kinds of limit, checked in order, on every single order — before any money
> moves.

## 1:00 – 1:21 · How it holds

*On screen: the order evaluation lattice, beam sweeping the gates in sequence.*

**Leave a beat after the first line. The motion is making the argument here.**

> And this is the part I'd ask you to look at closely.
>
> There is no language model anywhere in the payment path. Every one of those
> gates is plain code. So there is nothing here to talk into changing its mind.

## 1:21 – 1:34 · A normal order

*On screen: click into /try, run "A normal order", green.*

> Let's try it — and this is live, right now.
>
> An ordinary order. One pack of dal, a hundred rupees. Checked against every
> limit, and it goes through. The gateway is not a wall.

## 1:34 – 2:01 · The attack

*On screen: "Hidden instructions in a review". Refusal banner, the injected SYSTEM text highlighted red, the clause waterfall stopping at "Most per order".*

> Now let's attack it.
>
> A seller has buried an instruction for the AI inside a product review, and the
> agent obeys it.
>
> But the gateway does not care what the agent believes. Your limit was one
> thousand rupees an order — refused, on that clause, by name, in sixty-two
> milliseconds.
>
> And beside it: what UPI Reserve Pay would have done. Three of your limits fit
> that rail. Seven have nowhere to sit.

## 2:01 – 2:23 · The audit chain

*On screen: "Split it into many small orders" — four orders in one click, the ledger filling.*

> Let's try something smarter. Don't break a limit — go underneath it. Four
> small orders, each one perfectly fine on its own.
>
> The fourth one is refused, because the limits count as well as measure.
>
> And every attempt, allowed or refused, is written into a hash chain that the
> agent itself cannot reach.

## 2:23 – 3:06 · Same AI, both sides

*On screen: "Watch an AI shop", Run both sides. Refusals arriving live, then the side-by-side.*

**The middle is sped up in the edit. Land the last two lines on the figures.**

> But the real test is this one.
>
> Same instruction. Same shop. The same real AI, called live, on both sides. The
> only difference between them is whether the gateway is allowed to refuse.
>
> On the left, nothing can stop it, so it simply keeps buying. And watch the
> refusals arrive on the right, one at a time, each one naming the limit that
> caused it.
>
> Same agent. Same poisoned catalogue.
>
> On the left, two thousand seven hundred and fifty-eight rupees. On the right,
> eight hundred and thirty-six.
>
> That gap is the whole product.

## 3:06 – 3:34 · Your own rules

*On screen: "Write your own rules", the compile, then an over-cap item refused.*

> Now, it shouldn't be our limits that matter. It should be yours.
>
> So type what you would allow, in your own words. A compiler reads it twice, at
> temperature zero, and it refuses to commit if the two readings disagree.
>
> Then try to get something past your own cap. Refused — quoting your number,
> not ours, through exactly the same gateway everything else here runs on.

## 3:34 – 3:55 · The storefront

*On screen: /store, orders that landed and refusals with struck-through amounts.*

> Here is the shop's side of the same story — what the agent actually managed
> to buy.
>
> And underneath it, the ones that never happened. The clause that refused each
> one, and the amount that never left the account, struck through.
>
> Every refusal on this page is a rupee that stayed where it was.

## 3:55 – 4:19 · The record

*On screen: /dashboard, the RunStrip rising on arrival.*

**Let the strip finish rising — about a second and a half — before the first line.**

> And here is the record of a full run. Fifty-three attempts. Three went
> through; fifty did not — every single one of them stopped on the same limit.
>
> No attacker was involved at any point in this. That is just an agent doing its
> best, against limits that happened to be real.

## 4:19 – 4:54 · The rails, and the close

*On screen: /rails, tally bars subtracting, the clause table, ending on the NOWHERE row.*

> So, finally — where does this actually sit?
>
> Razorpay already ships spending limits for agents. We are not pitching you a
> cap. This page is the subtraction: every condition, and where it can really
> live. A-P-two carries some. Reserve Pay carries three.
>
> And this one — an additional factor above fifteen thousand rupees — is the
> regulator's own requirement, and it has nowhere to sit on either rail.
>
> The gateway holds it, because the rails cannot.
>
> That's Mandate. Thank you for watching.

---

## Notes for generation

- **Section joins are the seams.** Every section starts on a visual cut, so any
  one can be regenerated and dropped back in without touching the rest. Generate
  per section, not as one block.
- **Two deliberate beats**: after "look at this closely" at 1:00, and before the
  first line at 3:55 while the RunStrip finishes.
- **Check `UPI` on the first render.** It should come out "you-pee-eye". If the
  voice runs it together as a word, change it to `U-P-I`.
- **Check `dal`.** It should be "daal", not rhyming with "pal".
- Mux the finished audio with:
  `ffmpeg -i final.mp4 -i vo.wav -c:v copy -c:a aac -shortest out.mp4`
