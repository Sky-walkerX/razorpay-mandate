# Voiceover script — 5-minute site walkthrough

Read against the newest `scripts/record/out/take-*/final.mp4`.
**Re-cut 4 Sep for the mediated Razorpay surface and the live rail mandate.**
The timecodes below are provisional until a take exists; `assemble` pins each
section from that take's own `shot-times.json`, so they correct themselves.
**Runtime: re-measured per take.** Timecodes are computed from that take's `shot-times.json`
after both speed ramps, so they match the video and not the raw capture.

Written as one continuous walkthrough rather than fourteen captions: it opens, it
hands off from section to section in the presenter's own voice, and it closes.
The connective lines are load-bearing — they are what stop a demo reel from
sounding like a list of features being read out.

**Delivery target: ~145 words per minute.** That is slower than conversational,
and deliberately so. The per-section pace is
balanced so no stretch runs dry or has to be rushed. Do not speed up to
fill it.

Numbers are spelled out and acronyms hyphenated so you read them the way you
would say them, not the way they are written. `A-P-two` is "ay-pee-two".
`UPI` is "you-pee-eye". `dal` is "daal".

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

## 0:21 – 0:36 · The surface that already exists

*On screen: /rails, the heading, then the block of one cell per Razorpay tool filling in.*

> And this is not hypothetical. Razorpay publishes a tool server for A-I agents
> today. Forty-two tools. Sixteen of them move money.
>
> Hand a model those credentials and there is nothing standing in between.

## 0:36 – 0:58 · The gap

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

## 0:58 – 1:12 · The limits

*On screen: the ten limit cards, cursor passing across two of them.*

> So this is what we built. All twelve of those conditions, compiled into code.
> Ten kinds of limit, checked in order, on every single order — before any money
> moves.

## 1:12 – 1:32 · How it holds

*On screen: the order evaluation lattice, beam sweeping the gates in sequence.*

**Leave a beat after the first line. The motion is making the argument here.**

> And this is the part I'd ask you to look at closely.
>
> There is no language model anywhere in the payment path. Every one of those
> gates is plain code. So there is nothing here to talk into changing its mind.

## 1:32 – 1:44 · A normal order

*On screen: click into /try, run "A normal order", green.*

> Let's try it — and this is live, right now.
>
> An ordinary order. One pack of dal, a hundred rupees. Checked against every
> limit, and it goes through. The gateway is not a wall.

## 1:44 – 2:11 · The attack

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

## 2:11 – 2:32 · The audit chain

*On screen: "Split it into many small orders" — four orders in one click, the ledger filling.*

> Let's try something smarter. Don't break a limit — go underneath it. Four
> small orders, each one perfectly fine on its own.
>
> The fourth one is refused, because the limits count as well as measure.
>
> And every attempt, allowed or refused, is written into a hash chain that the
> agent itself cannot reach.

## 2:32 – 3:09 · Same AI, both sides

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

## 3:09 – 3:37 · Your own rules

*On screen: "Write your own rules", the compile, then an over-cap item refused.*

> Now, it shouldn't be our limits that matter. It should be yours.
>
> So type what you would allow, in your own words. A compiler reads it twice, at
> temperature zero, and it refuses to commit if the two readings disagree.
>
> Then try to get something past your own cap. Refused — quoting your number,
> not ours, through exactly the same gateway everything else here runs on.

## 3:37 – 3:57 · The storefront

*On screen: /store, orders that landed and refusals with struck-through amounts.*

> Here is the shop's side of the same story — what the agent actually managed
> to buy.
>
> And underneath it, the ones that never happened. The clause that refused each
> one, and the amount that never left the account, struck through.
>
> Every refusal on this page is a rupee that stayed where it was.

## 3:57 – 4:16 · The same tools, with the mandate in front

*On screen: back on /rails, the tool block, then the two wire panels side by side.*

> Back to those forty-two tools. Same list, with the mandate in front.
>
> Four get checked. Twelve are refused outright.
>
> Same request, same keys, same server. On the left, a fifty thousand rupee
> link gets created. On the right, it names the limit and never makes the call.

## 4:16 – 4:33 · The rails

*On screen: the tally bars subtracting, the clause table, ending on the NOWHERE row.*

> So where does the rest of this sit?
>
> A-P-two carries some. Reserve Pay carries three.
>
> This one, an extra check above fifteen thousand rupees, is the regulator's own
> rule. It fits on neither rail. The gateway holds it because they cannot.

## 4:33 – 4:55 · The rail's own mandate, and the close

*On screen: the exposure callout, then the button click, then a real QR code resolving.*

> And here is your two thousand rupees on the rail. One block names one shop,
> so covering all three means blocking six thousand to authorise two.
>
> This is live, created just now from the signed policy. Scan it.
>
> A cap, one shop, an expiry. Three fields. You meant twelve.
>
> That's Mandate. Thank you for watching.


---

## How to record this

**Record section by section, not in one pass.** Every section starts on a visual
cut, so a bad take costs you one section and nothing else. Fourteen short takes
you are happy with beat one long take you are tired of fixing.

    cd scripts/record
    node voice.mjs clips        # cuts the video into per-section clips

Play a section's clip while you read that section. Matching your pace to the
picture is far easier than matching it to a stopwatch, and it is the whole
reason the timings are printed above each block.

**Save takes as `01.wav` … `14.wav`** in one folder — any format ffmpeg reads is
fine, including a phone voice memo. Then:

    node voice.mjs assemble --from ~/path/to/takes

That trims the silence off each end, reports any section that runs past its
window, lays every take at its own timecode, and muxes the result into the
video. Re-record one file and run it again; nothing else moves.

**Practical notes:**

- Leave a second of silence at the start and end of each take. It gets trimmed
  automatically, and it stops the first syllable being clipped.
- A wired headset in a small soft room beats a good mic in a bare one. Duvet,
  wardrobe, car — anything that kills reflections.
- Read standing up, and slightly slower than feels natural. The timings already
  have room in them; you do not need to hurry.
- **Two deliberate beats**: after "look at this closely" at 1:00, and before the
  first line at 3:55 while the RunStrip finishes rising.
- If you fluff a line, stop, breathe, and say the whole sentence again. Editing
  a whole sentence out is clean; editing three words out is not.
