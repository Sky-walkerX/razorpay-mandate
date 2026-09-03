import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight, Check, Minus, AlertTriangle, CircleDashed } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { MandateLockup } from '@/components/brand/MandateLockup';
import {
  FATES, RAILS, REQUIREMENTS, POSTURE, CITATIONS, UAP,
  RESERVE_PAY, AP2_EXPORT, MANDATE_ID, POLICY_HASH,
} from '@/data/alignment';
import type { Fate, Status } from '@/data/alignment';
import { cn } from '@/lib/utils';
import { PART_COUNT } from '@/data/policy';

/**
 * Section: where this policy lives on the rails, and under the regulation.
 *
 * The argument the page makes, in order:
 *
 *   1. A person states more than a rail can hold. Every clause goes in; AP2 keeps
 *      five structurally, Reserve Pay keeps three. The remainder does not
 *      disappear, it becomes prose in a description nothing evaluates.
 *   2. That subtraction is concrete, not rhetorical: three allowed merchants
 *      become one payee, and two are dropped on the floor.
 *   3. Against the regulation the same honesty applies in the other direction —
 *      one requirement is a flat gap and it is on the page in the same weight as
 *      the ones that are met.
 *
 * Every figure is read from `@/data/alignment`, which reads `evidence.json`.
 * Nothing here is typed by hand, on purpose: a compliance table is the one
 * artefact nobody diffs against the code, so it is the one most likely to drift
 * into wishful thinking.
 *
 * Colour follows the house rule — the three meaning inks never carry meaning
 * alone. Every fate and every status appears with a glyph and a word beside it.
 */

/* ── the vocabulary, rendered ─────────────────────────────────────────────── */

const FATE_STYLE: Record<Fate, { label: string; cls: string; Icon: typeof Check }> = {
  ap2: { label: 'Structural', cls: 'text-pass bg-pass-soft border-pass-line', Icon: Check },
  rail: { label: 'On the rail', cls: 'text-pass bg-pass-soft border-pass-line', Icon: Check },
  prose: { label: 'Prose only', cls: 'text-refer bg-refer-soft border-refer-line', Icon: CircleDashed },
  none: { label: 'Nowhere', cls: 'text-halt bg-halt-soft border-halt-line', Icon: Minus },
};

const STATUS_STYLE: Record<Status, { label: string; cls: string; Icon: typeof Check }> = {
  held: { label: 'Held', cls: 'text-pass bg-pass-soft border-pass-line', Icon: Check },
  partial: { label: 'Partial', cls: 'text-refer bg-refer-soft border-refer-line', Icon: CircleDashed },
  gap: { label: 'Gap', cls: 'text-halt bg-halt-soft border-halt-line', Icon: AlertTriangle },
  out_of_scope: { label: 'Not ours', cls: 'text-ink-3 bg-sunk border-rule', Icon: Minus },
};

function Chip({ style }: { style: { label: string; cls: string; Icon: typeof Check } }) {
  const { label, cls, Icon } = style;
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-[5px] rounded-full border py-[3px] pl-[7px] pr-[9px]',
        'font-mono text-[9.5px] uppercase tracking-[0.08em]',
        // Fixed box, so the note beside it starts at the same x on every row.
        // Without it the chip is only as wide as its label — "NOWHERE" against
        // "ON THE RAIL" — and the note column acquires a 26px ragged left edge
        // that reads as sloppiness rather than as the deliberate table it is.
        'min-w-[104px]',
        cls,
      )}
    >
      <Icon aria-hidden className="size-[10px]" strokeWidth={2.4} />
      {label}
    </span>
  );
}

/* ── the counter that carries the argument ───────────────────────────────── */

function Tally({
  held, total, rail, sub, delay, reduced,
}: {
  held: number; total: number; rail: string; sub: string; delay: number; reduced: boolean;
}) {
  return (
    <motion.div
      className="flex-1 rounded-panel border border-rule bg-raise p-6 shadow-sheet max-sm:p-5"
      initial={reduced ? false : { opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.4, delay, ease: [0.22, 0.61, 0.36, 1] }}
    >
      <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">{rail}</div>
      <div className="mt-3 flex items-baseline gap-[3px]">
        <span className="font-mono text-[42px] leading-none tracking-[-0.02em] text-ink">{held}</span>
        <span className="font-mono text-[22px] leading-none text-ink-4">/{total}</span>
      </div>
      <div className="mt-2.5 text-[13px] leading-[1.5] text-ink-2">{sub}</div>
      {/* The bar is the subtraction made visible: filled is what survives. The
          cubic is the house no-overshoot curve; --ease-settle is a CSS linear()
          and Motion's `ease` does not take one. */}
      <div className="mt-4 flex gap-[3px]" aria-hidden>
        {Array.from({ length: total }, (_, i) => (
          <motion.span
            key={i}
            className={cn('h-[6px] flex-1 rounded-sm', i < held ? 'bg-indigo' : 'bg-rule')}
            initial={reduced ? false : { opacity: 0, scaleY: 0.3 }}
            whileInView={{ opacity: 1, scaleY: 1 }}
            viewport={{ once: true }}
            transition={{ duration: 0.3, delay: delay + 0.1 + i * 0.03, ease: [0.22, 0.61, 0.36, 1] }}
          />
        ))}
      </div>
    </motion.div>
  );
}

