import { useCallback, useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { RotateCw } from 'lucide-react';
import { PARTS, PART_COUNT } from '@/data/policy';
import { SCENARIOS } from '@/data/scenarios';
import { CAP_AT, fillPercent, readoutFor } from '@/lib/headroom';
import { rupees } from '@/lib/money';
import { cn } from '@/lib/utils';
import { AnimatedFigure } from './AnimatedFigure';
import { SellerChip } from './SellerMark';

type RowState = 'idle' | 'allow' | 'deny' | 'unknown' | 'skip';

/** Milliseconds between parts. Slow enough to read as an evaluation, not a flash. */
const STEP_MS = 120;

const VERDICT_WORD: Record<string, string> = {
  allow: 'ALLOWED',
  deny: 'REFUSED',
  unknown: 'NEEDS YOU',
};

/** No overshoot on anything carrying an amount. */
const SETTLE = { type: 'spring', bounce: 0, visualDuration: 0.45 } as const;
/** Chrome may overshoot a little; it carries no value. */
const SNAP = { type: 'spring', bounce: 0.18, visualDuration: 0.32 } as const;
/** Gentle entry for constraint rows appearing during evaluation. */
const ENTER = { duration: 0.28, ease: [0.16, 1, 0.3, 1] as const };

/* -------------------------------------------------------------------------- */
/*  Sub-components                                                            */
/* -------------------------------------------------------------------------- */

/** Shape carries meaning alongside hue, never hue alone. */
function Marker({ state, size = 7 }: { state: RowState; size?: number }) {
  return (
    <span
      className={cn(
        'shrink-0 transition-colors duration-200',
        state === 'allow' && 'bg-pass',
        state === 'deny' && 'rotate-45 bg-halt',
        state === 'unknown' && 'rounded-full bg-refer',
        (state === 'idle' || state === 'skip') && 'bg-ink-4',
      )}
      style={{ width: size, height: size }}
    />
  );
}

/** Limit progress track — wider and taller than the old panel. */
function Track({ load, state }: { load: number; state: RowState }) {
  const reduced = useReducedMotion();
  return (
    <span className="relative block h-[18px] min-w-0 flex-1 overflow-hidden rounded-[5px] border border-hair bg-sunk">
      <motion.span
        className={cn(
          'absolute inset-y-0 left-0 block rounded-l-[4px]',
          state === 'deny' && 'bg-halt',
          state === 'unknown' && 'bg-refer',
          state === 'allow' && 'bg-pass',
        )}
        initial={{ width: '0%' }}
        animate={{ width: `${fillPercent(load, CAP_AT)}%` }}
        transition={reduced ? { duration: 0 } : SETTLE}
      />
      {/* The cap line and the over-zone past it. */}
      <span
        aria-hidden
        className="absolute inset-y-0 right-0 border-l border-ink/20"
        style={{
          left: `${CAP_AT}%`,
          backgroundImage:
            'repeating-linear-gradient(45deg, var(--color-halt-soft) 0 4px, transparent 4px 8px)',
        }}
      />
    </span>
  );
}

function ruleWord(state: RowState): string {
  if (state === 'allow') return 'matches';
  if (state === 'deny') return 'no match';
  if (state === 'unknown') return 'unresolved';
  return '';
}

/* -------------------------------------------------------------------------- */
/*  Main component                                                            */
/* -------------------------------------------------------------------------- */

export default function GatewayPanel() {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(0);
  const [states, setStates] = useState<RowState[]>(() => PARTS.map(() => 'idle'));
  const [settled, setSettled] = useState(false);
  const timers = useRef<number[]>([]);
  const panelRef = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  const sc = SCENARIOS[active];

  const clear = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };

  const run = useCallback(
    (index: number) => {
      clear();
      const s = SCENARIOS[index];
      setActive(index);
      setSettled(false);
      setStates(PARTS.map(() => 'idle'));

      const last = s.stopsAt < 0 ? PARTS.length - 1 : s.stopsAt;
      const step = reduced ? 0 : STEP_MS;

      PARTS.forEach((_, i) => {
        timers.current.push(
          window.setTimeout(() => {
            setStates((prev) => {
              const next = [...prev];
              if (s.stopsAt >= 0 && i > last) next[i] = 'skip';
              else if (s.stopsAt >= 0 && i === s.stopsAt) next[i] = s.verdict;
              else next[i] = 'allow';
              return next;
            });
          }, step * (i + 1)),
        );
      });

      timers.current.push(
        window.setTimeout(() => setSettled(true), step * (PARTS.length + 1)),
      );
    },
    [reduced],
  );

  /* Fire the first evaluation when the panel scrolls into view. */
  useEffect(() => {
    const el = panelRef.current;
    const begin = () => {
      if (started.current) return;
      started.current = true;
      run(0);
    };
    if (!el || reduced || !('IntersectionObserver' in window)) {
      begin();
      return clear;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          window.setTimeout(begin, 340);
          io.disconnect();
        }
      },
      { threshold: 0.25 },
    );
    io.observe(el);
    const safety = window.setTimeout(begin, 1600);
    return () => {
      io.disconnect();
      window.clearTimeout(safety);
      clear();
    };
  }, [run, reduced]);

  /* Derived state */
  const skippedCount = states.filter((s) => s === 'skip').length;

  return (
    <div
      ref={panelRef}
      className="overflow-hidden rounded-panel border border-rule bg-bond shadow-lift"
    >
      {/* ─── Header ─── */}
      <div className="flex h-11 items-center gap-3 border-b border-rule bg-sheet px-5">
        <span className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-ink-2">
          Mandate Gateway
        </span>
        <span className="ml-auto inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.08em] text-pass">
          <span className="size-[6px] rounded-full bg-pass ring-[3px] ring-pass/15" />
          enforcing
        </span>
      </div>

      {/* ─── Scenario Tabs ─── */}
      <div
        className="flex overflow-x-auto border-b border-rule"
        role="tablist"
        aria-label="Order under test"
      >
        {SCENARIOS.map((s, i) => (
          <button
            key={s.id}
            type="button"
            role="tab"
            aria-selected={i === active}
            onClick={() => run(i)}
            className={cn(
              'relative flex min-w-0 flex-1 items-center justify-center gap-2 whitespace-nowrap',
              'border-r border-hair px-2.5 py-3 text-[12px] font-medium last:border-r-0',
              'transition-colors hover:bg-sheet',
              i === active ? 'text-ink' : 'text-ink-3 hover:text-ink-2',
            )}
          >
            <span
              className={cn(
                'size-[6px] shrink-0',
                s.verdict === 'deny' && 'rotate-45 bg-halt',
                s.verdict === 'unknown' && 'rounded-full bg-refer',
                s.verdict === 'allow' && 'bg-pass',
              )}
            />
            {s.tab}
            {i === active && (
              <motion.span
                layoutId="tab-indicator"
                transition={reduced ? { duration: 0 } : SNAP}
                className="absolute inset-x-0 -bottom-px h-0.5 bg-indigo"
              />
            )}
          </button>
        ))}
      </div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* Stage 1 · Incoming Order                                          */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <div className="border-b border-rule p-5">
        <div className="flex flex-wrap items-center gap-3">
          <SellerChip name={sc.seller} />
          <span className="rounded-md border border-rule bg-sheet px-2 py-0.5 font-mono text-[10.5px] text-ink-3">
            place_order
          </span>
          <AnimatedFigure
            paise={sc.amountPaise}
            format={rupees}
            className="ml-auto font-mono text-[24px] font-semibold tracking-[-0.045em]"
          />
        </div>

        {/* Payload — the raw text the agent saw, including seller-injected segments. */}
        <div className="mt-3 rounded-lg border border-hair bg-sunk px-3.5 py-2.5 font-mono text-[11.5px] leading-[1.68] text-ink-2 break-words">
          {sc.payload.map((seg, k) => (
            <span
              key={k}
              className={cn(
                seg.hostile &&
                  'rounded-[2px] bg-halt-soft font-medium text-halt shadow-[0_0_0_2px_var(--color-halt-soft)]',
                seg.dim && 'text-ink-3',
              )}
            >
              {seg.text}
            </span>
          ))}
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* Stage 2 · Mandate Gate — focused evaluation                       */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <div className="px-5 pb-5 pt-4">
        {/* Gate header */}
        <div className="flex items-center gap-3">
          <span className="font-mono text-[9.5px] font-semibold uppercase tracking-[0.12em] text-ink">
            Evaluation
          </span>
          <span className="h-px flex-1 bg-rule" />
          <AnimatePresence mode="wait" initial={false}>
            <motion.span
              key={settled ? 'done' : 'run'}
              initial={reduced ? false : { opacity: 0 }}
              animate={{ opacity: 1 }}
              className="font-mono text-[10px] tabular-nums text-ink-3"
            >
              {settled ? `${sc.ms} ms` : '···'}
            </motion.span>
          </AnimatePresence>
        </div>

        {/* Constraint rows — only evaluated parts, never idle or skip */}
        <div className="mt-3 space-y-1.5">
          {PARTS.map((part, i) => {
            const state = states[i];
            if (state === 'idle' || state === 'skip') return null;

            const isStop = settled && sc.stopsAt === i;
            const readout =
              part.kind === 'limit' ? readoutFor(part, sc.load[i] ?? 0) : null;

            return (
              <motion.div
                key={part.key}
                initial={reduced ? false : { opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={reduced ? { duration: 0 } : ENTER}
              >
                {/* The constraint row itself */}
                <div
                  className={cn(
                    'flex items-center gap-3 rounded-lg px-3.5 py-2.5',
                    'transition-colors duration-200',
                    state === 'deny' && 'bg-halt-soft',
                    state === 'unknown' && 'bg-refer-soft',
                    state === 'allow' && 'bg-sunk/50',
                  )}
                >
                  {/* Part number */}
                  <span
                    className={cn(
                      'inline-flex size-[22px] shrink-0 items-center justify-center rounded-full border',
                      'font-mono text-[10px] font-medium',
                      state === 'deny' && 'border-halt/30 text-halt',
                      state === 'unknown' && 'border-refer/30 text-refer',
                      state === 'allow' && 'border-pass-line text-pass',
                    )}
                  >
                    {part.n}
                  </span>

                  {/* Constraint name */}
                  <span
                    className={cn(
                      'w-[130px] shrink-0 truncate text-[13px] font-medium',
                      state === 'deny' && 'text-halt',
                      state === 'unknown' && 'text-refer',
                      state === 'allow' && 'text-ink-2',
                    )}
                  >
                    {part.label}
                  </span>

                  {/* Track (limits) or bound text (rules) */}
                  <span className="flex min-w-0 flex-1 items-center">
                    {part.kind === 'limit' ? (
                      <Track load={sc.load[i] ?? 0} state={state} />
                    ) : (
                      <span className="truncate font-mono text-[10.5px] text-ink-3">
                        {part.bound}
                      </span>
                    )}
                  </span>

                  {/* Readout or rule status */}
                  <span
                    className={cn(
                      'shrink-0 text-right font-mono leading-tight',
                      state === 'deny' && 'text-halt',
                      state === 'unknown' && 'text-refer',
                      state === 'allow' && 'text-pass',
                    )}
                  >
                    {part.kind === 'limit' && readout ? (
                      <>
                        <span className="block text-[12px] font-semibold tracking-[-0.025em]">
                          {readout.figure}
                        </span>
                        <span className="block text-[9px] font-normal text-ink-3">
                          {readout.against}
                        </span>
                      </>
                    ) : (
                      <span className="flex items-center gap-1.5 text-[11px]">
                        <Marker state={state} size={6} />
                        {ruleWord(state)}
                      </span>
                    )}
                  </span>
                </div>

                {/* The clause that stopped the order, quoted from the signed policy. */}
                <AnimatePresence initial={false}>
                  {isStop && (
                    <motion.div
                      key="clause"
                      initial={reduced ? false : { height: 0, opacity: 0 }}
                      animate={{ height: 'auto', opacity: 1 }}
                      exit={{ height: 0, opacity: 0 }}
                      transition={reduced ? { duration: 0 } : SNAP}
                      className="overflow-hidden"
                    >
                      <div
                        className={cn(
                          'ml-[52px] mr-3 mt-1.5 mb-1 border-l-2 py-2 pl-4 text-[12.5px] leading-[1.6]',
                          sc.verdict === 'unknown'
                            ? 'border-refer text-refer'
                            : 'border-halt text-halt',
                        )}
                      >
                        <span className="mb-1 block font-mono text-[9px] uppercase tracking-[0.1em] opacity-70">
                          Part {part.n} ·{' '}
                          {sc.verdict === 'unknown'
                            ? 'needs your decision'
                            : 'the limit it broke'}
                        </span>
                        <span className="font-medium">{sc.clause}</span>
                        <span className="mt-[3px] block text-ink-2">{sc.actual}</span>
                      </div>
                    </motion.div>
                  )}
                </AnimatePresence>
              </motion.div>
            );
          })}
        </div>

        {/* Skip badge — replaces the 7 dimmed "not checked" rows */}
        <AnimatePresence initial={false}>
          {skippedCount > 0 && (
            <motion.div
              key="skip-badge"
              initial={reduced ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -4 }}
              transition={reduced ? { duration: 0 } : { duration: 0.25, delay: 0.06 }}
              className="mt-2.5 flex items-center gap-2 rounded-lg border border-dashed border-rule bg-sheet/80 px-3.5 py-2"
            >
              <span className="text-[12px]">⚡</span>
              <span className="font-mono text-[11px] text-ink-3">
                {skippedCount} subsequent{' '}
                {skippedCount === 1 ? 'rule' : 'rules'} skipped
              </span>
              <span className="ml-auto rounded-full border border-rule bg-sunk px-2 py-px font-mono text-[9px] uppercase tracking-[0.08em] text-ink-4">
                fail-fast
              </span>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════ */}
      {/* Stage 3 · Verdict & Air Gap                                       */}
      {/* ═══════════════════════════════════════════════════════════════════ */}
      <div
        className={cn(
          'border-t border-rule px-5 py-4 transition-colors duration-300',
          settled && sc.verdict === 'deny' && 'bg-halt-soft',
          settled && sc.verdict === 'allow' && 'bg-pass-soft',
          settled && sc.verdict === 'unknown' && 'bg-refer-soft',
          !settled && 'bg-sheet',
        )}
      >
        {/* Verdict line */}
        <div className="flex items-center gap-3">
          <span
            className={cn(
              'inline-flex items-center gap-2.5 font-mono text-[14px] font-semibold tracking-[0.06em]',
              'transition-colors duration-300',
              settled && sc.verdict === 'deny' && 'text-halt',
              settled && sc.verdict === 'allow' && 'text-pass',
              settled && sc.verdict === 'unknown' && 'text-refer',
              !settled && 'text-ink-3',
            )}
          >
            <span
              className={cn(
                'size-[9px] bg-current transition-transform duration-200',
                settled && sc.verdict === 'deny' && 'rotate-45',
                settled && sc.verdict === 'unknown' && 'rounded-full',
              )}
            />
            <AnimatePresence mode="wait" initial={false}>
              <motion.span
                key={settled ? sc.verdict : 'checking'}
                initial={reduced ? false : { y: 6, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                exit={reduced ? undefined : { y: -6, opacity: 0 }}
                transition={reduced ? { duration: 0 } : { duration: 0.18 }}
              >
                {settled ? VERDICT_WORD[sc.verdict] : 'CHECKING'}
              </motion.span>
            </AnimatePresence>
          </span>

          <span className="ml-auto flex items-center gap-2.5">
            <button
              type="button"
              onClick={() => run(active)}
              title="Run this order again"
              aria-label="Run this order again"
              className="inline-flex rounded-md p-1 text-ink-3 transition-colors hover:bg-ink/5 hover:text-ink"
            >
              <RotateCw className="size-[14px]" />
            </button>
          </span>
        </div>

        {/* Summary */}
        <p className="mt-1.5 text-[13px] tracking-[-0.015em] text-ink-2">
          {settled ? sc.summary : `${PART_COUNT} parts, in order`}
        </p>

        {/* Air Gap — the visual proof that money stayed or moved */}
        <AnimatePresence initial={false}>
          {settled && (
            <motion.div
              key={`airgap-${sc.id}`}
              initial={reduced ? false : { opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={
                reduced ? { duration: 0 } : { duration: 0.35, delay: 0.1 }
              }
              className="mt-3"
            >
              <div
                className={cn(
                  'flex items-center gap-2.5 rounded-lg border px-3.5 py-2',
                  sc.verdict === 'deny' && 'border-halt-line',
                  sc.verdict === 'allow' && 'border-pass-line',
                  sc.verdict === 'unknown' && 'border-refer-line',
                )}
              >
                <Marker
                  state={
                    sc.verdict === 'allow'
                      ? 'allow'
                      : sc.verdict === 'deny'
                        ? 'deny'
                        : 'unknown'
                  }
                  size={6}
                />

                <span
                  className={cn(
                    'h-px flex-1',
                    sc.verdict === 'deny' &&
                      'border-t border-dashed border-halt/30',
                    sc.verdict === 'allow' && 'bg-pass/25',
                    sc.verdict === 'unknown' &&
                      'border-t border-dotted border-refer/30',
                  )}
                />

                <span
                  className={cn(
                    'shrink-0 font-mono text-[11px] font-medium tabular-nums',
                    sc.verdict === 'deny' && 'text-halt',
                    sc.verdict === 'allow' && 'text-pass',
                    sc.verdict === 'unknown' && 'text-refer',
                  )}
                >
                  {sc.movedPaise > 0
                    ? `${rupees(sc.movedPaise)} dispatched`
                    : sc.verdict === 'unknown'
                      ? 'awaiting decision'
                      : '₹0.00 charged'}
                </span>

                <span
                  className={cn(
                    'h-px flex-1',
                    sc.verdict === 'deny' &&
                      'border-t border-dashed border-halt/30',
                    sc.verdict === 'allow' && 'bg-pass/25',
                    sc.verdict === 'unknown' &&
                      'border-t border-dotted border-refer/30',
                  )}
                />

                <Marker
                  state={
                    sc.verdict === 'allow'
                      ? 'allow'
                      : sc.verdict === 'deny'
                        ? 'deny'
                        : 'unknown'
                  }
                  size={6}
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
