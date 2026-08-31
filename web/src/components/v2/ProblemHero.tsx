import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PARTS } from '@/data/policy';
import { SCENARIOS } from '@/data/scenarios';
import { SCOREBOARD, SOURCE } from '@/data/decisions';
import { rupees } from '@/lib/money';
import { cn } from '@/lib/utils';

/**
 * The hero states the problem and nothing else.
 *
 * One beam runs left to right: you, the agent, the rail, your card. It goes in
 * blue carrying a limit and comes out red carrying an amount, because in the
 * middle a seller wrote into the context the agent was reading. The gateway is
 * not on this screen on purpose — the section below it is the answer, and an
 * answer shown before the question lands as a feature list.
 *
 * Every figure is read, never typed. The bounds come from `PARTS`, which
 * `evidence.json` fills from the signed policy; the overrun is the same
 * `injection.description` load the gateway panel below runs, so the hero and
 * the panel are telling one story about one order rather than two about two;
 * and the containment line is the measured baseline from the scored run. The
 * one number that would have been retyped here — a rupee figure from a
 * different result directory — is the one this deliberately does not use.
 */

const TOTAL_CAP = PARTS.find((p) => p.key === 'budget.total');
const ATTACK = SCENARIOS[0];

/** The baseline arm's miss rate, stated as a count. A percentage over 18 runs
 *  implies a precision the interval does not support. */
const BASELINE = SCOREBOARD.containment.baseline;
const UNCONTAINED = BASELINE.total - BASELINE.contained;

interface Node {
  label: string;
  figure: string;
  caption: string;
  tone: 'ink' | 'halt';
}

const NODES: Node[] = [
  {
    label: 'you',
    figure: TOTAL_CAP?.bound ?? '',
    caption: 'the limit you set',
    tone: 'ink',
  },
  {
    label: 'the agent',
    figure: 'basket rewritten',
    caption: 'it read the seller’s page',
    tone: 'halt',
  },
  {
    label: 'the rail',
    figure: 'cap · merchant · expiry',
    caption: 'the three it can check',
    tone: 'ink',
  },
  {
    label: 'your card',
    figure: rupees(ATTACK.amountPaise),
    caption: 'charged, uncontained',
    tone: 'halt',
  },
];

/** Node centres, as a fraction of the track's own width. */
const CENTRE = ['12.5%', '37.5%', '62.5%', '87.5%'];

/** One loop of the beam, in seconds. Long enough to read, short enough to
 *  catch twice while scanning the headline. */
const LOOP = 4.2;
const RUN_A = 1.15;
const RUN_B = 1.9;
const START_B = 1.25;

function Beam({
  left,
  width,
  colour,
  delay,
  duration,
  reduced,
}: {
  left: string;
  width: string;
  colour: string;
  delay: number;
  duration: number;
  reduced: boolean;
}) {
  if (reduced) return null;
  return (
    <span className="absolute inset-y-0 overflow-hidden" style={{ left, width }}>
      <motion.span
        className="absolute top-1/2 h-[7px] w-[40%] -translate-y-1/2 rounded-full"
        style={{ background: `linear-gradient(90deg, transparent 0%, ${colour} 100%)` }}
        initial={{ x: '-100%', opacity: 0 }}
        animate={{ x: '250%', opacity: [0, 1, 1, 0] }}
        transition={{
          duration,
          delay,
          ease: 'linear',
          times: [0, 0.12, 0.82, 1],
          repeat: Infinity,
          repeatDelay: LOOP - duration,
        }}
      />
    </span>
  );
}

