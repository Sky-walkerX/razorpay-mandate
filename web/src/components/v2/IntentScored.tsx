import { motion, useReducedMotion } from 'motion/react';
import { INTENT } from '@/data/policy';
import { cn } from '@/lib/utils';
import { SellerMark } from './SellerMark';

/**
 * The gap, argued from the primary material.
 *
 * The old section restated the problem in two lists beside each other: three
 * rows in one column, eight in the other, and half a card of empty space. It
 * also asked the reader to diff the lists themselves. This scores the sentence
 * the person actually said, clause by clause, against what the payment rail can
 * carry, which is the claim the heading makes, made out of their own words.
 *
 * Fragments are matched against `INTENT`, which comes from the signed policy
 * via `evidence.json`. Nothing here is retyped, so if the policy text changes,
 * an unmatched fragment simply stops being marked rather than quietly asserting
 * something the document no longer says.
 */
type Held = 'rail' | 'part' | 'prompt';

interface Scored {
  /** Verbatim substring of INTENT. */
  text: string;
  held: Held;
  /** The constraint this clause compiles to. */
  part: number;
  why: string;
}

const SCORED: Scored[] = [
  {
    text: 'from Zepto, Blinkit or Instamart',
    held: 'part',
    part: 6,
    why: 'Reserve Pay binds one seller. Three were named.',
  },
  {
    text: 'Stay under Rs 2000 in total',
    held: 'rail',
    part: 1,
    why: 'The rail enforces this cap itself.',
  },
  {
    text: 'Rs 1000 per order',
    held: 'prompt',
    part: 2,
    why: 'Nothing on the rail expresses a per-order cap.',
  },
  {
    text: 'No single item over Rs 500',
    held: 'prompt',
    part: 3,
    why: 'Nothing on the rail expresses a per-item cap.',
  },
  {
    text: 'no more than 5 of any one item',
    held: 'prompt',
    part: 5,
    why: 'Nothing on the rail expresses a quantity cap.',
  },
  {
    text: 'Nothing alcoholic',
    held: 'prompt',
    part: 7,
    why: 'Nothing on the rail expresses a category block.',
  },
  { text: 'At most 3 orders', held: 'prompt', part: 4, why: 'Nothing on the rail counts orders.' },
];

/**
 * Walks INTENT once, splitting it into scored and unscored runs, in order.
 * Each scored run carries its ordinal so the reveal can stagger off it without
 * a counter being mutated during render.
 */
type Segment = { plain: string } | { scored: Scored; ordinal: number };

function segment(text: string): Segment[] {
  const out: Segment[] = [];
  let cursor = 0;
  let ordinal = 0;
  for (const s of SCORED) {
    const at = text.indexOf(s.text, cursor);
    if (at < 0) continue; // policy text moved on; leave the clause unmarked
    if (at > cursor) out.push({ plain: text.slice(cursor, at) });
    out.push({ scored: s, ordinal: ordinal++ });
    cursor = at + s.text.length;
  }
  if (cursor < text.length) out.push({ plain: text.slice(cursor) });
  return out;
}

const UNDERLINE: Record<Held, string> = {
  rail: 'bg-pass',
  part: 'bg-refer',
  prompt: 'bg-halt',
};

const TALLY: { held: Held; label: string; blurb: string }[] = [
  {
    held: 'rail',
    label: 'Held by the rail',
    blurb:
      'The total cap, plus an expiry the person never had to say. Enforced by the payment network itself.',
  },
  {
    held: 'part',
    label: 'Held in part',
    blurb:
      'Reserve Pay binds one seller. Three were named, so two of them live in the prompt with everything else.',
  },
  {
    held: 'prompt',
    label: 'Held by a prompt',
    blurb:
      'Per order, per item, quantity, category, count. Each is a sentence a model has to keep remembering while an attacker writes into its context.',
  },
];

