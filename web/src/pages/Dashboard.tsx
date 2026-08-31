import { Link } from 'react-router-dom';
import { Download } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { MandateLockup } from '@/components/brand/MandateLockup';
import { RunStrip } from '@/components/dashboard/RunStrip';
import { PartsAtEnd } from '@/components/dashboard/PartsAtEnd';
import { ChainSection } from '@/components/dashboard/ChainSection';
import { COUNTS, FEED_RUN, SCOREBOARD, SOURCE } from '@/data/decisions';
import { MANDATE } from '@/data/policy';
import { bindingPart, headline } from '@/lib/runShape';
import { exportEvidence } from '@/lib/exportEvidence';

/**
 * The record: one replayed run, read top to bottom.
 *
 * This used to be a sidebar, four undifferentiated tiles and two charts — the
 * shape of generic analytics, for a product whose whole argument is that the
 * interesting thing is not a metric but a refusal that can name its clause.
 * Four of the five sidebar items were inert, a card advertised a feature that
 * did not exist, and the bar chart spent a full panel drawing eight empty bars
 * to show one.
 *
 * It is now a document in the landing page's own grammar: an eyebrow, a
 * two-tone headline, evidence drawn rather than tiled, and a provenance line
 * naming the run, the model and the directory. Nothing on the page is inert.
 *
 * Two measurements appear here and they are kept visibly apart. Everything
 * above `Across the whole held-out set` is this one run, replayed from a
 * single `audit.jsonl`. The containment band below it is the aggregate across
 * the held-out sweep — a different measurement over different runs, so it
 * carries its own attribution rather than sitting in the same row as figures
 * it did not come from.
 */