export default function ProblemHero() {
  const reduced = useReducedMotion() ?? false;

  return (
    <section className="relative border-b border-rule">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0"
        style={{
          backgroundImage:
            'radial-gradient(circle at 1px 1px, var(--color-rule) 1px, transparent 0)',
          backgroundSize: '22px 22px',
          maskImage: 'radial-gradient(78% 44% at 50% 64%, #000 0%, transparent 72%)',
          WebkitMaskImage: 'radial-gradient(78% 44% at 50% 64%, #000 0%, transparent 72%)',
        }}
      />

      <div className="relative mx-auto flex max-w-[1220px] flex-col items-center px-8 pb-[56px] pt-[58px] max-sm:px-[18px] max-md:pb-12 max-md:pt-11">
        <span className="inline-flex items-center gap-2 rounded-full border border-rule bg-bond px-[13px] py-[6px] font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
          <span className="size-[6px] rotate-45 bg-halt" />
          the problem
        </span>

        <h1 className="mt-[20px] max-w-[30ch] text-balance text-center text-[clamp(2.05rem,4.4vw,3.6rem)] font-semibold leading-[1.04] tracking-[-0.048em]">
          You said “under {TOTAL_CAP?.bound.replace('.00', '')}”.{' '}
          <span className="text-ink-3">A seller wrote the rest.</span>
        </h1>

        <p className="mt-[18px] max-w-[40rem] text-center text-[17px] leading-[1.62] text-ink-2">
          Between your words and your money sits a language model reading text that a seller
          controls. The rail checks a cap, a merchant and an expiry.{' '}
          <b className="font-medium text-ink">
            Everything else you meant is a sentence in a system prompt
          </b>{' '}
          — and the prompt is not what the attacker is writing into.
        </p>

        {/* ── The rail, wide ─────────────────────────────────────────────── */}
        <div className="mt-[38px] hidden w-full max-w-[1100px] lg:block">
          <div className="relative">
            {/* What the agent read. Anchored over the agent node. */}
            <div className="relative mb-3 w-[42%]" style={{ marginLeft: '16.5%' }}>
              <div className="rounded-[10px] border border-halt-line bg-halt-soft px-[15px] py-[13px]">
                <div className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-halt">
                  seller-controlled text · product description
                </div>
                <p className="mt-2 font-mono text-[11.5px] leading-[1.6] text-ink-2">
                  {ATTACK.payload.map((seg, k) => (
                    <span key={k} className={cn(seg.hostile && 'font-medium text-halt')}>
                      {seg.text}
                    </span>
                  ))}
                </p>
              </div>
              <span
                aria-hidden
                className="absolute left-1/2 top-full h-[28px] w-px"
                style={{
                  backgroundImage:
                    'repeating-linear-gradient(var(--color-halt-line) 0 4px, transparent 4px 8px)',
                }}
              />
            </div>

            <div className="mt-[28px] grid grid-cols-4 gap-x-3">
              {NODES.map((n) => (
                <div key={n.label} className="text-center">
                  <span
                    className={cn(
                      'font-mono text-[10px] uppercase tracking-[0.12em]',
                      n.tone === 'halt' ? 'text-halt' : 'text-ink-3',
                    )}
                  >
                    {n.label}
                  </span>
                </div>
              ))}
            </div>

            {/* The track. Markers sit on it, so the line lives in this strip. */}
            <div className="relative mt-[14px] h-5">
              <span
                aria-hidden
                className="absolute top-1/2 h-[2px] -translate-y-1/2 bg-rule-soft"
                style={{ left: CENTRE[0], right: CENTRE[0] }}
              />
              <span
                aria-hidden
                className="absolute top-1/2 h-[2px] -translate-y-1/2 bg-indigo opacity-30"
                style={{ left: CENTRE[0], width: '25%' }}
              />
              <span
                aria-hidden
                className="absolute top-1/2 h-[2px] -translate-y-1/2 bg-halt opacity-30"
                style={{ left: CENTRE[1], width: '50%' }}
              />

              <Beam
                left={CENTRE[0]}
                width="25%"
                colour="#2F5EFF"
                delay={0}
                duration={RUN_A}
                reduced={reduced}
              />
              <Beam
                left={CENTRE[1]}
                width="50%"
                colour="#B42318"
                delay={START_B}
                duration={RUN_B}
                reduced={reduced}
              />

              {NODES.map((n, i) => (
                <span
                  key={n.label}
                  aria-hidden
                  className={cn(
                    'absolute top-1/2 size-[13px] -translate-x-1/2 -translate-y-1/2 rounded-[3px] shadow-[0_0_0_5px_var(--color-bond)]',
                    n.tone === 'halt' ? 'bg-halt' : 'bg-navy',
                  )}
                  style={{ left: CENTRE[i] }}
                />
              ))}
            </div>

            <div className="mt-[18px] grid grid-cols-4 gap-x-3">
              {NODES.map((n, i) => (
                <div key={n.label} className="text-center">
                  <div
                    className={cn(
                      'font-mono font-medium leading-none tracking-[-0.03em]',
                      i === NODES.length - 1
                        ? 'text-[clamp(20px,2vw,27px)] font-semibold'
                        : 'text-[15px]',
                      n.tone === 'halt' ? 'text-halt' : 'text-ink',
                    )}
                  >
                    {n.figure}
                  </div>
                  <div
                    className={cn(
                      'mt-[7px] text-[11.5px] leading-[1.4]',
                      n.tone === 'halt' ? 'text-halt' : 'text-ink-3',
                    )}
                  >
                    {n.caption}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* ── The rail, narrow. Same four beats, stacked. ─────────────────── */}
        <ol className="mt-9 w-full max-w-[26rem] lg:hidden">
          {NODES.map((n, i) => (
            <li key={n.label} className="relative flex gap-[14px] pb-6 last:pb-0">
              {i < NODES.length - 1 && (
                <span
                  aria-hidden
                  className={cn(
                    'absolute bottom-0 left-[6px] top-[16px] w-[2px]',
                    i === 0 ? 'bg-indigo/30' : 'bg-halt/30',
                  )}
                />
              )}
              <span
                aria-hidden
                className={cn(
                  'relative mt-[3px] size-[13px] shrink-0 rounded-[3px]',
                  n.tone === 'halt' ? 'bg-halt' : 'bg-navy',
                )}
              />
              <div className="min-w-0">
                <span
                  className={cn(
                    'font-mono text-[10px] uppercase tracking-[0.12em]',
                    n.tone === 'halt' ? 'text-halt' : 'text-ink-3',
                  )}
                >
                  {n.label}
                </span>
                <div
                  className={cn(
                    'mt-[5px] font-mono text-[17px] font-medium tracking-[-0.03em]',
                    n.tone === 'halt' ? 'text-halt' : 'text-ink',
                  )}
                >
                  {n.figure}
                </div>
                <div className="mt-[3px] text-[12px] leading-[1.45] text-ink-3">{n.caption}</div>
                {i === 1 && (
                  <p className="mt-[10px] rounded-[9px] border border-halt-line bg-halt-soft px-3 py-2.5 font-mono text-[11px] leading-[1.6] text-ink-2">
                    {ATTACK.payload.map((seg, k) => (
                      <span key={k} className={cn(seg.hostile && 'font-medium text-halt')}>
                        {seg.text}
                      </span>
                    ))}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ol>

        <div className="mt-[34px] flex flex-wrap items-center justify-center gap-x-[18px] gap-y-3">
          <Button asChild size="lg" className="h-[42px] rounded-[9px] px-5 text-[14px]">
            <a href="#gap">
              See what stops it
              <ArrowRight className="size-[14px]" />
            </a>
          </Button>
          <a
            href="#how"
            className="border-b border-rule pb-[2px] text-[14px] text-ink-2 transition-colors hover:text-ink"
          >
            How this was measured
          </a>
        </div>

        <p className="mt-[22px] text-center font-mono text-[10.5px] leading-[1.7] tracking-[0.04em] text-ink-4">
          load · {ATTACK.family} · with no gateway, {UNCONTAINED} of {BASELINE.total} held-out
          attacks executed
          <br className="sm:hidden" />
          <span className="max-sm:hidden"> · </span>
          {SOURCE.model} · {SOURCE.containment_dir}
        </p>
      </div>
    </section>
  );
}
