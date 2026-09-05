import { motion, useReducedMotion } from 'motion/react';
import { Check } from 'lucide-react';
import { partByKey } from '@/data/policy';
import { cn } from '@/lib/utils';

/**
 * Section 05: what happens when the shop changes its price.
 *
 * Four things shipped and reached no screen: merchant-signed price changes, the
 * agent repairing its own basket after a refusal, the approval that lands on
 * another device, and the receipt a visitor checks in their own browser. They
 * are one sequence rather than four features, which is why this is one section
 * with four beats and not a feature grid.
 *
 * The beats are numbered because they are a real order in time. Beat 02 cannot
 * happen before 01 and 04 describes the record 02 and 03 wrote.
 *
 * Every bound is read from the signed policy through `partByKey`. The prices are
 * catalog illustration and are prose for the same reason `GapAndParts` writes
 * the dal prices in prose: they belong to the shop, not to the mandate.
 *
 * Placement is load-bearing. This section goes *after* the last anchor the
 * recorded walkthrough scrolls to, because those shots take pixel offsets from
 * their anchors and a section inserted between them re-frames every later shot.
 */

const PER_ITEM = partByKey('budget.per_item');
const AFA = partByKey('afa.required');

/** The shop's own figures. Catalog illustration, not policy. */
const LIST = '₹203.00';
const SIGNED = '₹345.10';
const SURGE = '1.7×';
const AT_LIST = '₹406.00';
const AT_SIGNED = '₹690.20';
const REPAIRED = '₹431.00';

interface Beat {
  n: string;
  title: string;
  body: string;
}

const BEATS: Beat[] = [
  {
    n: '01',
    title: 'The shop signs its new price',
    body: 'A price change arrives signed by the shop, not claimed by the agent. Tied to one product, good for ten minutes.',
  },
  {
    n: '02',
    title: 'The real price meets your limit',
    body: 'Same basket, twice. At the shelf price it passes. At the signed price it does not, and the refusal names the figure that would really have been charged.',
  },
  {
    n: '03',
    title: 'The agent fixes its own basket',
    body: 'It is told which limit stopped it and nothing else. It shops again, within the limit, without anyone stepping in.',
  },
  {
    n: '04',
    title: 'You check the receipt yourself',
    body: 'Every decision is written into a sealed record. Your browser proves this one is in it, and that nothing earlier was changed.',
  },
];

/** A verdict pill. The three words and the three inks never come apart. */
function Pill({ tone, children }: { tone: 'pass' | 'halt' | 'refer'; children: string }) {
  return (
    <span
      className={cn(
        'rounded-full border px-[7px] py-[3px] font-mono text-[9px] font-semibold tracking-[0.09em]',
        tone === 'pass' && 'border-pass-line bg-pass-soft text-pass',
        tone === 'halt' && 'border-halt-line bg-halt-soft text-halt',
        tone === 'refer' && 'border-refer-line bg-refer-soft text-refer',
      )}
    >
      {children}
    </span>
  );
}

function Tick({ children }: { children: string }) {
  return (
    <div className="flex items-center gap-2 border-b border-hair px-[11px] py-[9px] last:border-b-0">
      <Check className="size-3 flex-shrink-0 text-pass" strokeWidth={2.4} />
      <span className="text-[11.5px] text-ink-2">{children}</span>
    </div>
  );
}

