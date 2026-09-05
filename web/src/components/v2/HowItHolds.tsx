import { useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Sparkles, PenTool, Cpu, Database, Lock, AlertTriangle, XOctagon, CheckSquare } from 'lucide-react';
import { cn } from '@/lib/utils';
import { MANDATE, PART_COUNT_TEXT, SET_PART_COUNT, SET_PART_COUNT_TEXT } from '@/data/policy';
import LatticeStage from './LatticeStage';

type LatticeVerdict = 'allow' | 'unknown' | 'deny';

const STAGES = [
  {
    n: '01',
    title: 'Compile',
    subtitle: 'Model · temp 0',
    icon: Sparkles,
    body: `What you said becomes a fixed set of limits. The compiler marks what it heard against what it proposed, and refuses rather than approximating an intent that does not fit the ${PART_COUNT_TEXT} types.`,
    note: 'runs once · never asked again',
    actor: 'gemini-3.7-flash',
    isModel: true,
    hoverBorder: 'hover:border-indigo',
    hoverGlow: 'from-indigo-soft/80',
    iconHover: 'group-hover/stage:text-indigo group-hover/stage:bg-indigo-soft/80',
  },
  {
    n: '02',
    title: 'Read & Sign',
    subtitle: 'You',
    icon: PenTool,
    body: 'You read your limits in plain language and sign them. Consent attaches to something checkable, not to prose. Signing fixes the policy hash forever.',
    note: `policy hash · ${MANDATE.policyHash.slice(0, 8)}…${MANDATE.policyHash.slice(-4)}`,
    actor: 'user_local',
    isModel: false,
    hoverBorder: 'hover:border-ink',
    hoverGlow: 'from-sunk/80',
    iconHover: 'group-hover/stage:text-ink group-hover/stage:bg-sunk',
  },
  {
    n: '03',
    title: 'Enforce',
    subtitle: 'Pure deterministic code',
    icon: Cpu,
    body: `Every proposed order goes through the ${SET_PART_COUNT_TEXT} parts this mandate sets, in pure functions with no I/O and no model. Allow and pay, refuse and say which limit, or escalate when unresolved.`,
    note: '0.0075 ms · no LLMs in payment path',
    actor: 'deterministic gateway',
    isModel: false,
    hoverBorder: 'hover:border-pass',
    hoverGlow: 'from-pass-soft/90',
    iconHover: 'group-hover/stage:text-pass group-hover/stage:bg-pass-soft',
  },
  {
    n: '04',
    title: 'Log',
    subtitle: 'Append-only ledger',
    icon: Database,
    body: 'Every decision enters a hash-chained log. Editing an earlier entry breaks every hash after it, so the record is tamper-evident rather than merely stored.',
    note: 'sha-256 · chained · replayable',
    actor: 'audit.jsonl ledger',
    isModel: false,
    hoverBorder: 'hover:border-refer',
    hoverGlow: 'from-refer-soft/80',
    iconHover: 'group-hover/stage:text-refer group-hover/stage:bg-refer-soft',
  },
];

