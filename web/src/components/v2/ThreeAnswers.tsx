import { useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Bell, Check, Lock, X } from 'lucide-react';
import { partByKey } from '@/data/policy';
import { cn } from '@/lib/utils';

/**
 * The three answers, at the foot of the hero.
 *
 * The hero states the problem and ends on "charged, uncontained". Everything
 * built to answer that was invisible on this page: the agent repairing its own
 * basket, the approval landing on another device, and the receipt a visitor
 * checks themselves. This carries all three in one band, in the three meaning
 * inks, so the highest-traffic section of the page is not the only one missing
 * the product.
 *
 * It goes BELOW the four-node rail deliberately. The recorded walkthrough holds
 * the hero at a fixed scroll position, so anything inserted above the rail moves
 * that frame off its mark while anything under it changes nothing.
 *
 * The phone is interactive because an approval a visitor performs is a different
 * claim from an approval they read about. Approving here proves nothing
 * cryptographic and says so: the real thing is at /approve, on a device that is
 * not this one.
 */

const AFA = partByKey('afa.required');

/** The repair trace. Real figures from the enforce arm, quoted in the notes. */
const REFUSED_AT = '₹1,572';
const ALLOWED_AT = '₹923';
/** The held basket, sized to sit above the statutory line. */
const HELD_AT = '₹18,600';

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

/** What the visitor did on the phone. `null` while it is still waiting. */
type Answered = 'approved' | 'declined' | null;

