import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight } from 'lucide-react';
import {
  PARTS,
  LIMITS,
  RULES,
  PART_COUNT_TEXT_CAP,
  SET_PART_COUNT_TEXT,
} from '@/data/policy';
import { Spell } from '@/lib/spell';
import { PartsGrid } from './YourLimitsGrid';
import { cn } from '@/lib/utils';

/**
 * Section 02: the gap, and the parts that close it, one argument, not three.
 *
 * This replaces three components that were each making the same point in a
 * different register and in three different places on the page: the old `#gap`
 * section's prose, `IntentScored`'s clause-by-clause scoring of the policy
 * sentence, and `YourLimitsGrid` sitting several screens below as an unmotivated
 * feature matrix.
 *
 * The join is the design. Every one of the twelve conditions carries the part
 * number it compiles to, so the grid underneath is read as the resolution of
 * the complaint above it rather than as a list of features. Every part is
 * reachable from the twelve, if a part ever stops being reachable, either the
 * example is wrong or the part has no motivation on this page.
 *
 * Bounds are interpolated from `PARTS`, which `evidence.json` fills from the
 * signed policy. The prices inside the dal clause are catalog illustration, not
 * policy, and are prose for that reason.
 */

const boundOf = (n: number) => PARTS.find((p) => p.n === n)?.bound ?? '';
/** "₹2,000.00" reads as "₹2,000" in a sentence. Paise belong on the chip. */
const short = (n: number) => boundOf(n).replace(/\.00$/, '');

interface Condition {
  text: string;
  /** Which part this compiles to, by its reference numeral. */
  part: number;
  /** Whether the payment rail could carry it on its own. */
  onRail: boolean;
}

const CONDITIONS: Condition[] = [
  { text: `Total under ${short(1)}`, part: 1, onRail: true },
  { text: `Only from ${boundOf(6)}`, part: 6, onRail: true },
  { text: 'Before the match starts, 8pm', part: 8, onRail: true },
  { text: `Under ${short(2)} in any one transaction`, part: 2, onRail: false },
  { text: 'Don’t swap the ₹80 dal for the ₹400 organic one', part: 3, onRail: false },
  { text: `Under ${short(3)} on any single item`, part: 3, onRail: false },
  { text: 'One order, not five', part: 4, onRail: false },
  { text: `No more than ${boundOf(5)}`, part: 5, onRail: false },
  { text: 'Nothing from a merchant I have never used', part: 6, onRail: false },
  { text: 'Not the seller who sent rotten produce', part: 6, onRail: false },
  { text: 'Nothing alcoholic', part: 7, onRail: false },
  { text: 'Don’t reorder what arrived yesterday', part: 9, onRail: false },
];

const ON_RAIL = CONDITIONS.filter((c) => c.onRail).length;
const IN_PROMPT = CONDITIONS.length - ON_RAIL;

function Row({ c, i, reduced }: { c: Condition; i: number; reduced: boolean }) {
  return (
    <motion.li
      className={cn(
        'grid grid-cols-[7px_1fr_auto] items-center gap-x-[14px] border-b border-hair px-5 py-[9px] last:border-b-0',
        'max-sm:grid-cols-[7px_1fr] max-sm:gap-y-1',
      )}
      initial={reduced ? false : { opacity: 0, x: -6 }}
      whileInView={{ opacity: 1, x: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.32, delay: Math.min(i * 0.028, 0.34), ease: [0.22, 0.61, 0.36, 1] }}
    >
      <span
        aria-hidden
        className={cn('size-[7px] rounded-full', c.onRail ? 'bg-indigo' : 'bg-halt-line')}
      />
      <span className={cn('text-[13.5px] leading-[1.45]', c.onRail ? 'text-ink' : 'text-ink-2')}>
        {c.text}
      </span>
      <span className="flex items-center gap-[10px] max-sm:col-start-2">
        <span
          className={cn(
            'font-mono text-[9.5px] uppercase tracking-[0.09em]',
            c.onRail ? 'text-indigo' : 'text-halt',
          )}
        >
          {c.onRail ? 'the rail holds this' : 'system prompt'}
        </span>
        <span className="w-[46px] text-right font-mono text-[10px] tracking-[0.05em] text-ink-3">
          part {c.part}
        </span>
      </span>
    </motion.li>
  );
}