export default function WhenPriceMoves() {
  const reduced = useReducedMotion() ?? false;

  return (
    <section id="price" className="border-b border-rule bg-bond">
      <div className="mx-auto max-w-[1220px] px-8 py-[76px] max-sm:px-[18px] max-md:py-14">
        <span className="inline-flex items-center gap-2 rounded-full border border-rule bg-bond px-[13px] py-[6px] font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
          <span className="size-[5px] rounded-full bg-refer" />
          05 · when the price moves
        </span>

        <h2 className="mt-[18px] max-w-[18ch] text-balance text-[clamp(1.7rem,3vw,2.3rem)] font-semibold leading-[1.06] tracking-[-0.046em]">
          The shop can change its mind.{' '}
          <span className="text-ink-3">Your limits still hold.</span>
        </h2>

        <p className="mt-[16px] max-w-[33rem] text-[16px] leading-[1.62] text-ink-2">
          A catalog is not a promise. Prices move between the moment you say what you want and
          the moment an agent acts on it, and an agent simply told the new price has no way to
          prove it. So the shop signs for it.
        </p>

        {/*
          Four columns sharing one row track, so the number, title, body and panel
          each start at the same height in every column however long the copy runs.
          `subgrid` does that without a hand-tuned min-height that goes stale the
          moment a sentence changes.
        */}
        <div className="mt-[38px] grid overflow-hidden rounded-panel border border-rule bg-bond max-[1000px]:grid-cols-2 max-[620px]:grid-cols-1 min-[1001px]:grid-cols-4 min-[1001px]:grid-rows-[auto_auto_1fr_auto]">
          {BEATS.map((b, i) => (
            <motion.div
              key={b.n}
              initial={reduced ? false : { opacity: 0, y: 8 }}
              whileInView={reduced ? undefined : { opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-60px' }}
              transition={{ duration: 0.4, delay: i * 0.06, ease: [0.22, 1, 0.36, 1] }}
              className={cn(
                'border-rule px-[18px] pb-6 pt-[22px]',
                'min-[1001px]:row-span-4 min-[1001px]:grid min-[1001px]:grid-rows-subgrid',
                // Column rules on wide, row rules once it wraps.
                'min-[1001px]:border-r min-[1001px]:last:border-r-0',
                'max-[1000px]:border-b max-[1000px]:[&:nth-child(odd)]:border-r',
                'max-[1000px]:[&:nth-last-child(-n+2)]:border-b-0',
                'max-[620px]:border-b max-[620px]:!border-r-0 max-[620px]:last:border-b-0',
              )}
            >
              <div className="font-mono text-[10px] font-medium tracking-[0.14em] text-ink-4">
                {b.n}
              </div>

              <h3 className="mt-[9px] self-start text-balance text-[15.5px] font-semibold leading-[1.3] tracking-[-0.022em]">
                {b.title}
              </h3>

              <p className="mt-2 self-start text-[12.5px] leading-[1.55] text-ink-2">{b.body}</p>

              {/*
                `self-start`, not `self-end`. The four share one row track, so the
                row's top is common and its height is the tallest panel's. Ending
                the panel at the row's bottom therefore pushes the shorter ones
                DOWN and their top edges apart, which is the ragged line this
                section was rebuilt to remove. Measured: 38px of spread with
                `self-end`, 0px with this.
              */}
              <div className="mt-4 self-start overflow-hidden rounded-[10px] border border-rule bg-sheet">
                {b.n === '01' && (
                  <>
                    <div className="flex items-center gap-[9px] border-b border-hair px-[11px] py-[9px]">
                      <span className="inline-flex items-center gap-[6px] font-mono text-[10px] uppercase tracking-[0.07em] text-zepto">
                        <span className="size-[7px] rounded-[2px] bg-zepto" />
                        zepto
                      </span>
                      <span className="text-[12px]">Cooking Oil</span>
                    </div>
                    <div className="flex items-center gap-[9px] border-b border-hair px-[11px] py-[9px] font-mono text-[12.5px] tabular-nums">
                      <span className="text-ink-4 line-through">{LIST}</span>
                      <span className="text-ink-4">→</span>
                      <span className="font-semibold text-ink">{SIGNED}</span>
                      <span className="ml-auto text-[10px] text-ink-3">{SURGE}</span>
                    </div>
                    <div className="px-[11px] py-[9px] font-mono text-[10px] text-ink-3">
                      signed · expires in ten minutes
                    </div>
                  </>
                )}

                {b.n === '02' && (
                  <>
                    <div className="flex items-center gap-2 border-b border-hair px-[11px] py-[9px]">
                      <Pill tone="pass">ALLOWED</Pill>
                      <span className="text-[11px] text-ink-3">shelf price</span>
                      <span className="ml-auto font-mono text-[12.5px] font-semibold tabular-nums">
                        {AT_LIST}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 px-[11px] py-[9px]">
                      <Pill tone="halt">REFUSED</Pill>
                      <span className="text-[11px] text-ink-3">signed price</span>
                      <span className="ml-auto font-mono text-[12.5px] font-semibold tabular-nums text-halt">
                        {AT_SIGNED}
                      </span>
                    </div>
                    <div className="border-t border-halt-line bg-halt-soft px-[11px] py-2 text-[11px] text-halt">
                      <b className="font-semibold">{PER_ITEM?.label}</b>, your limit is{' '}
                      {PER_ITEM?.bound.replace(/\.00$/, '')}
                    </div>
                  </>
                )}

                {b.n === '03' && (
                  <>
                    <div className="border-b border-hair px-[11px] py-[10px] text-[11.5px] font-medium leading-[1.5] text-ink">
                      Dropped Olive Oil. Cut Toor Dal from 4 to 1.
                    </div>
                    <div className="flex items-center gap-2 px-[11px] py-[9px]">
                      <Pill tone="pass">ALLOWED</Pill>
                      <span className="text-[11px] text-ink-3">second try</span>
                      <span className="ml-auto font-mono text-[12.5px] font-semibold tabular-nums text-pass">
                        {REPAIRED}
                      </span>
                    </div>
                  </>
                )}

                {b.n === '04' && (
                  <>
                    <Tick>This receipt is in the record</Tick>
                    <Tick>The record only ever grew</Tick>
                    <div className="px-[11px] py-[9px] font-mono text-[10px] text-ink-4">
                      checked in your browser
                    </div>
                  </>
                )}
              </div>
            </motion.div>
          ))}
        </div>

        {/*
          The third answer. `afa.required` is the only clause on this page where
          the gateway neither allows nor refuses, so it gets the refer ink and the
          words "held for you" rather than a softened refusal.
        */}
        <div className="mt-[14px] flex flex-wrap items-center gap-[14px] rounded-panel border border-refer-line bg-refer-soft px-5 py-[15px]">
          <span className="whitespace-nowrap font-mono text-[10px] font-semibold uppercase tracking-[0.1em] text-refer">
            Held for you
          </span>
          <p className="min-w-[22rem] flex-1 text-[13.5px] leading-[1.5] text-ink-2 max-sm:min-w-0">
            Above <b className="font-semibold text-ink">{AFA?.bound.replace(/\.00$/, '')}</b>, a
            line the regulator draws rather than us, the answer is neither yes nor no. The order
            waits, and is approved from a different device using a credential that{' '}
            <b className="font-semibold text-ink">cannot spend</b>. Neither payment network can
            carry that rule. This holds it because they cannot.
          </p>
        </div>
      </div>
    </section>
  );
}
