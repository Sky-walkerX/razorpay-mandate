/**
 * Live agent console. A judge writes an intent, picks a hostile catalog, and
 * watches a real Gemini agent shop against the gateway.
 *
 * Both arms run the same prompt against the same catalog. The only difference is
 * whether the gateway is allowed to stop the agent, which is the entire claim.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';

const API_BASE =
  typeof window !== 'undefined' && window.location.port === '5173'
    ? import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
    : '';

type Mode = 'enforce' | 'observe';

interface AgentEvent {
  event: 'start' | 'step' | 'verdict' | 'done' | 'error';
  mode?: Mode;
  n?: number;
  tool?: string;
  merchant?: string;
  items?: { sku: string; qty: number }[];
  verdict?: 'ALLOW' | 'DENY' | 'UNKNOWN';
  clause?: string | null;
  message?: string;
  executed?: boolean;
  downstream?: { id?: string; amount?: number } | null;
  spent?: number;
  steps?: number;
  stopped_reason?: string;
  detail?: string;
}

interface ArmState {
  events: AgentEvent[];
  running: boolean;
  spent: number;
  steps: number;
  stopped?: string;
  error?: string;
}

const EMPTY: ArmState = { events: [], running: false, spent: 0, steps: 0 };

const rupees = (paise: number) =>
  `₹${(paise / 100).toLocaleString('en-IN', { maximumFractionDigits: 0 })}`;

/** Reads an SSE body incrementally so steps land as they happen. */
async function readStream(
  res: Response,
  onEvent: (e: AgentEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const reader = res.body?.getReader();
  if (!reader) return;
  const decoder = new TextDecoder();
  let buffer = '';

  while (!signal.aborted) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // SSE frames are separated by a blank line.
    let split = buffer.indexOf('\n\n');
    while (split !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      for (const line of frame.split('\n')) {
        if (line.startsWith('data: ')) {
          try {
            onEvent(JSON.parse(line.slice(6)) as AgentEvent);
          } catch {
            /* a partial frame is not worth surfacing to a judge */
          }
        }
      }
      split = buffer.indexOf('\n\n');
    }
  }
}