export default function GapAndParts() {
  const reduced = useReducedMotion() ?? false;

  return (
    <section id="gap" className="border-b border-rule bg-bond">
      <div className="mx-auto max-w-[1220px] px-8 py-[84px] max-sm:px-[18px] max-md:py-14">
        {/* ── The gap ───────────────────────────────────────────────── */}
        <div className="grid items-start gap-x-[60px] gap-y-10 lg:grid-cols-[minmax(0,0.86fr)_minmax(0,1fr)]">
          <div className="lg:sticky lg:top-[84px]">
            <span className="inline-flex items-center gap-2 rounded-full border border-rule bg-bond px-[13px] py-[6px] font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
              <span className="size-[6px] rotate-45 bg-halt" />
              02 · the gap
            </span>

            <h2 className="mt-[18px] text-balance text-[clamp(1.9rem,3.6vw,2.75rem)] font-semibold leading-[1.06] tracking-[-0.046em]">
              The rail can hold three things.{' '}
              <span className="text-ink-3">You meant twelve.</span>
            </h2>

            <p className="mt-[16px] max-w-[31rem] text-[16.5px] leading-[1.62] text-ink-2">
              UPI Reserve Pay knows a total cap, a merchant and an expiry. AP2’s Intent Mandate lands
              in the same place. The other nine have nowhere to live except a system prompt, which
              makes the control protecting your money{' '}
              <b className="font-medium text-ink">
                a language model’s willingness to keep remembering an instruction
              </b>{' '}
              while a seller writes into the same context window.
            </p>

            <div className="mt-[22px] flex gap-[26px] border-t border-rule pt-[18px]">
              <div>
                <div className="font-mono text-[30px] font-semibold leading-none tracking-[-0.05em] text-indigo">
                  {ON_RAIL}
                </div>
                <div className="mt-[6px] text-[12.5px] leading-[1.45] text-ink-3">
                  the rail can carry
                </div>
              </div>
              <span aria-hidden className="w-px bg-rule" />
              <div>
                <div className="font-mono text-[30px] font-semibold leading-none tracking-[-0.05em] text-halt">
                  {IN_PROMPT}
                </div>
                <div className="mt-[6px] text-[12.5px] leading-[1.45] text-ink-3">
                  live in a system prompt
                </div>
              </div>
            </div>
          </div>

          <div className="overflow-hidden rounded-panel border border-rule bg-bond shadow-sheet">
            <div className="border-b border-rule bg-sheet px-5 py-4">
              <div className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-ink-3">
                one sentence you said
              </div>
              <p className="mt-[9px] text-[16.5px] leading-[1.45] tracking-[-0.022em]">
                “Order my usual groceries before the match, under {short(1)}.”
              </p>
            </div>

            <ul>
              {CONDITIONS.map((c, i) => (
                <Row key={c.text} c={c} i={i} reduced={reduced} />
              ))}
            </ul>

            <div className="flex items-center gap-[11px] border-t border-rule bg-halt-soft px-5 py-[14px]">
              <span aria-hidden className="size-[8px] shrink-0 rotate-45 bg-halt" />
              <p className="text-[13px] leading-[1.5] text-ink-2">
                <b className="font-semibold text-halt">
                  {IN_PROMPT} of {CONDITIONS.length}
                </b>{' '}
                are enforced only by a model choosing to remember them.
              </p>
            </div>
          </div>
        </div>

        {/* ── The turn ──────────────────────────────────────────────── */}
        <div className="mt-[54px] flex items-center gap-5 max-md:mt-10">
          <span aria-hidden className="h-px grow bg-rule" />
          <span className="inline-flex items-center gap-[10px] rounded-full border border-indigo bg-indigo-soft px-4 py-[7px] font-mono text-[11px] uppercase tracking-[0.1em] text-indigo max-sm:text-[10px]">
            so the twelve get compiled, signed, and checked in code
            <ArrowRight className="size-[13px]" />
          </span>
          <span aria-hidden className="h-px grow bg-rule" />
        </div>

        {/* ── The parts ─────────────────────────────────────────────── */}
        <div id="limits" className="mt-[46px] scroll-mt-[76px] max-md:mt-10">
          <div className="mb-10 flex flex-col justify-between gap-6 md:flex-row md:items-end">
            <div className="max-w-[36rem]">
              <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3">
                Pre-signed policy matrix
              </span>
              <h3 className="mt-2 text-balance text-[clamp(1.7rem,3vw,2.3rem)] font-semibold leading-[1.1] tracking-[-0.04em]">
                {PART_COUNT_TEXT_CAP} kinds of limit.{' '}
                <span className="text-ink-3">A closed set, evaluated in bounded time.</span>
              </h3>
              <p className="mt-3 text-[15px] leading-relaxed text-ink-2">
                {Spell(LIMITS.length)} compare a number against a figure you set. {Spell(RULES.length)}{' '}
                test a list, a category or a monotonic clock. Closed means the set does not grow, so
                evaluation terminates, and a refusal can always name the part it came from.
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3 rounded-lg border border-rule bg-sheet p-2 font-mono text-[11px] text-ink-3">
              <span className="inline-flex items-center gap-1.5 px-1.5 py-0.5">
                <span className="size-2 rounded-full bg-pass" /> {LIMITS.length} numerical limits
              </span>
              <span className="inline-flex items-center gap-1.5 px-1.5 py-0.5">
                <span className="size-2 rounded-full bg-indigo" /> {RULES.length} deterministic rules
              </span>
            </div>
          </div>

          <PartsGrid />

          <div className="mt-6 flex flex-wrap items-center justify-between gap-4 font-mono text-[11px] text-ink-3">
            <span>
              Every bound read from the signed policy · <b className="text-ink-2">nothing retyped</b>
            </span>
            <span>This mandate sets {SET_PART_COUNT_TEXT}, every one checked on every order</span>
          </div>
        </div>
      </div>
    </section>
  );
}