export default function HowItHolds() {
  const reduced = useReducedMotion();
  const [selectedVerdict, setSelectedVerdict] = useState<LatticeVerdict>('allow');

  const DURATION = 3.6;

  return (
    <section id="how" className="border-b border-rule bg-bond py-20">
      <div className="mx-auto max-w-[1220px] px-8 max-sm:px-[18px]">
        
        {/* Section Header */}
        <div className="flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div className="max-w-[38rem]">
            <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3">
              Execution Architecture
            </span>
            <h2 className="mt-2 text-balance text-[clamp(1.85rem,3.2vw,2.5rem)] font-semibold leading-[1.1] tracking-[-0.04em] text-ink">
              The model sits upstream of the money,{' '}
              <span className="text-ink-3">and it goes there once.</span>
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-ink-2">
              Compiling is where interpretation is allowed to happen. Enforcing is where it is not.
              A language model translates your intent once, and human consent fixes the policy hash forever.
            </p>
          </div>

          <div className="flex items-center gap-2 rounded-xl border border-rule bg-sheet px-3.5 py-2 self-start md:self-auto font-mono text-[11px] text-ink-2">
            <span className="size-2 rounded-full bg-pass" />
            <span>Payment path: <b>Zero LLMs · Pure Code</b></span>
          </div>
        </div>

        {/* 4-Stage Connected Track */}
        <div className="relative mt-14">
          
          {/* Laser conduit beam */}
          <div className="relative mb-6 hidden md:block">
            <div className="h-[2px] w-full bg-rule relative overflow-hidden rounded-full">
              <motion.div
                className="absolute top-0 bottom-0 left-0 w-1/3 bg-gradient-to-r from-transparent via-indigo to-transparent"
                animate={reduced ? {} : { x: ['-100%', '300%'] }}
                transition={{ repeat: Infinity, duration: 2.8, ease: 'linear' }}
              />
            </div>
          </div>

          {/* Model Air-Gap Marker */}
          <div className="absolute -top-3.5 left-1/2 -translate-x-1/2 hidden lg:flex items-center gap-1.5 px-3.5 py-0.5 rounded-full bg-ink text-bond text-[10px] font-mono z-20 shadow-sheet">
            <Lock className="size-3 text-pass" />
            <span>MODEL AIR-GAP · ZERO LLMS IN PAYMENT PATH</span>
          </div>

          {/* 4 Stage Cards */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {STAGES.map((s) => {
              const Icon = s.icon;

              return (
                <div
                  key={s.title}
                  className={cn(
                    'group/stage relative flex flex-col justify-between rounded-xl border border-rule bg-bond p-6 shadow-xs transition-all duration-300',
                    'hover:shadow-sheet hover:-translate-y-0.5 overflow-hidden',
                    s.hoverBorder,
                    s.isModel && 'bg-sheet/50'
                  )}
                >
                  {/* Subtle directional hover gradient */}
                  <div
                    className={cn(
                      'pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover/stage:opacity-100 bg-gradient-to-b to-transparent',
                      s.hoverGlow
                    )}
                  />

                  <div className="relative z-10">
                    <div className="flex items-center justify-between mb-4">
                      <div className="flex items-center gap-2">
                        <div
                          className={cn(
                            'flex size-7 items-center justify-center rounded-md border border-rule bg-sunk text-ink transition-colors duration-200',
                            s.iconHover
                          )}
                        >
                          <Icon className="size-3.5" />
                        </div>
                        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-3">
                          Stage {s.n}
                        </span>
                      </div>
                      <span className="font-mono text-[10.5px] text-ink-3">{s.subtitle}</span>
                    </div>

                    <h3 className="text-[16px] font-semibold tracking-[-0.02em] text-ink transition-transform duration-200 group-hover/stage:translate-x-0.5">
                      {s.title}
                    </h3>
                    <p className="mt-2 text-[12.5px] leading-relaxed text-ink-2">
                      {s.body}
                    </p>
                  </div>

                  <div className="relative z-10 mt-6 border-t border-rule-soft pt-3 flex items-center justify-between font-mono text-[11px]">
                    <span className="text-ink-3 truncate max-w-[130px]">{s.note}</span>
                    <span className="font-medium text-ink-2">{s.actor}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* REFINED 2-COLUMN PRECEDENCE LATTICE & SYNCHRONIZED BEAM */}
        <div className="mt-20 overflow-hidden rounded-2xl border border-rule bg-sheet p-8 lg:p-12 shadow-xs">
          <div className="grid grid-cols-1 items-start gap-10 lg:grid-cols-12 lg:gap-14">
            
            {/* LEFT COLUMN: Traveling Beam with Synchronized Card Glows (7 Cols) */}
            <div className="relative lg:col-span-7">
              <div className="relative overflow-hidden rounded-2xl border border-rule bg-bond p-6 shadow-xs sm:p-8">
                
                {/* Circuit Header */}
                <div className="mb-6 flex items-center justify-between border-b border-rule-soft pb-4">
                  <div className="flex items-center gap-2">
                    <span className="size-2 rounded-full bg-ink" />
                    <span className="font-mono text-xs font-semibold uppercase tracking-wider text-ink">
                      Order Evaluation Lattice
                    </span>
                  </div>
                  <span className="font-mono text-[11px] text-ink-3">
                    A refusal beats a hold. <b>A hold beats an approval.</b>
                  </span>
                </div>

                {/* Vertical Circuit with Traveling Beam */}
                <div className="relative space-y-4">
                  
                  {/* The Conduit Line with Continuous Traveling Laser Ray */}
                  <div className="pointer-events-none absolute bottom-8 left-6 top-8 w-[3px] bg-rule-soft rounded-full overflow-hidden">
                    <motion.div
                      className="h-24 w-full rounded-full bg-gradient-to-b from-halt via-refer to-pass"
                      animate={reduced ? {} : { y: ['-30%', '330%'] }}
                      transition={{
                        repeat: Infinity,
                        duration: DURATION,
                        ease: 'easeInOut',
                      }}
                    />
                  </div>

                  {/* GATE 1: DENY (Subtle red ground when ray is at top) */}
                  <motion.div
                    onClick={() => setSelectedVerdict('deny')}
                    whileHover={{ scale: 1.01 }}
                    animate={
                      reduced
                        ? {}
                        : {
                            borderColor: ['#b42318', '#e4e3df', '#e4e3df', '#b42318'],
                            backgroundColor: ['#fdf1ef', '#ffffff', '#ffffff', '#fdf1ef'],
                          }
                    }
                    transition={{
                      repeat: Infinity,
                      duration: DURATION,
                      times: [0, 0.32, 0.92, 1],
                      ease: 'easeInOut',
                    }}
                    className={cn(
                      'relative z-10 flex cursor-pointer items-start gap-4 rounded-xl border p-4.5 transition-all duration-300',
                      selectedVerdict === 'deny' ? 'ring-2 ring-halt/30' : ''
                    )}
                  >
                    <div className="flex size-11 flex-shrink-0 items-center justify-center rounded-xl border border-halt-line bg-halt-soft text-halt shadow-xs">
                      <XOctagon className="size-5" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-bold tracking-wider text-halt">
                          1. DENY GATE
                        </span>
                        <span className="rounded bg-sunk px-2 py-0.5 font-mono text-[10px] uppercase text-ink-3">
                          Highest Precedence
                        </span>
                      </div>
                      <div className="mt-1 text-[13.5px] font-semibold text-ink">
                        Refuse and cite limit
                      </div>
                      <p className="mt-0.5 text-[12px] leading-relaxed text-ink-2">
                        If ANY single limit fails, execution aborts before the payment rail is ever reached. No model call, no network round trip. Pure deterministic code.
                      </p>
                    </div>
                  </motion.div>

                  {/* Connector Badge */}
                  <div className="relative z-10 flex justify-center -my-1.5">
                    <span className="rounded border border-rule bg-sheet px-2.5 py-0.5 font-mono text-[10.5px] text-ink-3">
                      &#8826; if not denied
                    </span>
                  </div>

                  {/* GATE 2: UNKNOWN (Subtle amber ground when ray is in middle) */}
                  <motion.div
                    onClick={() => setSelectedVerdict('unknown')}
                    whileHover={{ scale: 1.01 }}
                    animate={
                      reduced
                        ? {}
                        : {
                            borderColor: ['#e4e3df', '#8a5a05', '#e4e3df', '#e4e3df'],
                            backgroundColor: ['#ffffff', '#fbf4e7', '#ffffff', '#ffffff'],
                          }
                    }
                    transition={{
                      repeat: Infinity,
                      duration: DURATION,
                      times: [0, 0.42, 0.68, 1],
                      ease: 'easeInOut',
                    }}
                    className={cn(
                      'relative z-10 flex cursor-pointer items-start gap-4 rounded-xl border p-4.5 transition-all duration-300',
                      selectedVerdict === 'unknown' ? 'ring-2 ring-refer/30' : ''
                    )}
                  >
                    <div className="flex size-11 flex-shrink-0 items-center justify-center rounded-xl border border-refer-line bg-refer-soft text-refer shadow-xs">
                      <AlertTriangle className="size-5" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <span className="font-mono text-xs font-bold tracking-wider text-refer">
                          2. UNKNOWN GATE
                        </span>
                        <span className="rounded bg-sunk px-2 py-0.5 font-mono text-[10px] uppercase text-ink-3">
                          Medium Precedence
                        </span>
                      </div>
                      <div className="mt-1 text-[13.5px] font-semibold text-ink">
                        Escalate to person
                      </div>
                      <p className="mt-0.5 text-[12px] leading-relaxed text-ink-2">
                        Unseen merchants or taxonomy ambiguity trigger human approval. Never falls through to allowed.
                      </p>
                    </div>
                  </motion.div>

                  {/* Connector Badge */}
                  <div className="relative z-10 flex justify-center -my-1.5">
                    <span className="rounded border border-rule bg-sheet px-2.5 py-0.5 font-mono text-[10.5px] text-ink-3">
                      &#8826; if resolved
                    </span>
                  </div>

                  {/* GATE 3: ALLOW (Soft emerald ground when ray arrives at bottom) */}
                  <motion.div
                    onClick={() => setSelectedVerdict('allow')}
                    whileHover={{ scale: 1.01 }}
                    animate={
                      reduced
                        ? {}
                        : {
                            borderColor: ['#e4e3df', '#e4e3df', '#0e7c56', '#e4e3df'],
                            backgroundColor: ['#ffffff', '#ffffff', '#edf7f2', '#ffffff'],
                          }
                    }
                    transition={{
                      repeat: Infinity,
                      duration: DURATION,
                      times: [0, 0.65, 0.88, 1],
                      ease: 'easeInOut',
                    }}
                    className={cn(
                      'relative z-10 flex cursor-pointer items-start gap-4 rounded-xl border p-5 transition-all duration-300',
                      selectedVerdict === 'allow' ? 'ring-2 ring-pass/30' : ''
                    )}
                  >
                    <div className="flex size-12 flex-shrink-0 items-center justify-center rounded-xl border border-pass-line bg-pass-soft text-pass shadow-xs">
                      <CheckSquare className="size-6" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-sm font-bold tracking-wider text-pass">
                            3. ALLOW (PAY)
                          </span>
                          <span className="size-2 rounded-full bg-pass animate-ping" />
                        </div>
                        <span className="rounded bg-pass-soft px-2 py-0.5 font-mono text-[10.5px] font-semibold text-pass">
                          {SET_PART_COUNT}/{SET_PART_COUNT} Verified
                        </span>
                      </div>
                      <div className="mt-1 text-[14px] font-semibold text-ink">
                        Authorize UPI reserve & move funds
                      </div>
                      <p className="mt-0.5 text-[12px] leading-relaxed text-ink-2">
                        All {SET_PART_COUNT_TEXT} policy bounds pass without objection. Order
                        executes deterministically.
                      </p>
                    </div>
                  </motion.div>

                </div>

                {/* Bottom Circuit Telemetry */}
                <div className="mt-6 flex items-center justify-between border-t border-rule-soft pt-4 font-mono text-[11px] text-ink-2">
                  <span className="flex items-center gap-1.5">
                    <span className="size-2 rounded-full bg-pass" /> Constant-time termination O(1)
                  </span>
                  {/* Measured, not asserted: 2,000 warm calls of `Gateway.propose()`
                      against `FakeDownstream`, 31 Aug. Clause evaluation is the
                      0.0075 ms; the rest of the median is audit persistence and the
                      downstream call. The tile said "< 0.38ms" before, which was the
                      third invented latency to reach this interface after the README
                      badge and the "slowest check 1.4 ms" dashboard tile. */}
                  <span className="text-ink-3">
                    {SET_PART_COUNT} clauses: 0.0075&#8239;ms &middot; full call: 4.9&#8239;ms median
                  </span>
                </div>

              </div>
            </div>

            {/* RIGHT COLUMN: Editorial Narrative & Formatted Deterministic Code (5 Cols) */}
            <div className="space-y-6 lg:col-span-5">
              <div>
                <span className="font-mono text-xs font-semibold uppercase tracking-wider text-pass">
                  Precedence Invariant
                </span>
                <h3 className="mt-1.5 text-2xl font-bold leading-tight tracking-[-0.035em] text-ink md:text-3xl">
                  A refusal stops everything. An unknown comes to you.
                </h3>
                <p className="mt-3 text-[14.5px] leading-relaxed text-ink-2">
                  Each part answers <b>allow</b>, <b>refuse</b> or <b>unknown</b>. They combine
                  on a strict mathematical lattice rather than a probabilistic score.
                </p>
                <p className="mt-2 text-[14.5px] font-medium leading-relaxed text-ink">
                  Rules fail closed; judging fails open.
                </p>
              </div>

              {/*
                The gates have been clickable since this was built and selecting
                one moved a ring and nothing else. The middle gate claimed that
                anything unresolved waits for a person while the product showed
                that approval nowhere, so this is where the escalation lands.
              */}
              <LatticeStage verdict={selectedVerdict} />

              {/* Formatted Code Block (Guaranteed clean wrapping) */}
              <div className="overflow-hidden rounded-xl border border-rule bg-bond p-5 shadow-xs font-mono text-xs">
                <div className="flex items-center justify-between border-b border-rule-soft pb-3 text-[11px] text-ink-3">
                  <span>lattice.py</span>
                  <span className="font-semibold text-pass">bounded · terminating</span>
                </div>
                <div className="mt-3 space-y-1 text-xs leading-relaxed text-ink">
                  <div className="text-ink-3 italic"># Deny beats unknown beats allow</div>
                  <div className="pt-1">
                    <span className="font-semibold text-indigo">if</span> any(DENY):
                  </div>
                  <div className="pl-4">
                    <span className="font-semibold text-indigo">return</span>{' '}
                    <span className="font-bold text-halt">DENY</span>
                    <span className="ml-2 text-ink-3"># refuse & cite</span>
                  </div>
                  <div className="pt-1">
                    <span className="font-semibold text-indigo">elif</span> any(UNKNOWN):
                  </div>
                  <div className="pl-4">
                    <span className="font-semibold text-indigo">return</span>{' '}
                    <span className="font-bold text-refer">UNKNOWN</span>
                    <span className="ml-2 text-ink-3"># escalate</span>
                  </div>
                  <div className="pt-1">
                    <span className="font-semibold text-indigo">else</span>:
                  </div>
                  <div className="pl-4">
                    <span className="font-semibold text-indigo">return</span>{' '}
                    <span className="font-bold text-pass">ALLOW</span>
                    <span className="ml-2 text-ink-3"># pay</span>
                  </div>
                </div>
              </div>

              {/* Strict Guarantees List */}
              <div className="space-y-2.5 font-mono text-xs text-ink-2">
                <div className="flex items-center gap-2.5 rounded-lg border border-rule bg-bond p-3 shadow-2xs">
                  <span className="size-1.5 rounded-full bg-pass flex-shrink-0" />
                  <span><b>Amounts are whole paise:</b> Zero floating-point errors.</span>
                </div>
                <div className="flex items-center gap-2.5 rounded-lg border border-rule bg-bond p-3 shadow-2xs">
                  <span className="size-1.5 rounded-full bg-pass flex-shrink-0" />
                  <span><b>Rupees only:</b> Foreign currencies refused, never converted.</span>
                </div>
              </div>

            </div>

          </div>
        </div>

      </div>
    </section>
  );
}