export default function LiveAgentPanel({ token }: { token: string | null }) {
  const [intent, setIntent] = useState('Order snacks and drinks for six people tonight');
  const [family, setFamily] = useState('injection.description');
  const [compromised, setCompromised] = useState(true);
  const [families, setFamilies] = useState<string[]>(['clean']);
  const [remaining, setRemaining] = useState<number | null>(null);

  const [arms, setArms] = useState<Record<Mode, ArmState>>({
    enforce: { ...EMPTY },
    observe: { ...EMPTY },
  });
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/v1/agent/families`)
      .then((r) => r.json())
      .then((b) => {
        if (Array.isArray(b.families)) setFamilies(b.families);
        if (typeof b.calls_remaining_today === 'number') setRemaining(b.calls_remaining_today);
      })
      .catch(() => undefined);
  }, []);

  const runArm = useCallback(
    async (mode: Mode, signal: AbortSignal) => {
      setArms((a) => ({ ...a, [mode]: { ...EMPTY, running: true } }));
      try {
        const res = await fetch(`${API_BASE}/v1/agent`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
          body: JSON.stringify({ intent, family, compromised, mode }),
          signal,
        });

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          const detail =
            res.status === 429
              ? 'daily model-call ceiling reached — no more live runs today'
              : body.detail || body.error || `HTTP ${res.status}`;
          setArms((a) => ({ ...a, [mode]: { ...a[mode], running: false, error: detail } }));
          return;
        }

        await readStream(
          res,
          (e) =>
            setArms((a) => {
              const cur = a[mode];
              return {
                ...a,
                [mode]: {
                  ...cur,
                  events: [...cur.events, e],
                  spent: e.spent ?? cur.spent,
                  steps: e.steps ?? e.n ?? cur.steps,
                  stopped: e.event === 'done' ? e.stopped_reason : cur.stopped,
                  error: e.event === 'error' ? e.detail : cur.error,
                  running: e.event !== 'done' && e.event !== 'error',
                },
              };
            }),
          signal,
        );
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setArms((a) => ({
          ...a,
          [mode]: { ...a[mode], running: false, error: (err as Error).message },
        }));
      }
    },
    [intent, family, compromised, token],
  );

  const runBoth = useCallback(() => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    // Sequential, not parallel: two concurrent runs share one session token and
    // would race each other's gateway state.
    void (async () => {
      await runArm('observe', ctrl.signal);
      await runArm('enforce', ctrl.signal);
    })();
  }, [runArm]);

  const busy = arms.enforce.running || arms.observe.running;

  return (
    <div className="grid gap-5 p-[26px] max-sm:px-4">
      {/* ── Controls ─────────────────────────────────────────────── */}
      <div className="overflow-hidden rounded-xl border border-rule bg-bond">
        <div className="border-b border-rule bg-sheet px-4 py-3">
          <h3 className="text-[13px] font-medium text-ink">Live agent</h3>
          <p className="mt-0.5 text-[11.5px] text-ink-3">
            One prompt, one catalog, two arms. The only difference is whether the gateway may
            refuse.
          </p>
        </div>

        <div className="grid gap-3 p-4">
          <label className="grid gap-1.5">
            <span className="text-[11.5px] text-ink-3">Intent</span>
            <textarea
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
              rows={2}
              className="resize-y rounded-[7px] border border-rule bg-sheet px-3 py-2 font-mono text-[12.5px] text-ink outline-none focus:border-navy"
            />
          </label>

          <div className="flex flex-wrap items-end gap-3">
            <label className="grid gap-1.5">
              <span className="text-[11.5px] text-ink-3">Catalog</span>
              <select
                value={family}
                onChange={(e) => setFamily(e.target.value)}
                className="h-[32px] rounded-[7px] border border-rule bg-sheet px-2 font-mono text-[12px] text-ink outline-none focus:border-navy"
              >
                {families.map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex h-[32px] items-center gap-2">
              <input
                type="checkbox"
                checked={compromised}
                onChange={(e) => setCompromised(e.target.checked)}
                className="size-[14px] accent-halt"
              />
              <span className="text-[12px] text-ink-2">agent obeys seller text</span>
            </label>

            <button
              onClick={runBoth}
              disabled={busy || !token || !intent.trim()}
              className="ml-auto h-[32px] rounded-[7px] bg-navy px-4 text-[12.5px] font-medium text-white transition-opacity disabled:opacity-40"
            >
              {busy ? 'Running…' : 'Run both arms'}
            </button>
          </div>

          {remaining !== null && (
            <p className="font-mono text-[11px] text-ink-3">
              {remaining} live model calls left today
            </p>
          )}
          {!token && (
            <p className="font-mono text-[11px] text-refer">
              no session — start one in the Console tab first
            </p>
          )}
        </div>
      </div>

      {/* ── The two arms ─────────────────────────────────────────── */}
      <div className="grid items-start gap-5 lg:grid-cols-2">
        <Arm mode="observe" state={arms.observe} />
        <Arm mode="enforce" state={arms.enforce} />
      </div>
    </div>
  );
}

function Arm({ mode, state }: { mode: Mode; state: ArmState }) {
  const unenforced = mode === 'observe';
  const verdicts = state.events.filter((e) => e.event === 'verdict');
  const executed = verdicts.filter((v) => v.executed).length;
  const refused = verdicts.filter((v) => !v.executed).length;

  return (
    <div
      className={cn(
        'overflow-hidden rounded-xl border bg-bond',
        unenforced ? 'border-halt-line' : 'border-rule',
      )}
    >
      {/* The banner is not decoration. A screenshot of this pane without it reads
          as the gateway failing, when it is the control arm doing its job. */}
      <div
        className={cn(
          'flex items-center justify-between border-b px-4 py-3',
          unenforced ? 'border-halt-line bg-halt-soft' : 'border-rule bg-sheet',
        )}
      >
        <div>
          <h3 className={cn('text-[13px] font-medium', unenforced ? 'text-halt' : 'text-ink')}>
            {unenforced ? 'UNENFORCED CONTROL ARM' : 'Gateway enforcing'}
          </h3>
          <p className="mt-0.5 text-[11.5px] text-ink-3">
            {unenforced
              ? 'the gateway logs but never refuses — this is what happens without Mandate'
              : 'every proposal passes the nine clauses'}
          </p>
        </div>
        <span className="font-mono text-[12px] font-medium text-ink">{rupees(state.spent)}</span>
      </div>

      <div className="grid gap-2 p-4">
        {state.events.length === 0 && !state.running && !state.error && (
          <p className="py-6 text-center text-[12px] text-ink-3">not run yet</p>
        )}

        {state.error && (
          <p className="rounded-[7px] border border-refer-line bg-refer-soft px-3 py-2 font-mono text-[11.5px] text-refer">
            {state.error}
          </p>
        )}

        {verdicts.map((v, i) => {
          const step = state.events.find((e) => e.event === 'step' && e.n === v.n);
          return (
            <div
              key={i}
              className={cn(
                'rounded-[7px] border px-3 py-2',
                v.executed ? 'border-pass-line bg-pass-soft' : 'border-halt-line bg-halt-soft',
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[11.5px] text-ink-2">
                  #{v.n} {step?.merchant ?? ''}{' '}
                  {step?.items?.map((it) => `${it.sku}×${it.qty}`).join(' ')}
                </span>
                <span
                  className={cn(
                    'font-mono text-[11px] font-medium',
                    v.executed ? 'text-pass' : 'text-halt',
                  )}
                >
                  {v.executed ? 'EXECUTED' : 'REFUSED'}
                </span>
              </div>
              {v.clause && (
                <p className="mt-1 font-mono text-[11px] text-ink-3">
                  {v.verdict} · {v.clause}
                </p>
              )}
              {v.downstream?.amount != null && (
                <p className="mt-1 font-mono text-[11px] text-ink-3">
                  {rupees(v.downstream.amount)} · {v.downstream.id}
                </p>
              )}
            </div>
          );
        })}

        {state.running && (
          <p className="py-2 text-center font-mono text-[11.5px] text-ink-3">agent thinking…</p>
        )}

        {state.stopped && (
          <p className="border-t border-rule pt-2 font-mono text-[11px] text-ink-3">
            {state.steps} steps · {executed} executed · {refused} refused · stopped:{' '}
            {state.stopped}
          </p>
        )}
      </div>
    </div>
  );
}
