import { useEffect, useRef, useState } from 'react';
import {
  motion,
  type MotionStyle,
  type MotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useScroll,
  useTransform,
} from 'motion/react';
import { ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { CAP_AT, fillPercent, readoutFor } from '@/lib/headroom';
import { rupees } from '@/lib/money';
import { LIMITS, PARTS, RULES } from '@/data/policy';
import { SCENARIOS } from '@/data/scenarios';
import { cn } from '@/lib/utils';
import GatewayPanel from './GatewayPanel';
import { SellerChip } from './SellerMark';

/**
 * The hero's magic moment: an order that already got refused, sitting quiet
 * beside the copy. Scrolling doesn't navigate away from it — it pulls that
 * same refusal open into the interactive gateway, so the thing you read
 * about in the headline is the thing you're now looking inside of.
 *
 * Built on scroll-linked motion values rather than a scroll-jacking library,
 * because the rest of this app is Motion end to end and a second animation
 * engine for one section isn't worth the bundle or the seam. Below `lg`, or
 * under reduced motion, the pin never engages — `Static` renders the same
 * copy beside the plain interactive panel, which is what shipped before this.
 */

const FACTS = [
  {
    term: 'The parts',
    lead: `${LIMITS.length} limits, ${RULES.length} rules.`,
    rest: `A closed set of ${LIMITS.length + RULES.length}.`,
  },
  {
    term: 'Precedence',
    lead: 'Refuse beats unknown beats allow.',
    rest: 'Nothing passes by default.',
  },
  { term: 'Credentials', lead: 'Your agent holds none.', rest: 'Only a handle to the gateway.' },
];

/** The teaser freezes on the injection attack: it's the sharpest single refusal in the corpus. */
const TEASER = SCENARIOS[0];
const TEASER_PART = PARTS[1];
const TEASER_READOUT = readoutFor(TEASER_PART, TEASER.load[1] ?? 0);
const TEASER_FILL = fillPercent(TEASER.load[1] ?? 0, CAP_AT);

/**
 * Mirrors a MotionValue into React state as a plain number.
 *
 * Every other CSS property here (`x`, `filter`, grid tracks) animates fine
 * as a raw MotionValue passed straight to `style`. `opacity` specifically
 * does not: in this Motion build, a `motion.div` never repaints its own
 * `style.opacity` from a subscribed MotionValue, even though the value
 * itself updates correctly and the same element's other style keys do
 * update. Routing it through React state sidesteps whatever internal path
 * is dropping it, at the cost of a re-render per scroll tick instead of a
 * direct DOM write — an acceptable trade for one hero section.
 */
function useSyncedNumber(value: MotionValue<number>) {
  const [n, setN] = useState(() => value.get());
  useMotionValueEvent(value, 'change', setN);
  return n;
}

function useIsLgViewport() {
  const [isLg, setIsLg] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia('(min-width: 1024px)');
    setIsLg(mq.matches);
    const onChange = (e: MediaQueryListEvent) => setIsLg(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);
  return isLg;
}

function Copy({ opacity, style }: { opacity?: number; style?: MotionStyle }) {
  return (
    <motion.div className="min-w-0" style={{ opacity, ...style }}>
      <span className="inline-flex items-center gap-2 rounded-full border border-rule bg-bond px-[13px] py-[6px] font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
        <span className="size-[6px] rotate-45 bg-halt" />
        nine parts · checked in order
      </span>

      <h1 className="mt-[22px] text-balance text-[clamp(2.15rem,4.2vw,3.45rem)] font-semibold leading-[1.05] tracking-[-0.048em]">
        A limit does not need to be persuaded.{' '}
        <span className="text-ink-3">It stops at the number you set.</span>
      </h1>

      <p className="mt-[22px] max-w-[32rem] text-[17px] leading-[1.62] text-ink-2">
        Mandate turns what you actually meant into a signed set of limits, then checks every
        order your agent tries to place against them in plain code.{' '}
        <b className="font-medium text-ink">
          A language model reads your words exactly once, and you approve the result.
        </b>{' '}
        After that it never gets a vote on whether money moves.
      </p>

      <div className="mt-8 flex flex-wrap gap-[10px]">
        <Button asChild size="lg" className="h-[38px] rounded-lg px-4 text-[13.5px]">
          <a href="/dashboard">
            Open the console
            <ArrowRight className="size-[14px]" />
          </a>
        </Button>
        <Button
          asChild
          variant="outline"
          size="lg"
          className="h-[38px] rounded-lg border-rule px-4 text-[13.5px] hover:bg-sheet"
        >
          <a href="#limits">See the nine limits</a>
        </Button>
      </div>

      <dl className="mt-[42px] grid gap-5 border-t border-rule pt-[22px] sm:grid-cols-3">
        {FACTS.map((f) => (
          <div key={f.term}>
            <dt className="mb-[6px] font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
              {f.term}
            </dt>
            <dd className="text-[13px] leading-[1.5] text-ink-2">
              <b className="font-medium text-ink">{f.lead}</b> {f.rest}
            </dd>
          </div>
        ))}
      </dl>
    </motion.div>
  );
}

/** The refusal, already settled — the state the interactive panel will replay once opened. */
function Teaser() {
  return (
    <div className="flex h-full flex-col overflow-hidden rounded-panel border border-rule bg-bond shadow-lift">
      <div className="flex h-11 items-center gap-3 border-b border-rule bg-sheet px-5">
        <span className="font-mono text-[10px] font-medium uppercase tracking-[0.12em] text-ink-2">
          Mandate Gateway
        </span>
        <span className="ml-auto inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.08em] text-pass">
          <span className="size-[6px] rounded-full bg-pass ring-[3px] ring-pass/15" />
          enforcing
        </span>
      </div>

      <div className="flex flex-1 flex-col justify-center gap-4 px-6 py-6">
        <div>
          <div className="font-mono text-[9.5px] uppercase tracking-[0.14em] text-ink-3">
            Order in flight
          </div>
          <div className="mt-3 flex items-center gap-[10px]">
            <SellerChip name={TEASER.seller} />
            <span className="rounded-md border border-rule bg-sheet px-2 py-0.5 font-mono text-[10.5px] text-ink-3">
              place_order
            </span>
          </div>
          <div className="mt-3 rounded-lg border border-hair bg-sunk px-3.5 py-2.5 font-mono text-[11.5px] leading-[1.68] text-ink-2 break-words">
            {TEASER.payload.map((seg, k) => (
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

        <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-4">
          <div>
            <div className="mb-2 font-mono text-[9.5px] uppercase tracking-[0.12em] text-ink-3">
              The agent asked for
            </div>
            <div className="font-mono text-[clamp(26px,2.6vw,38px)] font-semibold leading-none tracking-[-0.05em] text-halt">
              {rupees(TEASER.amountPaise)}
            </div>
          </div>
          <div className="h-full w-px self-stretch bg-rule" />
          <div>
            <div className="mb-2 font-mono text-[9.5px] uppercase tracking-[0.12em] text-ink-3">
              Your limit says
            </div>
            <div className="font-mono text-[clamp(26px,2.6vw,38px)] font-semibold leading-none tracking-[-0.05em]">
              {TEASER_PART.bound}
            </div>
          </div>
        </div>

        <div>
          <div className="relative h-4 overflow-hidden rounded-[5px] border border-hair bg-sunk">
            <div
              className="absolute inset-y-0 left-0 rounded-l-[4px] bg-halt"
              style={{ width: `${Math.min(TEASER_FILL, 100)}%` }}
            />
            <span
              aria-hidden
              className="absolute inset-y-0 right-0 border-l border-ink/20"
              style={{
                left: `${CAP_AT}%`,
                backgroundImage:
                  'repeating-linear-gradient(45deg, var(--color-halt-soft) 0 4px, transparent 4px 8px)',
              }}
            />
          </div>
          <div className="mt-[7px] flex justify-between font-mono text-[10.5px] text-ink-3">
            <span>
              part {TEASER_PART.n} · {TEASER_PART.label.toLowerCase()}
            </span>
            <span className="text-halt">{TEASER_READOUT?.figure ?? ''}</span>
          </div>
        </div>
      </div>

      <div className="border-t border-rule bg-halt-soft px-6 py-4">
        <div className="flex items-center gap-[10px]">
          <span className="size-[9px] rotate-45 bg-halt" />
          <span className="font-mono text-[14px] font-semibold tracking-[0.06em] text-halt">
            REFUSED
          </span>
          <span className="ml-auto font-mono text-[11px] font-medium text-halt">
            ₹0.00 charged
          </span>
        </div>
        <p className="mt-[7px] text-[13px] leading-[1.5] tracking-[-0.012em] text-ink-2">
          {TEASER.summary}
        </p>
      </div>

      <div className="flex h-11 items-center justify-center gap-[9px] border-t border-rule font-mono text-[10.5px] uppercase tracking-[0.12em] text-ink-3">
        scroll · open the gateway
        <motion.span
          animate={{ y: [0, 4, 0] }}
          transition={{ duration: 1.7, repeat: Infinity, ease: 'easeInOut' }}
        >
          ↓
        </motion.span>
      </div>
    </div>
  );
}

/** The `lg`, motion-enabled path: copy fades away, the teaser opens into the live panel. */
function Scrubbed() {
  const stageRef = useRef<HTMLDivElement>(null);
  const { scrollYProgress } = useScroll({
    target: stageRef,
    offset: ['start start', 'end end'],
  });

  // Paced scroll timeline with generous runway so the user doesn't blow past the transition
  const copyOpacity = useTransform(scrollYProgress, [0.12, 0.46], [1, 0]);
  const copyOpacityValue = useSyncedNumber(copyOpacity);
  const copyX = useTransform(scrollYProgress, [0.12, 0.46], [0, -56]);
  const copyBlur = useTransform(scrollYProgress, [0.12, 0.46], [0, 6]);
  const copyFilter = useTransform(copyBlur, (b) => `blur(${b}px)`);

  const leftPct = useTransform(scrollYProgress, [0.18, 0.68], [47.5, 0]);
  const gridTemplateColumns = useTransform(leftPct, (l) => `${l}% ${100 - l}%`);
  const gap = useTransform(scrollYProgress, [0.18, 0.68], [56, 0]);
  const columnGap = useTransform(gap, (g) => `${g}px`);

  const teaserOpacity = useTransform(scrollYProgress, [0.25, 0.52], [1, 0]);
  const teaserOpacityValue = useSyncedNumber(teaserOpacity);
  const fullOpacity = useTransform(scrollYProgress, [0.48, 0.74], [0, 1]);
  const fullOpacityValue = useSyncedNumber(fullOpacity);

  const labelOpacity = useTransform(scrollYProgress, [0.70, 0.88], [0, 1]);
  const labelOpacityValue = useSyncedNumber(labelOpacity);

  const teaserInteractive = teaserOpacityValue > 0.5;

  return (
    <div ref={stageRef} className="relative" style={{ height: 'calc(320vh - 60px)' }}>
      <div className="sticky top-[60px] h-[calc(100vh-60px)] overflow-hidden">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0"
          style={{
            backgroundImage:
              'radial-gradient(circle at 1px 1px, var(--color-rule) 1px, transparent 0)',
            backgroundSize: '22px 22px',
            maskImage: 'radial-gradient(120% 80% at 18% 0%, #000 0%, transparent 70%)',
            WebkitMaskImage: 'radial-gradient(120% 80% at 18% 0%, #000 0%, transparent 70%)',
          }}
        />

        <div
          className="absolute left-8 top-[84px] flex items-center gap-3"
          style={{ opacity: labelOpacityValue }}
        >
          <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
            02 · the gateway, open
          </span>
          <span className="h-px w-[52px] bg-rule" />
          <span className="hidden font-mono text-[10px] tracking-[0.06em] text-ink-4 xl:inline">
            pick an order — watch the nine parts run
          </span>
        </div>

        <motion.div
          className="mx-auto grid h-full max-w-[1220px] items-center px-8"
          style={{ gridTemplateColumns, columnGap }}
        >
          <div className="min-w-0 overflow-hidden">
            <Copy opacity={copyOpacityValue} style={{ x: copyX, filter: copyFilter }} />
          </div>

          <div className="relative h-[600px] min-w-0 xl:h-[640px]">
            <div
              className="absolute inset-0"
              style={{ opacity: teaserOpacityValue, pointerEvents: teaserInteractive ? 'auto' : 'none' }}
            >
              <Teaser />
            </div>
            <div
              className="absolute inset-0 overflow-y-auto"
              style={{ opacity: fullOpacityValue, pointerEvents: teaserInteractive ? 'none' : 'auto' }}
            >
              <GatewayPanel />
            </div>
          </div>
        </motion.div>
      </div>
    </div>
  );
}

/** Below `lg`, and under reduced motion: no pin, the panel is simply already open. */
function Static() {
  return (
    <div className="mx-auto grid max-w-[1220px] grid-cols-1 items-start gap-14 px-8 pb-[84px] pt-[72px] max-sm:px-[18px] lg:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)] max-lg:pb-[60px] max-lg:pt-[52px]">
      <Copy />
      <div>
        <GatewayPanel />
      </div>
    </div>
  );
}

export default function HeroScrollStage() {
  const reduced = useReducedMotion();
  const isLg = useIsLgViewport();

  return (
    <section className="relative border-b border-rule">
      {!reduced && isLg ? <Scrubbed /> : <Static />}
    </section>
  );
}