/* ── page ─────────────────────────────────────────────────────────────────── */

export default function Alignment() {
  const reduced = useReducedMotion() ?? false;
  const rbi = CITATIONS.rbi_emandate_2026;
  const uap = CITATIONS.npci_uap;

  /* Of the clauses in this mandate, most came from the user's sentence and the
     rest are imposed. Saying "a person states nine conditions" would be the
     overstatement this project exists to catch: two of them nobody asked for. */
  const stated = FATES.filter((f) => f.statedByUser).length;
  const imposed = FATES.length - stated;
  /* The regulator's own clauses are not privileged on a rail. Whether any of
     them survive is computed, not assumed, because it is the sharpest line on
     the page and would be the worst one to get wrong. */
  const imposedLost = FATES.filter(
    (f) => !f.statedByUser && f.reservePay === 'none',
  );

  return (
    <div data-v2 className="min-h-screen bg-bond font-sans text-ink">
      <nav className="sticky top-0 z-50 border-b border-rule bg-bond/85 backdrop-blur-[12px]">
        <div className="mx-auto flex h-[60px] max-w-[1100px] items-center gap-[26px] px-8 max-sm:px-[18px]">
          <Link to="/" aria-label="Mandate, by Razorpay">
            <MandateLockup />
          </Link>
          <div className="ml-3 hidden gap-[22px] text-[13.5px] text-ink-2 lg:flex">
            <a href="#rails" className="transition-colors hover:text-ink">On the rails</a>
            <a href="#regulation" className="transition-colors hover:text-ink">Under the regulation</a>
            <a href="#export" className="transition-colors hover:text-ink">Export</a>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <Button asChild variant="outline" size="sm" className="h-[38px] rounded-lg px-3.5 text-[13px]">
              <Link to="/">Home</Link>
            </Button>
            <Button asChild size="sm" className="h-[38px] rounded-lg bg-[#2F5EFF] px-4 text-[13.5px] text-white shadow-2xs hover:bg-[#254ED0]">
              <Link to="/try">Try it live →</Link>
            </Button>
          </div>
        </div>
      </nav>

      {/* 1100 is the frame /store and /dashboard already use, so the lockup and
          the content edge do not move when you navigate between them. The home
          page sits at 1220 and is left alone. */}
      <main className="mx-auto max-w-[1100px] px-8 pb-24 max-sm:px-[18px]">
        {/* ── the claim ─────────────────────────────────────────────────── */}
        <header className="border-b border-rule py-14 max-sm:py-10">
          <div className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
            Rails &amp; regulation · {MANDATE_ID}
          </div>
          <h1 className="mt-4 max-w-[820px] text-[38px] font-medium leading-[1.12] tracking-[-0.02em] text-ink max-sm:text-[27px]">
            {stated} conditions from a person, {imposed} from the regulator. The rail
            carries {RAILS.reservePayHeld}.
          </h1>
          <p className="mt-5 max-w-[680px] text-[15px] leading-[1.6] text-ink-2">
            Spending limits for agents already ship. UPI Reserve Pay blocks an amount
            against one merchant until an expiry, and that is the entire vocabulary. This
            page is the subtraction: which clauses of a signed mandate survive each rail,
            which survive only as words in a description nothing evaluates, and which have
            nowhere to go at all. It is computed from the signed policy, not written about it.
          </p>
          {imposedLost.length > 0 && (
            <p className="mt-4 max-w-[680px] text-[15px] leading-[1.6] text-ink-2">
              The subtraction does not spare the regulator.{' '}
              {imposedLost.map((f, i) => (
                <span key={f.clause}>
                  {i > 0 && ' and '}
                  <span className="font-mono text-[13px] text-ink">{f.clause}</span>
                </span>
              ))}{' '}
              {imposedLost.length === 1 ? 'is' : 'are'} imposed by RBI and{' '}
              {imposedLost.length === 1 ? 'has' : 'have'} nowhere to sit on Reserve Pay
              either — a block is authorised once at the front, so there is no per-debit
              step-up inside it. Enforcing that clause is the gateway's job because the
              rail has no place to keep it.
            </p>
          )}
          <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 font-mono text-[10.5px] text-ink-3">
            <span>sha256:{POLICY_HASH.slice(0, 24)}…</span>
            <span className="text-ink-4">·</span>
            <span>computed by mandate.policy.rails</span>
          </div>
        </header>

        {/* ── the two tallies ───────────────────────────────────────────── */}
        <section id="rails" className="scroll-mt-[76px] py-12">
          <div className="flex gap-4 max-md:flex-col">
            <Tally
              rail="AP2 · Open Checkout Mandate"
              held={RAILS.ap2Held}
              total={RAILS.totalClauses}
              sub={`${RAILS.ap2Held} clauses map to a structured field or a Payment Mandate constraint. ${RAILS.ap2Prose} survive only as prose inside natural_language_description. ${RAILS.ap2Lost - RAILS.ap2Prose} have no representation at all.`}
              delay={0}
              reduced={reduced}
            />
            <Tally
              rail="UPI Reserve Pay · live today"
              held={RAILS.reservePayHeld}
              total={RAILS.totalClauses}
              sub={`An amount, a payee and an expiry. The rail never sees a line item, a category or a quantity, so ${RAILS.reservePayLost} clauses have nowhere to sit.`}
              delay={0.08}
              reduced={reduced}
            />
          </div>

          {/* The concrete instance of the subtraction, which beats the count. */}
          <motion.div
            className="mt-4 rounded-panel border border-refer-line bg-refer-soft px-6 py-5 max-sm:px-5"
            initial={reduced ? false : { opacity: 0, y: 10 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{ duration: 0.4, delay: 0.16, ease: [0.22, 0.61, 0.36, 1] }}
          >
            <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-refer">
              What the count looks like in practice
            </div>
            <p className="mt-2.5 text-[13.5px] leading-[1.55] text-ink-2">
              This mandate allows {1 + RESERVE_PAY.overflow.length} sellers. A Reserve Pay
              block names one payee, so the projection keeps{' '}
              <span className="font-mono text-ink">{RESERVE_PAY.payee}</span> and reports{' '}
              {RESERVE_PAY.overflow.map((m, i) => (
                <span key={m}>
                  {i > 0 && ' and '}
                  <span className="font-mono text-halt line-through decoration-halt-line">{m}</span>
                </span>
              ))}{' '}
              as dropped rather than collapsing the list quietly to its first element. Two
              merchants the user named would be unreachable, and nothing on the rail would
              say so.
            </p>
          </motion.div>

          {/* ── clause by clause ────────────────────────────────────────── */}
          <div className="mt-10 overflow-hidden rounded-panel border border-rule bg-raise shadow-sheet">
            <div className="grid grid-cols-[minmax(150px,1.1fr)_minmax(0,1.35fr)_minmax(0,1.35fr)] items-center gap-x-5 border-b border-rule bg-sheet px-6 py-3 font-mono text-[9.5px] uppercase tracking-[0.09em] text-ink-3 max-md:grid-cols-1 max-md:gap-y-1 max-sm:px-5">
              <span>Clause</span>
              <span className="max-md:hidden">AP2</span>
              <span className="max-md:hidden">UPI Reserve Pay</span>
            </div>
            {FATES.map((f, i) => (
              <motion.div
                key={f.clause}
                className="grid grid-cols-[minmax(150px,1.1fr)_minmax(0,1.35fr)_minmax(0,1.35fr)] items-start gap-x-5 border-b border-hair px-6 py-[13px] last:border-b-0 max-md:grid-cols-1 max-md:gap-y-2.5 max-sm:px-5"
                initial={reduced ? false : { opacity: 0, x: -6 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: '-40px' }}
                transition={{ duration: 0.32, delay: Math.min(i * 0.03, 0.3), ease: [0.22, 0.61, 0.36, 1] }}
              >
                <div className="pt-[1px]">
                  <div className="text-[13.5px] leading-[1.4] text-ink">{f.label}</div>
                  <div className="mt-[3px] flex items-center gap-2">
                    <span className="font-mono text-[10px] text-ink-4">{f.clause}</span>
                    {!f.statedByUser && (
                      <span className="font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3">
                        imposed
                      </span>
                    )}
                  </div>
                </div>
                {/* Below md the column headers are gone and the two fates stack, so
                    each carries its own rail name there or the reader cannot tell
                    which verdict belongs to which rail. */}
                <div className="flex items-start gap-2.5">
                  <span className="hidden shrink-0 pt-[3px] font-mono text-[9.5px] uppercase tracking-[0.09em] text-ink-4 max-md:inline">
                    AP2
                  </span>
                  <Chip style={FATE_STYLE[f.ap2]} />
                  <span className="text-[12.5px] leading-[1.45] text-ink-2">{f.ap2Note}</span>
                </div>
                <div className="flex items-start gap-2.5">
                  <span className="hidden shrink-0 pt-[3px] font-mono text-[9.5px] uppercase tracking-[0.09em] text-ink-4 max-md:inline">
                    RSV
                  </span>
                  <Chip style={FATE_STYLE[f.reservePay]} />
                  <span className="text-[12.5px] leading-[1.45] text-ink-2">{f.reservePayNote}</span>
                </div>
              </motion.div>
            ))}
          </div>
          <p className="mt-3 max-w-[820px] text-[12.5px] leading-[1.5] text-ink-3">
            AP2 is richer than an amount plus an expiry and this page says so. Overstating
            the gap would be the same failure the project exists to catch. The table covers
            the {RAILS.totalClauses} clauses this mandate carries. The gateway implements{' '}
            {PART_COUNT} kinds in total; <span className="font-mono">item.deny_recent</span>{' '}
            is the one this policy does not set, which is why the loader counts {PART_COUNT}{' '}
            and this page {RAILS.totalClauses}.
          </p>
        </section>

        {/* ── the regulation ────────────────────────────────────────────── */}
        <section id="regulation" className="scroll-mt-[76px] border-t border-rule py-12">
          <h2 className="text-[26px] font-medium leading-[1.2] tracking-[-0.015em] text-ink max-sm:text-[21px]">
            Under the regulation
          </h2>
          <p className="mt-4 max-w-[680px] text-[15px] leading-[1.6] text-ink-2">
            The table above asks whether a rail can carry our clause. This one asks the
            opposite question — whether we carry a regulator's obligation — and the two are
            kept apart because &ldquo;held&rdquo; would otherwise mean two different things
            in adjacent columns. <span className="text-ink">Not ours</span> and{' '}
            <span className="text-ink">gap</span> are different claims: the first says the
            obligation lands on an issuer or a bank, the second says it is ours and unmet.
          </p>

          <div className="mt-6 flex flex-wrap gap-2.5">
            {([
              ['held', POSTURE.held],
              ['partial', POSTURE.partial],
              ['gap', POSTURE.gaps],
              ['out_of_scope', POSTURE.outOfScope],
            ] as [Status, number][]).map(([s, n]) => (
              <span
                key={s}
                className={cn(
                  'inline-flex items-center gap-2 rounded-lg border px-3 py-[7px] font-mono text-[11px]',
                  STATUS_STYLE[s].cls,
                )}
              >
                <span className="text-[15px] leading-none">{n}</span>
                <span className="uppercase tracking-[0.07em]">{STATUS_STYLE[s].label}</span>
              </span>
            ))}
          </div>

          <div className="mt-3 font-mono text-[10.5px] leading-[1.6] text-ink-3">
            {rbi.title} · issued {rbi.issued} · checked {rbi.checked}
          </div>

          <div className="mt-7 space-y-3">
            {REQUIREMENTS.map((r, i) => (
              <motion.article
                key={r.key}
                className={cn(
                  'rounded-panel border bg-raise p-5 shadow-sheet max-sm:p-[18px]',
                  r.status === 'gap' ? 'border-halt-line' : 'border-rule',
                )}
                initial={reduced ? false : { opacity: 0, y: 8 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true, margin: '-50px' }}
                transition={{ duration: 0.34, delay: Math.min(i * 0.035, 0.28), ease: [0.22, 0.61, 0.36, 1] }}
              >
                <div className="flex items-start justify-between gap-4">
                  <p className="max-w-[720px] text-[14px] font-medium leading-[1.5] text-ink">
                    {r.requirement}
                  </p>
                  <Chip style={STATUS_STYLE[r.status]} />
                </div>
                <p className="mt-2.5 max-w-[820px] text-[13px] leading-[1.55] text-ink-2">
                  {r.mechanism}
                </p>
                {r.clause && (
                  <div className="mt-3 inline-flex items-center gap-[6px] rounded-md border border-rule bg-sunk px-2 py-[3px] font-mono text-[10px] text-ink-2">
                    <ArrowRight aria-hidden className="size-[10px]" />
                    {r.clause}
                  </div>
                )}
              </motion.article>
            ))}
          </div>
        </section>

        {/* ── the protocol nobody has read ──────────────────────────────── */}
        <section className="border-t border-rule py-12">
          <h2 className="text-[26px] font-medium leading-[1.2] tracking-[-0.015em] text-ink max-sm:text-[21px]">
            NPCI's Unified Agent Protocol
          </h2>
          <div className="mt-5 rounded-panel border border-rule bg-sunk p-6 max-sm:p-5">
            <div className="flex items-center gap-2.5">
              <Chip style={{ label: 'Unpublished', cls: 'text-ink-3 bg-bond border-rule', Icon: CircleDashed }} />
              <span className="font-mono text-[10.5px] text-ink-3">
                {uap.note} · checked {uap.checked}
              </span>
            </div>
            <p className="mt-4 max-w-[820px] text-[14px] leading-[1.6] text-ink-2">{UAP}</p>
          </div>
        </section>

        {/* ── the export ────────────────────────────────────────────────── */}
        <section id="export" className="scroll-mt-[76px] border-t border-rule py-12">
          <h2 className="text-[26px] font-medium leading-[1.2] tracking-[-0.015em] text-ink max-sm:text-[21px]">
            The mandate, as AP2 sees it
          </h2>
          <p className="mt-4 max-w-[680px] text-[15px] leading-[1.6] text-ink-2">
            The gateway renders the same signed policy as an AP2 v0.2 credential. The{' '}
            {RAILS.ap2Lost} clauses AP2 cannot hold structurally do not vanish from it — they
            end up inside{' '}
            <span className="font-mono text-[13px] text-ink">natural_language_description</span>,
            as the user's own sentence, where nothing downstream evaluates them. That field
            is the gap, printed, so it is printed here rather than left to scroll off the
            edge of a JSON panel.
          </p>

          <div className="mt-6 rounded-panel border border-refer-line bg-refer-soft px-6 py-5 max-sm:px-5">
            <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-refer">
              natural_language_description · carried, not evaluated
            </div>
            <p className="mt-3 max-w-[880px] text-[15px] leading-[1.65] text-ink">
              “{AP2_EXPORT.intentMandate.natural_language_description}”
            </p>
            <p className="mt-3 max-w-[880px] text-[12.5px] leading-[1.5] text-ink-2">
              Every clause in the table above marked <span className="text-refer">prose only</span>{' '}
              lives in this string and nowhere else. A rail that receives it has the words
              and no way to act on them; this gateway compiled the same sentence into
              clauses it evaluates on every order.
            </p>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-4 max-md:grid-cols-1">
            <div className="overflow-hidden rounded-panel border border-rule bg-raise shadow-sheet">
              <div className="border-b border-rule bg-sheet px-5 py-2.5 font-mono text-[9.5px] uppercase tracking-[0.09em] text-ink-3">
                IntentMandate
              </div>
              <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words px-5 py-4 font-mono text-[11.5px] leading-[1.65] text-ink-2">
{JSON.stringify(AP2_EXPORT.intentMandate, null, 2)}
              </pre>
            </div>
            <div className="overflow-hidden rounded-panel border border-rule bg-raise shadow-sheet">
              <div className="border-b border-rule bg-sheet px-5 py-2.5 font-mono text-[9.5px] uppercase tracking-[0.09em] text-ink-3">
                Payment Mandate constraints · {AP2_EXPORT.paymentConstraints.length}
              </div>
              <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words px-5 py-4 font-mono text-[11.5px] leading-[1.65] text-ink-2">
{JSON.stringify(AP2_EXPORT.paymentConstraints, null, 2)}
              </pre>
            </div>
          </div>

          <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-2 rounded-panel border border-rule bg-sheet px-5 py-4 font-mono text-[11.5px] text-ink-2">
            <span className="text-ink-3">Reproduce it:</span>
            <span className="text-ink">{AP2_EXPORT.cli}</span>
            <span className="text-ink-4">·</span>
            <a
              href={AP2_EXPORT.endpoint}
              className="text-indigo underline-offset-2 hover:underline"
            >
              GET {AP2_EXPORT.endpoint}
            </a>
          </div>
        </section>
      </main>

      <footer className="mx-auto flex max-w-[1100px] flex-wrap items-center justify-between gap-4 border-t border-rule px-8 py-7 text-[12.5px] text-ink-3 max-sm:px-[18px]">
        <span>Mandate · rails and regulation, computed from the signed policy</span>
        <span>Citations checked {rbi.checked}. Statuses are code, not marketing.</span>
      </footer>
    </div>
  );
}