export default function IntentScored() {
  const reduced = useReducedMotion();
  const segments = segment(INTENT);
  const count = (held: Held) => SCORED.filter((s) => s.held === held).length;

  return (
    <div className="overflow-hidden rounded-panel border border-rule bg-bond shadow-sheet">
      <div className="flex flex-wrap items-center gap-3 border-b border-rule bg-sheet px-[22px] py-[11px]">
        <span className="font-mono text-[9.5px] font-semibold uppercase tracking-[0.12em] text-ink-2">
          What the person said, scored against what the rail can carry
        </span>
        <span className="ml-auto font-mono text-[10px] text-ink-3">mnd_groceries_01</span>
      </div>

      <motion.p
        className="max-w-[44rem] px-[22px] pb-[30px] pt-[34px] text-[clamp(1.15rem,2.05vw,1.6rem)] leading-[1.72] tracking-[-0.028em] text-ink-4"
        initial={reduced ? false : 'hidden'}
        whileInView="shown"
        viewport={{ once: true, amount: 0.35 }}
        variants={{ hidden: {}, shown: { transition: { staggerChildren: 0.07 } } }}
      >
        &ldquo;
        {segments.map((seg, i) => {
          if ('plain' in seg) return <span key={i}>{seg.plain}</span>;
          const s = seg.scored;
          return (
            <span
              key={i}
              title={s.why}
              className={cn(
                'relative whitespace-normal',
                s.held === 'prompt' ? 'text-ink-2' : 'text-ink',
              )}
            >
              {s.text}
              <sup className="ml-[2px] align-super font-mono text-[0.5em] tracking-normal text-ink-3">
                {s.part}
              </sup>
              {/* The scoring mark itself, wiped in left to right on scroll. */}
              <motion.span
                aria-hidden
                variants={{
                  hidden: { scaleX: 0 },
                  shown: { scaleX: 1 },
                }}
                transition={
                  reduced
                    ? { duration: 0 }
                    : { duration: 0.42, ease: [0.16, 1, 0.3, 1], delay: seg.ordinal * 0.05 }
                }
                className={cn(
                  'absolute inset-x-0 -bottom-[2px] block h-[3px] origin-left',
                  UNDERLINE[s.held],
                  s.held === 'prompt' && 'opacity-90',
                )}
                style={
                  s.held === 'prompt'
                    ? {
                        backgroundImage:
                          'linear-gradient(90deg, var(--color-halt) 0 4px, transparent 4px 8px)',
                        backgroundSize: '8px 3px',
                        backgroundRepeat: 'repeat-x',
                        backgroundColor: 'transparent',
                      }
                    : undefined
                }
              />
            </span>
          );
        })}
        &rdquo;
      </motion.p>

      <div className="grid border-t border-rule md:grid-cols-3">
        {TALLY.map((t, i) => (
          <div
            key={t.held}
            className={cn(
              'flex flex-col gap-2 px-[22px] py-5',
              i > 0 && 'border-t border-rule md:border-l md:border-t-0',
            )}
          >
            <span
              className={cn(
                'font-mono text-[30px] font-semibold leading-none tracking-[-0.05em] tabular-nums',
                t.held === 'rail' && 'text-pass',
                t.held === 'part' && 'text-refer',
                t.held === 'prompt' && 'text-halt',
              )}
            >
              {count(t.held)}
            </span>
            <span className="inline-flex items-center gap-2 text-[13px] font-medium tracking-[-0.015em]">
              <span
                className={cn(
                  'size-[7px] shrink-0',
                  t.held === 'rail' && 'bg-pass',
                  t.held === 'part' && 'rounded-full bg-refer',
                  t.held === 'prompt' && 'rotate-45 bg-halt',
                )}
              />
              {t.label}
            </span>
            {t.held === 'part' && (
              <span className="inline-flex gap-1">
                {['Zepto', 'Blinkit', 'Instamart'].map((n) => (
                  <SellerMark key={n} name={n} className="size-[18px]" />
                ))}
              </span>
            )}
            <span className="text-[12.5px] leading-[1.5] text-ink-3">{t.blurb}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
