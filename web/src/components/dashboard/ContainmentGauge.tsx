import { motion, useReducedMotion } from 'motion/react';
import { SCOREBOARD } from '@/data/decisions';

const R = 80; // chord between the arc's two endpoints (20,105)-(180,105) is 160 = 2R
const CIRC = Math.PI * R; // half the circumference — this is a semicircle gauge

export function ContainmentGauge() {
  const reduced = useReducedMotion();
  const c = SCOREBOARD.containment.enforce;
  const pct = c.pct * 100;

  return (
    <div className="flex flex-col items-center rounded-panel border border-rule bg-bond px-4.5 py-4 text-center shadow-sheet">
      <h3 className="self-start text-[13px] font-semibold tracking-[-0.02em]">Attack containment</h3>

      <svg viewBox="0 0 200 120" className="mt-1.5 w-45">
        <path
          d={`M20,105 A${R},${R} 0 0 1 180,105`}
          fill="none"
          stroke="var(--color-rule-soft)"
          strokeWidth={14}
          strokeLinecap="round"
        />
        <motion.path
          d={`M20,105 A${R},${R} 0 0 1 180,105`}
          fill="none"
          stroke="var(--color-pass)"
          strokeWidth={14}
          strokeLinecap="round"
          strokeDasharray={CIRC}
          initial={{ strokeDashoffset: CIRC }}
          animate={{ strokeDashoffset: CIRC * (1 - pct / 100) }}
          transition={reduced ? { duration: 0 } : { type: 'spring', bounce: 0, visualDuration: 0.7 }}
        />
        <text x="100" y="90" textAnchor="middle" fontSize="26" fontWeight={700} fill="var(--color-ink)" fontFamily="var(--font-mono)">
          {Math.round(pct)}%
        </text>
      </svg>

      <div className="-mt-1 text-[11.5px] text-ink-3">
        {c.contained} / {c.total} hostile attacks contained · {c.total - c.contained} escaped
      </div>
    </div>
  );
}
