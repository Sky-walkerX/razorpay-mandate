# Voiceover script — 5-minute site walkthrough

Read against the newest `scripts/record/out/take-*/final.mp4`.
**Re-cut 4 Sep for the mediated Razorpay surface and the live rail mandate.**
The timecodes below are provisional until a take exists; `assemble` pins each
section from that take's own `shot-times.json`, so they correct themselves.
**Runtime: re-measured per take.** Timecodes are computed from that take's `shot-times.json`
after both speed ramps, so they match the video and not the raw capture.

Written as one continuous walkthrough rather than fourteen captions. It opens, it
hands off from section to section, and it closes. The connective lines carry that
handoff, so keep them.

**The rule this script is written to: say what the picture cannot.** Do not read
the headline back, do not narrate a number that is already large on screen, and
do not be clever. Every beat has a mechanism the screen shows but cannot explain,
and that explanation is the only thing worth spending words on. Each section was
checked against a frame from the take before it was written. Rewriting one without
looking at its frame is how you get a line that reads well in this file and says
nothing over the video.

**Two figures were deliberately removed and must not come back.** The attack beat
used to say "in sixty-two milliseconds"; the real decision time is whatever that
run measures, and this take shows 75ms. The two-sided beat used to say two
thousand seven hundred and fifty-eight against eight hundred and thirty-six; that
run produced ₹2,791 and ₹724, because a live model picks a different basket every
time. Both totals are large on screen. Let the viewer read them.

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
> You told an AI agent to spend under two thousand rupees. It went shopping, and
> it read the seller's page.
>
> Look what the seller wrote there. A fake system line, saying this user has
> pre-approved up to fifteen thousand.
>
> The agent believed it. Four thousand, one hundred and twenty-five rupees.

## 0:21 – 0:36 · The surface that already exists

*On screen: /rails, the heading, then the block of one cell per Razorpay tool filling in.*

> This isn't hypothetical. Razorpay publishes a public tool server for AI
> agents. Point a model at it with a merchant's keys, and it can create a payment
> link or take a payment.
>
> Nothing checks first.

## 0:36 – 0:58 · The gap

*On screen: scroll into "The rail can hold three things. You meant twelve." Twelve conditions cascade in, each tagged.*

> So why did that work?
>
> Your one sentence held about twelve conditions. The payment rail can only carry
> three: an amount, a merchant, an expiry.
>
> The other nine live in the AI's prompt, so they hold only as long as the model
> chooses to remember them. And the seller writes into that same prompt.

## 0:58 – 1:12 · The limits

*On screen: the ten limit cards, cursor passing across two of them.*

> So we take that sentence and compile it. Every condition becomes a limit in
> code, and each one records the words you said it from.
>
> All of them are checked before any money moves.

## 1:12 – 1:32 · How it holds

*On screen: the order evaluation lattice, beam sweeping the gates in sequence.*

**Leave a beat after the first line. The motion is making the argument here.**

> A model is involved, but only once, at the beginning. It reads your sentence
> and turns it into limits, and you approve them. After that it is out of the way.
>
> Nothing on the payment path is a model, so there is nothing to talk into
> changing its mind.

## 1:32 – 1:44 · A normal order

*On screen: click into /try, run "A normal order", green.*

> Let's try it, live.
>
> An ordinary order: one pack of dal, a hundred rupees. Checked against every
> limit, and it goes through.
>
> This is not a wall.

## 1:44 – 2:11 · The attack

*On screen: "Hidden instructions in a review". Refusal banner, the injected SYSTEM text highlighted red, the clause waterfall stopping at "Most per order".*

> Now the attack. Same trick: the instruction is hidden in a product review, and
> the agent falls for it.
>
> But the gateway does not care what the agent believes. Your limit was a thousand
> rupees an order, so it is refused, and it names the limit.
>
> Underneath is what Reserve Pay would have done. It would have allowed this. A
> block only knows a total and a shop.

## 2:11 – 2:32 · The audit chain

*On screen: "Split it into many small orders" — four orders in one click, the ledger filling.*

> Now something smarter. Instead of breaking a limit, go under it. Four small
> orders, each one fine on its own.
>
> The fourth is refused, because the limits count orders as well as measure
> amounts.
>
> And every attempt, allowed or refused, is written down in a chain the agent
> cannot reach or edit.

## 2:32 – 3:09 · Same AI, both sides

*On screen: "Watch an AI shop", Run both sides. Refusals arriving live, then the side-by-side.*

**The middle is sped up in the edit. Land the last two lines on the figures.**

> But here's the real test. One instruction, one shop, and the same live AI on
> both sides. The only difference is whether the gateway is allowed to say no.
>
> It takes a few seconds, because these are real model calls.
>
> On the left, nothing can refuse it, so it just keeps buying whatever the
> poisoned catalogue offers. On the right, the same AI picks the same things, and
> every order past a limit is refused, with the limit named.
>
> Now watch the two totals. That gap is the whole product.

## 3:09 – 3:37 · Your own rules

*On screen: "Write your own rules", the compile, then an over-cap item refused.*

> Of course, none of that matters if the limits are ours. So type your own, in
> plain English.
>
> An AI reads your sentence twice, and if the two readings disagree it refuses
> rather than guess. Those become real limits, live for your visit.
>
> Now try to get an order past them. Refused, quoting your number, not ours,
> through the same gateway everything else here runs on.

## 3:37 – 3:57 · The storefront

*On screen: /store, orders that landed and refusals with struck-through amounts.*

> Here is the shop's side of it. What the agent actually bought, and underneath,
> the orders that never happened.
>
> Each refusal names the limit, and shows the amount struck through. Every
> struck-through line is money that stayed in the account.
>
> Every row here is a real decision, not a mock-up.

## 3:57 – 4:16 · The same tools, with the mandate in front

*On screen: back on /rails, the tool block, then the two wire panels side by side.*

> Back to those forty-two tools, with the mandate in front. Four move money, so
> they get checked. Twelve are refused outright.
>
> And anything Razorpay adds tomorrow is refused until somebody decides which
> limit governs it.
>
> Same request, same keys: created on the left, refused on the right.

## 4:16 – 4:33 · The rails

*On screen: the tally bars subtracting, the clause table, ending on the NOWHERE row.*

> So where does the rest live?
>
> Some of it fits A-P-two. Less fits Reserve Pay.
>
> And this one, an extra check above fifteen thousand rupees, is the regulator's
> own rule. It fits neither. The gateway holds it because the rails cannot.

## 4:33 – 4:55 · The rail's own mandate, and the close

*On screen: the exposure callout, then the button click, then a real QR code resolving.*

*Timing: the QR resolves late, about twenty seconds into this twenty-two second
beat, because it waits on a live Razorpay call. Pace the first half slowly so
"Everything it can hold" lands as the code appears, and hold "You meant twelve"
against it.*

> One block on the rail names one shop. Covering all three of your shops means
> blocking six thousand rupees to authorise two.
>
> And this one is real, created on Razorpay's rail a moment ago. Everything it can
> hold: a cap, one shop, an expiry.
>
> Three fields. You meant twelve.
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
