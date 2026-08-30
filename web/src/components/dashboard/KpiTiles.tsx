import type { ReactNode } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { MANDATE } from '@/data/policy';
import { COUNTS, SCOREBOARD } from '@/data/decisions';
import { AnimatedFigure } from '@/components/v2/AnimatedFigure';
import { rupees, rupeesWhole } from '@/lib/money';
import { cn } from '@/lib/utils';

const ENTER = { duration: 0.32, ease: [0.16, 1, 0.3, 1] as const };

function Tile({
  label,
  children,
  delay,
}: {
  label: string;
  children: ReactNode;
  delay: number;
}) {
  const reduced = useReducedMotion();
  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={reduced ? { duration: 0 } : { ...ENTER, delay }}
      className="rounded-panel border border-rule bg-bond px-4.5 py-4.25 shadow-sheet"
    >
      <div className="text-[11.5px] text-ink-3">{label}</div>
      {children}
    </motion.div>
  );
}

export function KpiTiles() {
  const reduced = useReducedMotion();
  const spent = MANDATE.committedPaise;
  const total = MANDATE.totalBudgetPaise;
  const spentPct = total > 0 ? Math.min((spent / total) * 100, 100) : 0;
  const containment = SCOREBOARD.containment.enforce;

  return (
    <div className="grid grid-cols-4 gap-3.5">
      <Tile label="Total spend" delay={0}>
        <div className="mt-2.5 flex items-baseline gap-1.5">
          <AnimatedFigure
            paise={spent}
            format={rupees}
            className="font-mono text-[26px] font-semibold tracking-[-0.03em]"
          />
          <span className="font-mono text-[15px] font-medium text-ink-3">/ {rupeesWhole(total)}</span>
        </div>
        <div className="mt-2.75 h-1 overflow-hidden rounded-full bg-rule">
          <motion.div
            className="h-full rounded-full bg-indigo"
            initial={{ width: 0 }}
            animate={{ width: `${spentPct}%` }}
            transition={reduced ? { duration: 0 } : { type: 'spring', bounce: 0, visualDuration: 0.6, delay: 0.15 }}
          />
        </div>
        <div className="mt-2.25 text-[12px] text-ink-3">
          <b className="font-medium text-ink-2">{rupeesWhole(total - spent)}</b> left of cap
        </div>
      </Tile>

      <Tile label="Orders evaluated" delay={0.05}>
        <div className="mt-2.5 font-mono text-[26px] font-semibold tracking-[-0.03em]">{COUNTS.evaluated}</div>
        <div className="mt-3.75 text-[12px] text-ink-3">
          <b className="font-medium text-pass">{COUNTS.allowed} allowed</b> ·{' '}
          <b className="font-medium text-halt">{COUNTS.refused} refused</b>
        </div>
      </Tile>

      <Tile label="Attack containment" delay={0.1}>
        <div className={cn('mt-2.5 font-mono text-[26px] font-semibold tracking-[-0.03em]', 'text-pass')}>
          {Math.round(containment.pct * 100)}%
        </div>
        <div className="mt-3.75 text-[12px] text-ink-3">
          {containment.contained} / {containment.total} enforce ·{' '}
          <b className="font-medium text-ink-2">{containment.total - containment.contained} escaped</b>
        </div>
      </Tile>

      <Tile label="Audit chain" delay={0.15}>
        <div className="mt-2.5 flex items-baseline gap-1.5 font-mono text-[26px] font-semibold tracking-[-0.03em]">
          {COUNTS.evaluated}
          <span className="text-[15px] font-medium text-ink-3">/ {COUNTS.evaluated}</span>
        </div>
        <div className="mt-3.75 text-[12px] text-ink-3">
          hashes verified · <b className="font-medium text-ink-2">SHA-256 chained</b>
        </div>
      </Tile>
    </div>
  );
}