function Phone() {
  const [answered, setAnswered] = useState<Answered>(null);

  return (
    <div className="flex justify-center">
      <div className="w-[172px] rounded-[18px] border border-rule bg-sunk px-[7px] pb-3 pt-2 shadow-xs">
        <div className="mx-auto mb-2 h-1 w-[42px] rounded-full bg-ink-4/50" />

        {answered === null ? (
          <div className="rounded-[11px] border border-rule bg-bond px-[10px] py-[9px]">
            <div className="flex items-center gap-[6px]">
              <span className="grid size-[13px] place-items-center rounded-[3px] bg-refer">
                <Bell className="size-[8px] text-bond" strokeWidth={2.6} />
              </span>
              <span className="font-mono text-[8px] uppercase tracking-[0.1em] text-ink-3">
                Mandate
              </span>
              <span className="ml-auto font-mono text-[8px] text-ink-4">now</span>
            </div>

            <div className="mt-[7px] text-[11.5px] font-semibold leading-[1.3] tracking-[-0.01em]">
              An order is waiting for you
            </div>
            <div className="mt-[3px] font-mono text-[15px] font-semibold tracking-[-0.02em] tabular-nums">
              {HELD_AT}
            </div>
            <div className="mt-1 text-[10px] leading-[1.4] text-ink-3">
              Groceries at zepto. Over the {AFA?.bound.replace(/\.00$/, '')} line.
            </div>

            <div className="mt-[9px] flex gap-[6px]">
              <button
                type="button"
                onClick={() => setAnswered('declined')}
                className="flex-1 rounded-md border border-rule bg-bond py-[5px] text-[10.5px] font-semibold text-ink-2 transition-colors hover:bg-sheet"
              >
                Decline
              </button>
              <button
                type="button"
                onClick={() => setAnswered('approved')}
                className="flex-1 rounded-md border border-pass bg-pass py-[5px] text-[10.5px] font-semibold text-bond transition-opacity hover:opacity-90"
              >
                Approve
              </button>
            </div>
          </div>
        ) : (
          <div className="rounded-[11px] border border-rule bg-bond px-[10px] py-[14px] text-center">
            <span
              className={cn(
                'mx-auto grid size-[30px] place-items-center rounded-full border',
                answered === 'approved'
                  ? 'border-pass-line bg-pass-soft'
                  : 'border-halt-line bg-halt-soft',
              )}
            >
              {answered === 'approved' ? (
                <Check className="size-[15px] text-pass" strokeWidth={2.6} />
              ) : (
                <X className="size-[15px] text-halt" strokeWidth={2.6} />
              )}
            </span>
            <div
              className={cn(
                'mt-[9px] text-[11.5px] font-semibold',
                answered === 'approved' ? 'text-pass' : 'text-halt',
              )}
            >
              {answered === 'approved' ? 'Approved' : 'Declined'}
            </div>
            <p className="mt-[3px] text-[10px] leading-[1.4] text-ink-3">
              {answered === 'approved'
                ? 'The agent may now place this one order, and no other.'
                : 'Nothing was charged. The agent is told only that it may not proceed.'}
            </p>
            <button
              type="button"
              onClick={() => setAnswered(null)}
              className="mt-[9px] font-mono text-[9px] uppercase tracking-[0.09em] text-ink-4 underline decoration-dotted underline-offset-2 transition-colors hover:text-ink-2"
            >
              reset
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function ThreeAnswers() {
  const reduced = useReducedMotion() ?? false;

  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 10 }}
      whileInView={reduced ? undefined : { opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-40px' }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className="mt-[38px] w-full max-w-[1100px]"
    >
      <div className="mb-[14px] flex flex-wrap items-baseline gap-3">
        <b className="text-[16px] font-semibold tracking-[-0.025em]">
          With Mandate, one of three things happens.
        </b>
        <span className="text-[13.5px] text-ink-2">Never a silent charge.</span>
      </div>

      <div className="grid overflow-hidden rounded-panel border border-rule bg-bond max-[980px]:grid-cols-1 min-[981px]:grid-cols-3 min-[981px]:grid-rows-[auto_auto_1fr]">
        {/* ── Refused, then repaired ─────────────────────────────────── */}
        <div className="border-rule px-[17px] pb-[18px] pt-4 max-[980px]:border-b min-[981px]:row-span-3 min-[981px]:grid min-[981px]:grid-rows-subgrid min-[981px]:border-r">
          <div className="flex items-center gap-2">
            <Pill tone="halt">REFUSED</Pill>
            <span className="text-[13.5px] font-semibold tracking-[-0.018em]">
              then it fixes itself
            </span>
          </div>
          <p className="mt-[9px] self-start text-[12px] leading-[1.5] text-ink-2">
            The agent is told which limit stopped it and nothing else. It shops again, inside
            the limit, with nobody stepping in.
          </p>
          <div className="mt-3 self-start overflow-hidden rounded-[10px] border border-rule bg-sheet">
            <div className="flex items-center gap-2 border-b border-hair px-[10px] py-2 text-[11.5px]">
              <Pill tone="halt">REFUSED</Pill>
              <span className="ml-auto font-mono font-semibold tabular-nums text-halt">
                {REFUSED_AT}
              </span>
            </div>
            <div className="border-b border-hair bg-bond px-[10px] py-[9px] text-[11.5px] font-medium leading-[1.45] text-ink">
              Dropped Olive Oil. Cut Toor Dal from 4 to 1.
            </div>
            <div className="flex items-center gap-2 px-[10px] py-2 text-[11.5px]">
              <Pill tone="pass">ALLOWED</Pill>
              <span className="ml-auto font-mono font-semibold tabular-nums text-pass">
                {ALLOWED_AT}
              </span>
            </div>
          </div>
        </div>

        {/* ── Held for you ───────────────────────────────────────────── */}
        <div className="border-rule px-[17px] pb-[18px] pt-4 max-[980px]:border-b min-[981px]:row-span-3 min-[981px]:grid min-[981px]:grid-rows-subgrid min-[981px]:border-r">
          <div className="flex items-center gap-2">
            <Pill tone="refer">HELD</Pill>
            <span className="text-[13.5px] font-semibold tracking-[-0.018em]">
              it asks you first
            </span>
          </div>
          <p className="mt-[9px] self-start text-[12px] leading-[1.5] text-ink-2">
            Above {AFA?.bound.replace(/\.00$/, '')} the answer is neither yes nor no. It waits,
            and you approve on your phone with a credential that cannot spend.
          </p>
          <div className="mt-3 self-start">
            <Phone />
          </div>
        </div>

        {/* ── Allowed, and checkable ─────────────────────────────────── */}
        <div className="px-[17px] pb-[18px] pt-4 min-[981px]:row-span-3 min-[981px]:grid min-[981px]:grid-rows-subgrid">
          <div className="flex items-center gap-2">
            <Pill tone="pass">ALLOWED</Pill>
            <span className="text-[13.5px] font-semibold tracking-[-0.018em]">
              and you can check it
            </span>
          </div>
          <p className="mt-[9px] self-start text-[12px] leading-[1.5] text-ink-2">
            Every answer is written into a sealed record. Your browser proves this one is in
            it, and that nothing earlier was changed.
          </p>
          <div className="mt-3 self-start overflow-hidden rounded-[10px] border border-rule bg-sheet">
            <div className="flex items-center gap-2 border-b border-hair px-[10px] py-2">
              <Check className="size-3 flex-shrink-0 text-pass" strokeWidth={2.4} />
              <span className="text-[11px] text-ink-2">This receipt is in the record</span>
            </div>
            <div className="flex items-center gap-2 border-b border-hair px-[10px] py-2">
              <Check className="size-3 flex-shrink-0 text-pass" strokeWidth={2.4} />
              <span className="text-[11px] text-ink-2">The record only ever grew</span>
            </div>
            <div className="flex items-center gap-2 px-[10px] py-2">
              <span className="text-[11px] text-ink-3">checked in your browser</span>
              <span className="ml-auto inline-flex items-center gap-[6px] rounded-lg border border-rule bg-bond px-[9px] py-1 font-mono text-[11px] font-medium text-ink-2">
                <Lock className="size-[10px] text-ink-3" strokeWidth={2} />
                Verify
              </span>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}
