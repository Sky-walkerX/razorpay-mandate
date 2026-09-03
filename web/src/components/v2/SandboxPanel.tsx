import { useEffect, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { FileCode2, Lock, ShieldOff, Play } from 'lucide-react';
import { cn } from '@/lib/utils';

/**
 * Bring your own mandate: a visitor writes an intent, it compiles, and the same
 * gateway enforces *their* limits for one ephemeral session.
 *
 * Two things about this panel are deliberate and should not be "tidied".
 *
 * **It says unsigned, loudly, and shows where signing happens.** The service
 * cannot sign a policy — that needs the issuer private key, which is offline by
 * design and absent from the deployed image. The gateway refusing to sign is the
 * feature, so the banner states it and prints the CLI command that would. Hiding
 * the limitation would trade the strongest claim in the project for a tidier box.
 *
 * **The probe posts to the same `/v1/orders` every other tab posts to.** There is
 * no sandbox-flavoured evaluation path. If a judge's cap refuses an order it is
 * the production gateway doing it, which is the only version of this demo worth
 * showing — and the reason the caps must visibly disagree with the house policy's.
 */

interface Constraint {
  id: string;
  spec: unknown;
  source: 'heard' | 'inferred' | 'regulatory';
}

interface Sandbox {
  token: string;
  jti: string;
  mandate_id: string;
  policy_hash: string;
  signed: boolean;
  signed_mandate_id: string;
  sign_command: string;
  source_text: string;
  constraints: Constraint[];
  sandbox_tokens_remaining: number;
}

interface CatalogItem {
  sku: string;
  title: string;
  merchant: string;
  unit_price: number;
  category: string;
}

interface Probe {
  verdict: string;
  clause_id: string | null;
  message: string;
  executed: boolean;
  amount_paise: number;
}

const SOURCE_LABEL: Record<string, string> = {
  heard: 'heard',
  inferred: 'inferred',
  regulatory: 'required by law',
};

const SAMPLES = [
  'Spend at most ₹300 on any one order, ₹800 in total. Nothing alcoholic.',
  'Only from Blinkit. Under ₹250 an order, at most 2 orders.',
  'No more than 2 of any one item, nothing over ₹150 each.',
];

const rupees = (paise: number) => `₹${(paise / 100).toLocaleString('en-IN', {
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})}`;

/** The bound as a person reads it, from whatever shape the clause carries. */
function readBound(id: string, spec: unknown): string {
  if (Array.isArray(spec)) return spec.join(', ');
  if (spec && typeof spec === 'object') {
    const o = spec as Record<string, unknown>;
    if (typeof o.max_actions === 'number') return `${o.max_actions} per ${o.window ?? 'mandate'}`;
    if (typeof o.threshold === 'number') return rupees(o.threshold);
    if (typeof o.max === 'number') {
      return id.startsWith('budget.') ? rupees(o.max) : String(o.max);
    }
  }
  return 'set';
}

export default function SandboxPanel({ apiBase }: { apiBase: string }) {
  const reduced = useReducedMotion() ?? false;

  const [prompt, setPrompt] = useState(SAMPLES[0]);
  const [busy, setBusy] = useState(false);
  const [sandbox, setSandbox] = useState<Sandbox | null>(null);
  /** Why there is no sandbox. `kind` matters: a decline is the determinism
   *  check firing and will repeat, a timeout says nothing about the intent. */
  const [refusal, setRefusal] = useState<{ kind: string; reason: string } | null>(null);

  const [catalog, setCatalog] = useState<CatalogItem[]>([]);
  const [sku, setSku] = useState('');
  const [qty, setQty] = useState(1);
  const [probe, setProbe] = useState<Probe | null>(null);
  const [probing, setProbing] = useState(false);

  useEffect(() => {
    fetch(`${apiBase}/v1/catalog`)
      .then((r) => (r.ok ? r.json() : []))
      .then((items: CatalogItem[]) => {
        setCatalog(items);
        if (items.length && !sku) setSku(items[0].sku);
      })
      .catch(() => setCatalog([]));
    // Fetched once. The catalog does not change inside a session.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase]);

  const compile = async () => {
    setBusy(true);
    setRefusal(null);
    setSandbox(null);
    setProbe(null);
    try {
      const res = await fetch(`${apiBase}/v1/sandbox`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt }),
      });
      const data = await res.json();
      if (!res.ok || data.compiled === false) {
        // A refusal is an outcome, not a failure to hide — but only one of the
        // three kinds is the compiler being careful, so the gloss below keys off
        // `kind` rather than explaining a slow network as good judgement.
        setRefusal({
          kind: data.kind || 'error',
          reason: data.reason || data.detail || `HTTP ${res.status}`,
        });
        return;
      }
      setSandbox(data as Sandbox);
    } catch (e) {
      setRefusal({
        kind: 'error',
        reason: e instanceof Error ? e.message : 'the gateway did not answer',
      });
    } finally {
      setBusy(false);
    }
  };

  const runProbe = async () => {
    if (!sandbox) return;
    const item = catalog.find((c) => c.sku === sku);
    if (!item) return;
    setProbing(true);
    try {
      const res = await fetch(`${apiBase}/v1/orders`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${sandbox.token}`,
        },
        body: JSON.stringify({ merchant: item.merchant, items: [{ sku, qty }] }),
      });
      const data = await res.json();
      const dec = data.decision || data;
      setProbe({
        verdict: dec.verdict ?? 'ERROR',
        clause_id: dec.clause_id ?? null,
        message: dec.message ?? data.detail ?? '',
        executed: Boolean(dec.executed),
        amount_paise: data.record?.action?.amount ?? item.unit_price * qty,
      });
    } catch (e) {
      setProbe({
        verdict: 'ERROR', clause_id: null,
        message: e instanceof Error ? e.message : 'no answer', executed: false,
        amount_paise: 0,
      });
    } finally {
      setProbing(false);
    }
  };

  const selected = catalog.find((c) => c.sku === sku);
  const estimate = selected ? selected.unit_price * qty : 0;

  return (
    <div className="grid items-start gap-5 p-8 max-sm:px-[18px] lg:grid-cols-2">
      {/* ── write it ──────────────────────────────────────────────────── */}
      <div className="overflow-hidden rounded-panel border border-rule bg-bond">
        <div className="border-b border-rule bg-sheet px-5 py-[11px]">
          <div className="flex flex-col gap-[2px]">
            <span className="text-[13.5px] font-semibold text-ink">Say what you would allow</span>
            <span className="text-[12px] text-ink-3">
              Plain English. Amounts, shops, things you never want bought.
            </span>
          </div>
        </div>
        <div className="flex flex-col gap-3 p-5">
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            rows={5}
            aria-label="Your mandate, in plain words"
            className="w-full resize-none rounded-lg border border-rule bg-sheet p-3 text-[13.5px] leading-[1.6] text-ink outline-none focus:border-indigo"
          />
          <div className="flex flex-wrap gap-1.5">
            {SAMPLES.map((s) => (
              <button
                key={s}
                onClick={() => setPrompt(s)}
                className="rounded-full border border-rule bg-sheet px-2.5 py-[4px] text-[11.5px] text-ink-2 transition-colors hover:border-indigo hover:text-ink"
              >
                {s.slice(0, 34)}…
              </button>
            ))}
          </div>
          <button
            onClick={compile}
            disabled={busy || !prompt.trim()}
            className="inline-flex h-[38px] items-center justify-center gap-[7px] self-start rounded-lg bg-indigo px-4 text-[13.5px] font-medium text-white transition-colors hover:bg-[#254ED0] disabled:opacity-50"
          >
            <FileCode2 className="size-[14px]" />
            {busy ? 'Reading it…' : 'Turn this into real limits'}
          </button>
          <p className="text-[12.5px] leading-[1.55] text-ink-3">
            <span className="mr-[6px] inline-flex items-center gap-[6px] whitespace-nowrap rounded-full bg-indigo-soft px-[9px] py-[2px] text-[11px] font-medium text-indigo align-[1px]">
              <span aria-hidden className="size-[7px] rounded-full bg-indigo" />
              Uses AI
            </span>
            An AI reads your sentence twice and refuses if the two readings disagree, rather than
            guessing at what you meant. What comes out is enforced by the same gateway every other
            tab uses, and enforcing it involves no AI. Keep your caps well under the demo's ₹1,000
            an order, or you will not be able to tell whose number refused you.
          </p>
        </div>
      </div>

      {/* ── what happened to it ───────────────────────────────────────── */}
      <div className="overflow-hidden rounded-panel border border-rule bg-bond">
        <div className="border-b border-rule bg-sheet px-5 py-[11px]">
          <div className="flex flex-col gap-[2px]">
            <span className="text-[13.5px] font-semibold text-ink">
              {sandbox ? 'Your limits, now being enforced' : 'What it understood'}
            </span>
            <span className="text-[12px] text-ink-3">
              {sandbox
                ? 'Live for this visit only, and not signed.'
                : 'Your sentence, turned into limits the gateway can check.'}
            </span>
          </div>
        </div>

        {refusal && (
          <div className="border-b border-refer-line bg-refer-soft px-5 py-4">
            <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-refer">
              no mandate was built
            </div>
            <p className="mt-2 text-[13px] leading-[1.55] text-ink-2">{refusal.reason}</p>
            <p className="mt-2 text-[12.5px] leading-[1.5] text-ink-3">
              {refusal.kind === 'declined'
                ? 'The compiler declining is the determinism check working. It read your ' +
                  'words twice and the two readings disagreed, so it would rather say ' +
                  'nothing than commit to one of them. Rewording the limits usually fixes it.'
                : refusal.kind === 'timeout'
                  ? 'This one is the network, not your sentence — the model did not answer ' +
                    'in time. Nothing was compiled and nothing was enforced. Try again.'
                  : 'The gateway could not reach the compiler. Nothing was compiled and ' +
                    'nothing was enforced.'}
            </p>
          </div>
        )}

        {!sandbox && !refusal && (
          <p className="px-5 py-10 text-center text-[13px] text-ink-3">
            Nothing read yet. Your limits appear here, each marked{' '}
            <b className="font-medium text-ink-2">you said this</b> or{' '}
            <b className="font-medium text-ink-2">we guessed</b>, and then you can try to
            get an order past them.
          </p>
        )}

        {sandbox && (
          <motion.div
            initial={reduced ? false : { opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.32, ease: [0.22, 0.61, 0.36, 1] }}
          >
            {/* The limitation, stated first and on purpose. */}
            <div className="border-b border-refer-line bg-refer-soft px-5 py-4">
              <div className="flex items-center gap-2">
                <ShieldOff aria-hidden className="size-[13px] text-refer" strokeWidth={2.2} />
                <span className="text-[12px] font-medium text-refer">
                  Not signed, and gone when you leave
                </span>
              </div>
              <p className="mt-2 text-[12.5px] leading-[1.55] text-ink-2">
                We cannot sign your rules here, and that is deliberate: signing needs a
                private key that is kept offline and is not on this server. Your rules are
                enforced for this visit only, and orders made under them are filed
                separately from the demo mandate so the two can never be confused.
              </p>
              <div className="mt-2.5 flex items-start gap-2 overflow-x-auto rounded-md border border-rule bg-bond px-2.5 py-2">
                <Lock aria-hidden className="mt-[2px] size-[11px] shrink-0 text-ink-3" />
                <code className="whitespace-pre font-mono text-[11px] text-ink-2">
                  {sandbox.sign_command}
                </code>
              </div>
            </div>

            {/* Their limits. */}
            <ul className="divide-y divide-hair">
              {sandbox.constraints.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3 px-5 py-[10px]">
                  <span className="font-mono text-[11.5px] text-ink-2">{c.id}</span>
                  <span className="flex items-center gap-2.5">
                    <span className="text-[13px] text-ink">{readBound(c.id, c.spec)}</span>
                    <span
                      className={cn(
                        'shrink-0 rounded-full border px-[7px] py-[2px] font-mono text-[9px] uppercase tracking-[0.07em]',
                        c.source === 'heard'
                          ? 'border-pass-line bg-pass-soft text-pass'
                          : c.source === 'regulatory'
                            ? 'border-rule bg-sunk text-ink-3'
                            : 'border-refer-line bg-refer-soft text-refer',
                      )}
                    >
                      {SOURCE_LABEL[c.source] ?? c.source}
                    </span>
                  </span>
                </li>
              ))}
            </ul>

            {/* Try to get past them. */}
            <div className="border-t border-rule bg-sheet px-5 py-4">
              <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-ink-2">
                now try to get an order past it
              </div>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <select
                  value={sku}
                  onChange={(e) => setSku(e.target.value)}
                  aria-label="Item"
                  className="h-[34px] min-w-[190px] flex-1 rounded-lg border border-rule bg-bond px-2 text-[13px] text-ink outline-none focus:border-indigo"
                >
                  {catalog.map((c) => (
                    <option key={c.sku} value={c.sku}>
                      {c.title} — {rupees(c.unit_price)}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={1}
                  max={99}
                  value={qty}
                  onChange={(e) => setQty(Math.max(1, Number(e.target.value) || 1))}
                  aria-label="Quantity"
                  className="h-[34px] w-[64px] rounded-lg border border-rule bg-bond px-2 text-[13px] text-ink outline-none focus:border-indigo"
                />
                <button
                  onClick={runProbe}
                  disabled={probing || !sku}
                  className="inline-flex h-[34px] items-center gap-[6px] rounded-lg border border-rule bg-bond px-3 text-[13px] font-medium text-ink transition-colors hover:border-indigo disabled:opacity-50"
                >
                  <Play aria-hidden className="size-[12px]" />
                  {probing ? 'Sending…' : 'Propose'}
                </button>
                {selected && (
                  <span className="font-mono text-[11.5px] text-ink-3">
                    = {rupees(estimate)}
                  </span>
                )}
              </div>

              {probe && (
                <motion.div
                  key={`${probe.verdict}-${probe.clause_id}-${probe.amount_paise}`}
                  className={cn(
                    'mt-3 rounded-lg border px-4 py-3',
                    probe.executed
                      ? 'border-pass-line bg-pass-soft'
                      : 'border-halt-line bg-halt-soft',
                  )}
                  initial={reduced ? false : { opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.26, ease: [0.22, 0.61, 0.36, 1] }}
                >
                  <div
                    className={cn(
                      'font-mono text-[10px] uppercase tracking-[0.1em]',
                      probe.executed ? 'text-pass' : 'text-halt',
                    )}
                  >
                    {probe.executed ? 'Went through' : 'Refused'}
                  </div>
                  <p className="mt-1.5 text-[13px] leading-[1.5] text-ink">{probe.message}</p>
                  <p className="mt-1.5 text-[12px] leading-[1.5] text-ink-2">
                    {probe.executed
                      ? 'Inside every limit you wrote, so the payment went through.'
                      : 'Your limit, your number, and the same gateway the demo runs on.'}
                  </p>
                </motion.div>
              )}
            </div>
          </motion.div>
        )}
      </div>
    </div>
  );
}
