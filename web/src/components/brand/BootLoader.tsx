import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { PARTS } from '@/data/policy';

/**
 * The opening: a beam crosses the plate, the gate closes behind it, the name
 * arrives, and the plate lifts. About 1.9 seconds, and it is the mark
 * performing its own function rather than a spinner borrowed from somewhere.
 *
 * Three rules it has to obey, because a loader that breaks any of them is
 * worse than no loader:
 *
 * - It runs once per tab. `sessionStorage` is read in the initialiser, so a
 *   route change or a return to `/` never replays it.
 * - Reduced motion skips it entirely, not a shortened version, none of it.
 * - It never gates content. Nothing waits on this; the page beneath is already
 *   mounted and interactive, and the plate is a cover that lifts off it.
 *
 * The `sessionStorage` reads are wrapped because a private window, or a browser
 * set to block site data, throws on access rather than returning null.
 */

const SEEN_KEY = 'mandate.boot.seen';
const LIFT_AT_MS = 1900;

/** Ease that settles without overshoot, the same shape as `--ease-settle`. */
const SETTLE = [0.22, 0.61, 0.36, 1] as const;

function shouldPlay(): boolean {
  if (typeof window === 'undefined') return false;
  if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return false;
  try {
    return window.sessionStorage.getItem(SEEN_KEY) === null;
  } catch {
    // Storage blocked. Playing once per load is the better failure than never.
    return true;
  }
}

export function BootLoader() {
  const [playing, setPlaying] = useState(shouldPlay);

  useEffect(() => {
    if (!playing) return;
    try {
      window.sessionStorage.setItem(SEEN_KEY, '1');
    } catch {
      // Nothing to do, the loader simply plays again next load.
    }
    const t = window.setTimeout(() => setPlaying(false), LIFT_AT_MS);
    return () => window.clearTimeout(t);
  }, [playing]);

  // The page beneath is live the whole time; the plate only has to stop the
  // scroll position drifting under it while it is up.
  useEffect(() => {
    if (!playing) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = prev;
    };
  }, [playing]);

  return (
    <AnimatePresence>
      {playing && (
        <motion.div
          key="boot"
          className="fixed inset-0 z-[100] flex flex-col items-center justify-center gap-[24px] bg-bond"
          initial={{ opacity: 1 }}
          exit={{ opacity: 0, y: -14 }}
          transition={{ duration: 0.4, ease: SETTLE }}
        >
          <span className="sr-only">Loading Mandate</span>

          <div
            aria-hidden
            className="pointer-events-none absolute inset-0"
            style={{
              backgroundImage:
                'radial-gradient(circle at 1px 1px, var(--color-rule) 1px, transparent 0)',
              backgroundSize: '22px 22px',
              maskImage: 'radial-gradient(50% 54% at 50% 50%, #000 0%, transparent 76%)',
              WebkitMaskImage: 'radial-gradient(50% 54% at 50% 50%, #000 0%, transparent 76%)',
            }}
          />

          {/* The mark, assembling. Same 40x40 geometry as `MandateMark`, so the
              plate resolves into exactly the logo that sits in the nav a
              moment later, the post exists first, then the order arrives and
              goes through it, which is the order those two things happen in. */}
          <svg
            aria-hidden
            width="62"
            height="62"
            viewBox="0 0 40 40"
            fill="none"
            className="relative"
          >
            <motion.rect
              x="25.6"
              y="3.6"
              width="6.2"
              height="13"
              rx="2.4"
              fill="var(--color-navy)"
              style={{ transformBox: 'fill-box', transformOrigin: 'bottom' }}
              initial={{ scaleY: 0, opacity: 0 }}
              animate={{ scaleY: 1, opacity: 1 }}
              transition={{ duration: 0.35, delay: 0.1, ease: SETTLE }}
            />
            <motion.rect
              x="25.6"
              y="23.4"
              width="6.2"
              height="13"
              rx="2.4"
              fill="var(--color-navy)"
              style={{ transformBox: 'fill-box', transformOrigin: 'top' }}
              initial={{ scaleY: 0, opacity: 0 }}
              animate={{ scaleY: 1, opacity: 1 }}
              transition={{ duration: 0.35, delay: 0.1, ease: SETTLE }}
            />
            <motion.path
              d="M4 20h25.4"
              stroke="var(--color-indigo)"
              strokeWidth="3.6"
              strokeLinecap="round"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{
                duration: 0.5,
                delay: 0.42,
                ease: SETTLE,
                opacity: { duration: 0.12, delay: 0.42 },
              }}
            />
          </svg>

          <motion.div
            aria-hidden
            className="relative flex items-center gap-[11px]"
            initial={{ opacity: 0, y: 9 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, delay: 0.85, ease: SETTLE }}
          >
            <span className="text-[31px] font-semibold tracking-[-0.05em] text-navy">Mandate</span>
            <span className="h-[21px] w-px bg-rule" />
            <span className="text-[16px] tracking-[-0.02em] text-ink-3">by Razorpay</span>
          </motion.div>

          <div aria-hidden className="relative h-[2px] w-[208px] rounded-full bg-rule-soft">
            <motion.span
              className="absolute inset-y-0 left-0 rounded-full bg-indigo"
              initial={{ width: 0 }}
              animate={{ width: '100%' }}
              transition={{ duration: 0.5, delay: 1.1, ease: 'linear' }}
            />
          </div>

          <motion.div
            aria-hidden
            className="relative flex items-center gap-[7px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3, delay: 1.45 }}
          >
            <span className="size-[5px] rounded-full bg-pass" />
            <span className="font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-3">
              policy loaded · {PARTS.length} clauses
            </span>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
