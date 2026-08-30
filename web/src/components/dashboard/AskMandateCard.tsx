import { ArrowUp } from 'lucide-react';
import { motion, useReducedMotion } from 'motion/react';

export function AskMandateCard() {
  const reduced = useReducedMotion();

  return (
    <div className="relative overflow-hidden rounded-panel border border-rule bg-bond px-4.5 py-4.5 text-center shadow-sheet">
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: 'radial-gradient(circle at 50% 28%, rgb(47 94 255 / 0.1), transparent 60%)' }}
      />

      <div className="relative">
        <motion.div
          className="mx-auto size-16 rounded-full"
          style={{
            background: 'radial-gradient(circle at 35% 30%, #6f8fff, #2f5eff 65%, #123bcf)',
            boxShadow: '0 8px 24px -6px rgb(47 94 255 / 0.55)',
          }}
          animate={reduced ? undefined : { scale: [1, 1.04, 1] }}
          transition={reduced ? undefined : { duration: 3.2, repeat: Infinity, ease: 'easeInOut' }}
        />

        <div className="mt-3.5 text-[13px] font-semibold">Ask Mandate</div>
        <div className="mt-1 text-[11.5px] leading-normal text-ink-3">
          &ldquo;Why was order #04 refused?&rdquo;
        </div>

        <div className="mt-3.5 flex items-center gap-2 rounded-full border border-rule bg-sheet px-3 py-2.25 text-left opacity-70">
          <span className="truncate text-[12px] text-ink-4">Ask about a decision…</span>
          <ArrowUp className="ml-auto size-[13px] shrink-0 text-ink-4" />
        </div>
        <div className="mt-2 font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink-4">Coming soon</div>
      </div>
    </div>
  );
}