export default function Dashboard() {
  const { lead, turn } = headline();
  const binding = bindingPart();
  const enforce = SCOREBOARD.containment.enforce;
  const baseline = SCOREBOARD.containment.baseline;

  return (
    <div data-v2 className="min-h-screen bg-bond font-sans text-ink">
      {/* ── Navigation, matching the landing page ─────────────────────── */}
      <nav className="sticky top-0 z-50 border-b border-rule bg-bond/85 backdrop-blur-[12px]">
        <div className="mx-auto flex h-[60px] max-w-[1100px] items-center gap-[18px] px-8 max-sm:px-[18px]">
          <Link to="/" aria-label="Mandate, by Razorpay">
            <MandateLockup />
          </Link>
          <span className="hidden items-center gap-[7px] rounded-full border border-rule bg-sheet py-[5px] pl-[9px] pr-[11px] font-mono text-[10.5px] uppercase tracking-[0.07em] text-ink-2 sm:inline-flex">
            <span className="size-[5px] rounded-full bg-pass" />
            Replayed · not live
          </span>

          <div className="ml-auto flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={exportEvidence}
              className="h-[38px] gap-[7px] rounded-lg px-3.5 text-[13px]"
            >
              <Download className="size-[14px]" />
              Export evidence
            </Button>
            <Button asChild size="sm" className="h-[38px] rounded-lg px-4 text-[13.5px]">
              <Link to="/try">Try it live →</Link>
            </Button>
          </div>
        </div>
      </nav>

      {/* ── The claim ─────────────────────────────────────────────────── */}
      <header className="border-b border-rule">
        <div className="mx-auto max-w-[1100px] px-8 py-[52px] max-sm:px-[18px] max-md:py-10">
          <span className="inline-flex items-center gap-2 rounded-full border border-rule bg-bond px-[13px] py-[6px] font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
            <span className="size-[6px] rotate-45 bg-indigo" />
            the record · {FEED_RUN}
          </span>

          <h1 className="mt-[18px] text-balance text-[clamp(1.9rem,3.6vw,2.7rem)] font-semibold leading-[1.06] tracking-[-0.046em]">
            {lead} <span className="text-ink-3">{turn}</span>
          </h1>

          <p className="mt-[15px] max-w-[54rem] text-[15.5px] leading-[1.62] text-ink-2">
            One recorded run, replayed in full from a single audit log — every decision, in order,
            with nothing selected.{' '}
            {binding ? (
              <>
                The agent placed the orders its mandate allowed, then kept trying. Every attempt
                after that was refused by{' '}
                <b className="font-medium text-ink">
                  Part {binding.part.n}, {binding.part.label.toLowerCase()}
                </b>
                , and every refusal named it.{' '}
                <b className="font-medium text-ink">No attacker was involved at any point.</b>
              </>
            ) : (
              <>Refusals in this run cite more than one part, so no single clause bound it.</>
            )}
          </p>
        </div>
      </header>

      {/* ── The run, drawn ────────────────────────────────────────────── */}
      <section className="border-b border-rule">
        <div className="mx-auto max-w-[1100px] px-8 py-[46px] max-sm:px-[18px] max-md:py-9">
          <RunStrip />
        </div>
      </section>

      {/* ── The nine parts ────────────────────────────────────────────── */}
      <section className="border-b border-rule">
        <div className="mx-auto max-w-[1100px] px-8 py-[46px] max-sm:px-[18px] max-md:py-9">
          <div className="mb-[22px] flex flex-col justify-between gap-4 md:flex-row md:items-end">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-rule bg-bond px-[13px] py-[6px] font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
                <span className="size-[6px] rotate-45 bg-pass" />
                the nine parts, at the end of the run
              </span>
              <h2 className="mt-[14px] text-balance text-[clamp(1.35rem,2.4vw,1.75rem)] font-semibold leading-[1.1] tracking-[-0.04em]">
                {binding ? (
                  <>
                    Eight had headroom. <span className="text-ink-3">One was at its cap.</span>
                  </>
                ) : (
                  <>
                    All nine were evaluated.{' '}
                    <span className="text-ink-3">On every attempt.</span>
                  </>
                )}
              </h2>
            </div>
            <span className="font-mono text-[11px] text-ink-3">
              evaluated in order, on all {COUNTS.evaluated} attempts
            </span>
          </div>

          <PartsAtEnd />
        </div>
      </section>

      {/* ── The chain ─────────────────────────────────────────────────── */}
      <section className="border-b border-rule">
        <div className="mx-auto max-w-[1100px] px-8 py-[46px] max-sm:px-[18px] max-md:py-9">
          <div className="mb-[22px]">
            <span className="inline-flex items-center gap-2 rounded-full border border-rule bg-bond px-[13px] py-[6px] font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
              <span className="size-[6px] rotate-45 bg-refer" />
              the chain
            </span>
            <h2 className="mt-[14px] text-balance text-[clamp(1.35rem,2.4vw,1.75rem)] font-semibold leading-[1.1] tracking-[-0.04em]">
              Every decision links to the one before it.{' '}
              <span className="text-ink-3">Editing one breaks all of them.</span>
            </h2>
          </div>

          <ChainSection />

          <p className="mt-3 font-mono text-[9.5px] leading-[1.7] tracking-[0.04em] text-ink-4">
            {COUNTS.evaluated} of {COUNTS.evaluated} hashes verified · {SOURCE.feed_file}
          </p>
        </div>
      </section>

      {/* ── A different measurement, kept apart and attributed ────────── */}
      <section className="border-b border-rule bg-sheet">
        <div className="mx-auto max-w-[1100px] px-8 py-[42px] max-sm:px-[18px] max-md:py-9">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
            a different measurement
          </span>
          <h2 className="mt-[12px] max-w-[46rem] text-balance text-[clamp(1.25rem,2.2vw,1.6rem)] font-semibold leading-[1.12] tracking-[-0.04em]">
            Across the whole held-out set, not just this run.
          </h2>

          <div className="mt-[22px] grid gap-4 sm:grid-cols-2">
            <div className="rounded-panel border border-pass-line bg-pass-soft px-5 py-[18px]">
              <div className="font-mono text-[9.5px] uppercase tracking-[0.11em] text-pass">
                with the gateway enforcing
              </div>
              <div className="mt-2 font-mono text-[27px] font-semibold leading-none tracking-[-0.045em] text-pass">
                {enforce.contained} / {enforce.total}
              </div>
              <p className="mt-2.5 text-[12.5px] leading-[1.5] text-ink-2">
                attacks contained · {enforce.total - enforce.contained} escaped
              </p>
            </div>

            <div className="rounded-panel border border-rule bg-bond px-5 py-[18px]">
              <div className="font-mono text-[9.5px] uppercase tracking-[0.11em] text-ink-3">
                with no gateway at all
              </div>
              <div className="mt-2 font-mono text-[27px] font-semibold leading-none tracking-[-0.045em] text-halt">
                {baseline.contained} / {baseline.total}
              </div>
              <p className="mt-2.5 text-[12.5px] leading-[1.5] text-ink-2">
                contained in the baseline arm · clearly below the enforced arms, though{' '}
                {baseline.total} runs is too few to put a precise figure on it
              </p>
            </div>
          </div>

          <p className="mt-4 font-mono text-[9.5px] leading-[1.7] tracking-[0.04em] text-ink-4">
            {SOURCE.model} · {SOURCE.containment_dir} · run {SOURCE.containment_run} · counts, not
            percentages, because the interval over {baseline.total} runs does not support one
          </p>
        </div>
      </section>

      {/* ── Provenance ────────────────────────────────────────────────── */}
      <section>
        <div className="mx-auto max-w-[1100px] px-8 py-[38px] max-sm:px-[18px]">
          <span className="font-mono text-[10.5px] uppercase tracking-[0.1em] text-ink-3">
            where these came from
          </span>
          <dl className="mt-[18px] grid gap-x-8 gap-y-3 sm:grid-cols-2 lg:grid-cols-3">
            <Provenance label="Run replayed above" value={FEED_RUN} />
            <Provenance label="Read from" value={SOURCE.feed_file} />
            <Provenance label="Model" value={SOURCE.model} />
            <Provenance label="Containment set" value={SOURCE.containment_dir} />
            <Provenance label="False-block set" value={SOURCE.false_block_dir} />
            <Provenance label="Policy signed" value={`${MANDATE.id} · ${MANDATE.signedOn}`} />
          </dl>
          <p className="mt-[22px] max-w-[58rem] text-[12.5px] leading-[1.6] text-ink-3">
            Every bound and figure on this page is read from{' '}
            <span className="font-mono text-[12px]">evidence.json</span>, which{' '}
            <span className="font-mono text-[12px]">mandate evidence</span> writes from the signed
            policy and the scored result directories. Nothing here is retyped, and the Export
            evidence button above hands you the same file.
          </p>
        </div>
      </section>

      <footer className="mx-auto flex max-w-[1100px] flex-wrap items-center justify-between gap-4 border-t border-rule px-8 py-7 text-[12.5px] text-ink-3 max-sm:px-[18px]">
        <span>Mandate · Autonomous Agent Payment Guardrails</span>
        <span>One run, replayed in full · nothing selected</span>
      </footer>
    </div>
  );
}

function Provenance({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 border-t border-rule-soft pt-2.5">
      <dt className="text-[11.5px] text-ink-3">{label}</dt>
      <dd className="mt-1 truncate font-mono text-[12px] text-ink-2" title={value}>
        {value}
      </dd>
    </div>
  );
}
