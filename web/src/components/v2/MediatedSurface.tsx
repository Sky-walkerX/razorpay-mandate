import { useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { QRCodeSVG } from 'qrcode.react';
import { ArrowUpRight, Check, Loader2, ShieldAlert } from 'lucide-react';
import { SURFACE, EXPOSURE, MANDATE_ID } from '@/data/alignment';
import { API_BASE } from '@/lib/api';
import { rupeesWhole as rupees } from '@/lib/money';
import { cn } from '@/lib/utils';

/**
 * Two sections about the rail as it actually is, rather than as this repo
 * describes it.
 *
 * The page around them argues from a projection: `rails.py` decides which
 * clauses a rail could carry, and the reader has only our word for it. These two
 * argue from objects anyone in the room can reach. `mcp.razorpay.com/mcp` is a
 * public endpoint serving a tool list, and `/v1/rail/mandate` opens a real
 * mandate on the rail and hands back a link a judge scans on their phone.
 *
 * Every figure comes from `evidence.json` by way of `@/data/alignment`, so the
 * counts are the upstream's own `destructiveHint` annotations rather than a
 * number typed here. The one exception is the rail mandate itself, which cannot
 * be static because creating it is the point.
 */

/* ── the tool grid ────────────────────────────────────────────────────────── */

type Bucket = 'bound' | 'refused' | 'passthrough';

const BUCKET: Record<Bucket, { label: string; cell: string }> = {
  bound: { label: 'Checked against the mandate', cell: 'bg-indigo' },
  refused: { label: 'Refused outright', cell: 'bg-halt' },
  passthrough: { label: 'Read-only, passed through', cell: 'bg-rule' },
};

/** One cell per upstream tool, ordered so the money-moving ones lead. */
function ToolGrid({ reduced }: { reduced: boolean }) {
  const cells: Bucket[] = [
    ...Array<Bucket>(SURFACE.bound.length).fill('bound'),
    ...Array<Bucket>(SURFACE.refused.length).fill('refused'),
    ...Array<Bucket>(SURFACE.passthroughCount).fill('passthrough'),
  ];
  return (
    <div>
      {/* The column counts divide the upstream's tool count exactly at both
          sizes, so the block is a full rectangle. Left to flex-wrap it ends on
          an orphan row, which reads as an accident rather than as a count. If
          Razorpay's surface changes size, revisit these two numbers. */}
      <div
        className="grid max-w-[600px] gap-[5px] grid-cols-[repeat(14,minmax(0,1fr))] max-sm:max-w-none max-sm:grid-cols-[repeat(7,minmax(0,1fr))]"
        aria-hidden
      >
        {cells.map((b, i) => (
          <motion.span
            key={i}
            className={cn('aspect-square w-full rounded-sm', BUCKET[b].cell)}
            initial={reduced ? false : { opacity: 0, scale: 0.6 }}
            whileInView={{ opacity: 1, scale: 1 }}
            viewport={{ once: true, margin: '-60px' }}
            transition={{
              duration: 0.28,
              delay: Math.min(i * 0.012, 0.5),
              ease: [0.22, 0.61, 0.36, 1],
            }}
          />
        ))}
      </div>
      <p className="sr-only">
        {SURFACE.total} tools: {SURFACE.bound.length} checked against the mandate before
        they run, {SURFACE.refused.length} refused outright, {SURFACE.passthroughCount}{' '}
        read-only and passed through.
      </p>
      {/* Colour never carries the meaning on its own here; the count and the
          label do, and the swatch only ties each row back to the block above. */}
      <div className="mt-5 flex flex-wrap gap-x-7 gap-y-2.5">
        {(Object.keys(BUCKET) as Bucket[]).map((b) => {
          const n =
            b === 'bound' ? SURFACE.bound.length
              : b === 'refused' ? SURFACE.refused.length
                : SURFACE.passthroughCount;
          const { label, cell } = BUCKET[b];
          return (
            <span key={b} className="flex items-baseline gap-2">
              <span className={cn('h-[10px] w-[10px] shrink-0 translate-y-[-1px] rounded-sm', cell)} />
              <span className="font-mono text-[16px] leading-none text-ink">{n}</span>
              <span className="text-[13px] text-ink-2">{label}</span>
            </span>
          );
        })}
      </div>
    </div>
  );
}

/* ── the same request, sent to two places ─────────────────────────────────── */

function Wire({
  host, verdict, tone, body, note,
}: {
  host: string;
  verdict: string;
  tone: 'halt' | 'pass';
  body: string;
  note: string;
}) {
  return (
    <div className="flex-1 overflow-hidden rounded-panel border border-rule bg-raise shadow-sheet">
      <div className="flex items-center gap-2 border-b border-rule bg-sheet px-4 py-2.5">
        <span className="truncate font-mono text-[11px] text-ink-2">{host}</span>
        <span
          className={cn(
            'ml-auto shrink-0 rounded-full border px-2 py-[2px] font-mono text-[9.5px] uppercase tracking-[0.08em]',
            tone === 'halt'
              ? 'border-halt-line bg-halt-soft text-halt'
              : 'border-pass-line bg-pass-soft text-pass',
          )}
        >
          {verdict}
        </span>
      </div>
      <pre className="overflow-x-auto px-4 py-3.5 font-mono text-[11.5px] leading-[1.65] text-ink-2">
        {body}
      </pre>
      <div className="border-t border-hair px-4 py-2.5 text-[12.5px] leading-[1.45] text-ink-3">
        {note}
      </div>
    </div>
  );
}

export function RazorpaySurface() {
  const reduced = useReducedMotion() ?? false;

  return (
    <section id="surface" className="scroll-mt-[76px] border-t border-rule py-12">
      <h2 className="max-w-[760px] text-[27px] font-medium leading-[1.18] tracking-[-0.018em] text-ink max-sm:text-[21px]">
        Razorpay already gives an agent {SURFACE.total} tools. {SURFACE.destructive} of
        them move money, and nothing stands in front of them.
      </h2>
      <p className="mt-4 max-w-[680px] text-[15px] leading-[1.6] text-ink-2">
        <span className="font-mono text-[13.5px] text-ink">{SURFACE.endpoint}</span> is
        public. It authenticates with a merchant's API keys over HTTP Basic and answers a
        plain JSON-RPC POST, with no handshake. Point a model at it and it can create a
        payment link, capture a payment or revoke a saved instrument. That is not a
        criticism: a payment API's job is to move money when asked. It is the reason a
        layer has to exist above it.
      </p>

      <div className="mt-9 rounded-panel border border-rule bg-raise p-6 shadow-sheet max-sm:p-5">
        <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
          The same {SURFACE.total} tools, behind {MANDATE_ID}
        </div>
        <div className="mt-4">
          <ToolGrid reduced={reduced} />
        </div>
        <p className="mt-5 max-w-[720px] text-[13.5px] leading-[1.55] text-ink-2">
          Anything Razorpay ships next is refused until somebody decides which limit can
          bound it. A proxy that forwards a seventeenth money-moving tool because nobody
          updated a list is the failure this whole project is about, so the classification
          test fails on a name it has not been told about rather than passing it along.
        </p>
      </div>

      <div className="mt-4 flex gap-4 max-md:flex-col">
        <Wire
          host="POST mcp.razorpay.com/mcp"
          verdict="₹50,000 created"
          tone="halt"
          body={'"name": "create_payment_link",\n"arguments": {\n  "amount": 5000000,\n  "currency": "INR"\n}'}
          note="A link for fifty thousand rupees, against a mandate that allows one thousand per transaction. The rail was never told about the mandate."
        />
        <Wire
          host={`POST ${SURFACE.mediatedPath}`}
          verdict="refused"
          tone="pass"
          body={'"clause": "budget.per_transaction",\n"message": "limit ₹1000.00,\n            attempted ₹50000.00",\n"allowed": false'}
          note="Same request, same credentials, same upstream. The gateway priced it against the signed mandate and never made the call."
        />
      </div>

      <div className="mt-9 grid grid-cols-2 gap-x-6 gap-y-3 max-md:grid-cols-1">
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
            Checked against the mandate, then forwarded
          </div>
          <ul className="mt-3 space-y-2">
            {SURFACE.bound.map((t) => (
              <li key={t} className="flex items-start gap-2.5">
                <Check aria-hidden className="mt-[3px] size-[13px] shrink-0 text-indigo" strokeWidth={2.6} />
                <span className="font-mono text-[12.5px] leading-[1.45] text-ink">{t}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 max-w-[400px] text-[12.5px] leading-[1.5] text-ink-3">
            A call carrying only an amount can reach {SURFACE.evaluatedOnRawCall} of this
            mandate's limits. The other {SURFACE.notApplicableOnRawCall} read line items or
            a payee and there are none, so the answer says so rather than reporting them
            as passed.
          </p>
        </div>
        <div>
          <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
            Refused, because no limit can decide them
          </div>
          <ul className="mt-3 space-y-[9px]">
            {SURFACE.refused.map((r) => (
              <li key={r.tool} className="flex items-start gap-2.5">
                <ShieldAlert aria-hidden className="mt-[3px] size-[13px] shrink-0 text-halt" strokeWidth={2.4} />
                <span className="text-[12.5px] leading-[1.45] text-ink-2">
                  <span className="font-mono text-ink">{r.tool}</span>{' '}
                  <span className="text-ink-3">{r.reason}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

/* ── the rail's own mandate ───────────────────────────────────────────────── */

interface RailLink {
  id: string;
  short_url: string;
  status: string;
  order_id: string;
  rail_holds: {
    max_amount_paise: number;
    payee: string;
    expire_at: number;
    frequency: string;
  };
  product: string;
  not_reserve_pay_because: string;
}

type State =
  | { kind: 'idle' }
  | { kind: 'opening' }
  | { kind: 'open'; link: RailLink }
  | { kind: 'failed'; reason: string };

export function RailMandate() {
  const reduced = useReducedMotion() ?? false;
  const [state, setState] = useState<State>({ kind: 'idle' });

  async function open() {
    setState({ kind: 'opening' });
    try {
      const res = await fetch(`${API_BASE}/v1/rail/mandate`, { method: 'POST' });
      const body = await res.json();
      if (!res.ok) {
        setState({ kind: 'failed', reason: body.reason || `HTTP ${res.status}` });
        return;
      }
      setState({ kind: 'open', link: body.link });
    } catch (e) {
      setState({ kind: 'failed', reason: e instanceof Error ? e.message : 'the request failed' });
    }
  }

  return (
    <section id="mandate" className="scroll-mt-[76px] border-t border-rule py-12">
      <h2 className="max-w-[760px] text-[27px] font-medium leading-[1.18] tracking-[-0.018em] text-ink max-sm:text-[21px]">
        Open the rail's own mandate and read what it holds.
      </h2>
      <p className="mt-4 max-w-[680px] text-[15px] leading-[1.6] text-ink-2">
        Everything above this line is a projection of the rail's vocabulary. This is the
        object. It is created from the signed policy, on Razorpay's test rail, right now:
        the block is <span className="font-mono text-[13.5px] text-ink">budget.total</span>,
        the expiry is the mandate's own, and the mandate id travels in the notes so the two
        documents can be lined up afterwards.
      </p>

      {/* The cost of expressing this mandate in blocks, which is the finding the
          per-payee fix would otherwise hide. */}
      <div className="mt-7 rounded-panel border border-refer-line bg-refer-soft px-6 py-5 max-sm:px-5">
        <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-refer">
          What it costs to say this on the rail
        </div>
        <p className="mt-2.5 max-w-[720px] text-[13.5px] leading-[1.55] text-ink-2">
          A block names one payee and carries its own amount, so{' '}
          <span className="text-ink">{rupees(EXPOSURE.mandateCapPaise)} across {EXPOSURE.payees} shops</span>{' '}
          has two representations and both are wrong. One block serves one shop and refuses{' '}
          {EXPOSURE.refusedPayees.map((m, i) => (
            <span key={m}>
              {i > 0 && ' and '}
              <span className="font-mono text-halt">{m}</span>
            </span>
          ))}
          . One block per shop covers all {EXPOSURE.payees} and blocks{' '}
          <span className="text-ink">{rupees(EXPOSURE.blockedTotalPaise)}</span> of the
          person's money to authorise {rupees(EXPOSURE.mandateCapPaise)} of spending.
          Reporting only the first overstates how rigid the rail is; reporting only the
          second hides that blocked funds are money they cannot spend elsewhere.
        </p>
      </div>

      <div className="mt-4 rounded-panel border border-rule bg-raise p-6 shadow-sheet max-sm:p-5">
        {state.kind !== 'open' && (
          <div className="flex flex-wrap items-center gap-4">
            <button
              type="button"
              onClick={open}
              disabled={state.kind === 'opening'}
              className={cn(
                'inline-flex h-[38px] items-center gap-2 rounded-lg bg-[#2F5EFF] px-4',
                'text-[13.5px] text-white shadow-2xs transition-colors',
                'hover:bg-[#254ED0] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2F5EFF]',
                'disabled:cursor-not-allowed disabled:opacity-60',
              )}
            >
              {state.kind === 'opening' && (
                <Loader2 aria-hidden className="size-[14px] animate-spin" strokeWidth={2.4} />
              )}
              {state.kind === 'opening' ? 'Asking the rail…' : "Open the rail's mandate"}
            </button>
            <span className="text-[12.5px] leading-[1.45] text-ink-3">
              Razorpay test mode. No real money moves.
            </span>
          </div>
        )}

        {state.kind === 'failed' && (
          <div className="mt-4 flex items-start gap-2.5 rounded-lg border border-halt-line bg-halt-soft px-4 py-3">
            <ShieldAlert aria-hidden className="mt-[2px] size-[14px] shrink-0 text-halt" strokeWidth={2.4} />
            <div className="text-[13px] leading-[1.5] text-ink-2">
              <span className="text-halt">The rail did not open a mandate.</span>{' '}
              {state.reason}
            </div>
          </div>
        )}

        {state.kind === 'open' && (
          <motion.div
            className="flex gap-7 max-md:flex-col"
            initial={reduced ? false : { opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: [0.22, 0.61, 0.36, 1] }}
          >
            <div className="shrink-0">
              <div className="w-fit rounded-panel border border-rule bg-white p-3">
                <QRCodeSVG value={state.link.short_url} size={148} level="M" marginSize={0} />
              </div>
              <a
                href={state.link.short_url}
                target="_blank"
                rel="noreferrer"
                className="mt-3 inline-flex items-center gap-1.5 font-mono text-[15px] text-ink underline decoration-rule underline-offset-[4px] transition-colors hover:decoration-ink"
              >
                {state.link.short_url.replace(/^https?:\/\//, '')}
                <ArrowUpRight aria-hidden className="size-[12px]" strokeWidth={2.4} />
              </a>
            </div>

            <div className="min-w-0 flex-1">
              <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
                {state.link.product} · {state.link.id}
              </div>
              <p className="mt-2 text-[13.5px] leading-[1.5] text-ink-2">
                Everything this mandate can say, on the rail. Four fields, and one of
                them bounds nothing.
              </p>
              <dl className="mt-4 divide-y divide-hair border-y border-hair">
                {[
                  ['Blocked amount', rupees(state.link.rail_holds.max_amount_paise)],
                  // The sharpest row on the panel: the mandate names three shops
                  // and a block can name one of them.
                  ['Payee', `1 of ${EXPOSURE.payees} this mandate allows`],
                  ['Expires', new Date(state.link.rail_holds.expire_at * 1000).toLocaleDateString()],
                  ['Frequency', `${state.link.rail_holds.frequency}, bounds nothing`],
                ].map(([k, v]) => (
                  <div key={k} className="flex items-baseline justify-between gap-4 py-[9px]">
                    <dt className="text-[13px] text-ink-2">{k}</dt>
                    <dd className="text-right font-mono text-[13px] text-ink">{v}</dd>
                  </div>
                ))}
              </dl>
              <p className="mt-4 max-w-[440px] text-[12.5px] leading-[1.5] text-ink-3">
                {state.link.not_reserve_pay_because}
              </p>
            </div>
          </motion.div>
        )}
      </div>
    </section>
  );
}
