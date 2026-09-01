import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import { Button } from '@/components/ui/button';
import { MandateLockup } from '@/components/brand/MandateLockup';
import { SellerChip } from '@/components/v2/SellerMark';
import { StatusBadge, type Tone } from '@/components/dashboard/StatusBadge';
import { rupees, rupeesWhole } from '@/lib/money';

/**
 * The shop floor.
 *
 * Everywhere else in this app a refusal is a row in a table with a clause id
 * beside it. Here it is an order that did not arrive. The card keeps the exact
 * shape of a delivered one and changes a single field: where a grocery app puts
 * the delivery status, a refused order puts the clause that stopped it. That
 * substitution is the argument, and it needs no caption.
 *
 * Orders arrive from three places and each row says which: the console's agent,
 * an MCP client someone pointed at /mcp, or a direct call to /v1/orders.
 */

const API_BASE =
  typeof window !== 'undefined' && window.location.port === '5173'
    ? import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
    : '';

const POLL_INTERVAL_MS = 1500;
const TOKEN_KEY = 'mandate_judge_token';
const EASE = [0.22, 0.61, 0.36, 1] as const;

const SELLER_NAMES: Record<string, string> = {
  zepto: 'Zepto',
  blinkit: 'Blinkit',
  instamart: 'Instamart',
};

const TONE_BY_STATUS: Record<string, Tone> = {
  EXECUTED: 'pass',
  REFUSED: 'halt',
  UNKNOWN: 'refer',
};

const SOURCE_LABEL: Record<string, string> = {
  mcp: 'MCP client',
  agent: 'Console agent',
  http: 'Direct API',
};

interface StoreLine {
  sku: string;
  title: string;
  qty: number;
  unit_price_paise: number;
  amount_paise: number;
  category: string;
}

interface StoreOrder {
  order_id: string;
  ts: string;
  week: number;
  merchant: string;
  items: StoreLine[];
  amount_paise: number;
  status: 'EXECUTED' | 'REFUSED' | 'UNKNOWN';
  verdict: string;
  clause_id: string | null;
  message: string;
  downstream_id: string | null;
  source: string;
}

interface WeekMarker {
  week: number;
  family: string;
}

interface StoreBody {
  week: number;
  weeks: WeekMarker[];
  orders: StoreOrder[];
  totals: { executed_paise: number; executed_count: number; refused_count: number };
}

interface WeekBody {
  week: number;
  family: string;
  corpus_hash: string | null;
}

function sellerName(merchant: string): string {
  return SELLER_NAMES[merchant.trim().toLowerCase()] ?? merchant;
}

/** A bearer for the one write on this page. Reused from the console if present. */
async function ensureToken(): Promise<string | null> {
  const cached = sessionStorage.getItem(TOKEN_KEY);
  if (cached) return cached;
  try {
    const res = await fetch(`${API_BASE}/v1/sessions`, { method: 'POST' });
    if (!res.ok) return null;
    const body = await res.json();
    sessionStorage.setItem(TOKEN_KEY, body.token);
    return body.token as string;
  } catch {
    return null;
  }
}

function OrderCard({
  order,
  index,
  reduced,
}: {
  order: StoreOrder;
  index: number;
  reduced: boolean;
}) {
  const refused = order.status === 'REFUSED';
  const at = new Date(order.ts).toLocaleTimeString('en-IN', {
    hour: 'numeric',
    minute: '2-digit',
  });

  return (
    <motion.li
      initial={reduced ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.03, 0.24), ease: EASE }}
      className="rounded-panel border border-rule bg-raise shadow-sheet"
    >
      <div className="flex flex-wrap items-center gap-3 border-b border-hair px-4 py-3">
        <SellerChip name={sellerName(order.merchant)} />
        <StatusBadge tone={TONE_BY_STATUS[order.status] ?? 'unset'} label={order.status} />
        <span className="ml-auto font-mono text-[10.5px] uppercase tracking-[0.07em] text-ink-3">
          {SOURCE_LABEL[order.source] ?? order.source} &middot; {at}
        </span>
      </div>

      <ul className="divide-y divide-hair px-4">
        {order.items.map((line) => (
          <li key={line.sku} className="flex items-baseline gap-3 py-2.5">
            <span className="font-mono text-[11px] text-ink-4">{line.qty}&times;</span>
            <span className="text-[13.5px] text-ink">{line.title}</span>
            <span className="ml-auto font-mono text-[12.5px] text-ink-2">
              {rupees(line.amount_paise)}
            </span>
          </li>
        ))}
        {order.items.length === 0 && (
          <li className="py-2.5 text-[13px] text-ink-3">
            Nothing was priced. The basket stopped before it was costed.
          </li>
        )}
      </ul>

      {/* The one substituted field. A grocery app says "Delivered in 11 minutes"
          here. A refused order says which clause stopped it. */}
      <div
        className={
          refused
            ? 'flex flex-wrap items-center gap-x-3 gap-y-1 rounded-b-panel border-t border-halt-line bg-halt-soft px-4 py-3'
            : 'flex flex-wrap items-center gap-x-3 gap-y-1 rounded-b-panel border-t border-hair bg-sheet px-4 py-3'
        }
      >
        {refused ? (
          <>
            <span className="font-mono text-[11px] uppercase tracking-[0.07em] text-halt">
              {order.clause_id}
            </span>
            <span className="text-[13px] text-ink-2">{order.message}</span>
            <span className="ml-auto font-mono text-[13px] text-ink-4 line-through">
              {rupees(order.amount_paise)}
            </span>
          </>
        ) : (
          <>
            <span className="font-mono text-[11px] uppercase tracking-[0.07em] text-ink-3">
              {order.downstream_id ?? 'no rail reference'}
            </span>
            {order.verdict === 'DENY' && (
              <span className="text-[13px] text-refer">
                Executed unenforced, against {order.clause_id}
              </span>
            )}
            <span className="ml-auto font-mono text-[13px] font-medium text-ink">
              {rupees(order.amount_paise)}
            </span>
          </>
        )}
      </div>
    </motion.li>
  );
}

function Figure({ label, value, tone }: { label: string; value: string; tone?: 'halt' }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="font-mono text-[9.5px] uppercase tracking-[0.09em] text-ink-3">{label}</span>
      <span
        className={
          tone === 'halt'
            ? 'font-mono text-[22px] leading-none tracking-[-0.02em] text-halt'
            : 'font-mono text-[22px] leading-none tracking-[-0.02em] text-ink'
        }
      >
        {value}
      </span>
    </div>
  );
}

export default function Storefront() {
  const reduced = useReducedMotion() ?? false;
  const [body, setBody] = useState<StoreBody | null>(null);
  const [week, setWeek] = useState<WeekBody | null>(null);
  const [offline, setOffline] = useState(false);
  const [busy, setBusy] = useState(false);
  const etag = useRef<string | null>(null);

  const poll = useCallback(async () => {
    try {
      const headers: HeadersInit = etag.current ? { 'If-None-Match': etag.current } : {};
      const res = await fetch(`${API_BASE}/v1/store/orders`, { headers });
      if (res.status === 304) {
        setOffline(false);
        return;
      }
      if (!res.ok) {
        setOffline(true);
        return;
      }
      etag.current = res.headers.get('etag');
      setBody((await res.json()) as StoreBody);
      setOffline(false);
    } catch {
      setOffline(true);
    }
  }, []);

  useEffect(() => {
    void poll();
    const id = window.setInterval(poll, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [poll]);

  const currentWeek = body?.week;
  useEffect(() => {
    fetch(`${API_BASE}/v1/store/week`)
      .then((r) => (r.ok ? r.json() : null))
      .then((w) => setWeek(w as WeekBody | null))
      .catch(() => setWeek(null));
  }, [currentWeek]);

  async function advance() {
    setBusy(true);
    try {
      const token = await ensureToken();
      if (!token) return;
      await fetch(`${API_BASE}/v1/store/advance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ family: 'injection.description' }),
      });
      etag.current = null;
      await poll();
    } finally {
      setBusy(false);
    }
  }

  const orders = body?.orders ?? [];
  const byWeek = new Map<number, StoreOrder[]>();
  for (const order of orders) {
    const bucket = byWeek.get(order.week) ?? [];
    bucket.push(order);
    byWeek.set(order.week, bucket);
  }
  const familyOf = (n: number) => body?.weeks.find((w) => w.week === n)?.family ?? 'clean';

  // The endpoint totals whatever was asked for, and this page asks for every
  // week so it can render the history. The figures say "this week", so they are
  // counted from this week's rows rather than from that whole-history total.
  const thisWeek = byWeek.get(body?.week ?? 1) ?? [];
  const spent = thisWeek
    .filter((o) => o.status === 'EXECUTED')
    .reduce((sum, o) => sum + o.amount_paise, 0);
  const delivered = thisWeek.filter((o) => o.status === 'EXECUTED').length;
  const stopped = thisWeek.filter((o) => o.status === 'REFUSED').length;

  return (
    <div data-v2 className="min-h-screen bg-bond font-sans text-ink">
      <nav className="sticky top-0 z-50 border-b border-rule bg-bond/85 backdrop-blur-[12px]">
        <div className="mx-auto flex h-[60px] max-w-[1100px] items-center gap-[26px] px-8 max-sm:px-[18px]">
          <Link to="/" aria-label="Mandate, by Razorpay">
            <MandateLockup />
          </Link>
          <span className="hidden text-[13.5px] text-ink-2 sm:inline">Weekly groceries</span>
          <div className="ml-auto flex items-center gap-3">
            <Button
              asChild
              variant="outline"
              size="sm"
              className="h-[38px] rounded-lg px-3.5 text-[13px]"
            >
              <Link to="/try">Console</Link>
            </Button>
          </div>
        </div>
      </nav>

      <main className="mx-auto max-w-[1100px] px-8 py-10 max-sm:px-[18px]">
        <header className="flex flex-wrap items-end justify-between gap-6 border-b border-rule pb-7">
          <div>
            <h1 className="text-[27px] font-medium tracking-[-0.025em] text-ink">Your orders</h1>
            <p className="mt-1.5 max-w-[46ch] text-[13.5px] leading-[1.55] text-ink-2">
              Placed by an agent shopping under your mandate. It names a SKU and a
              quantity. Everything else on these rows, prices included, is the
              gateway&rsquo;s.
            </p>
          </div>
          <div className="flex items-end gap-8">
            <Figure label="Spent this week" value={rupeesWhole(spent)} />
            <Figure label="Delivered" value={String(delivered)} />
            <Figure label="Stopped" value={String(stopped)} tone={stopped > 0 ? 'halt' : undefined} />
          </div>
        </header>

        <div className="flex flex-wrap items-center gap-3 py-5">
          {/* Each week's section header already names the week and its shelf, so
              this strip carries only the provenance and the control. */}
          {week?.corpus_hash && (
            <span className="font-mono text-[10.5px] uppercase tracking-[0.07em] text-ink-3">
              Shelves drawn from corpus{' '}
              <span className="normal-case text-ink-4">{week.corpus_hash.slice(7, 21)}</span>
            </span>
          )}
          <Button
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={advance}
            className="ml-auto h-[34px] rounded-lg px-3 text-[12.5px]"
          >
            {busy ? 'Restocking…' : 'Next week, new shelf'}
          </Button>
        </div>

        {offline && (
          <p className="rounded-panel border border-refer-line bg-refer-soft px-4 py-3 text-[13px] text-refer">
            The gateway is not answering, so this list may be stale. Start it with{' '}
            <span className="font-mono">mandate serve</span>.
          </p>
        )}

        {orders.length === 0 && !offline && (
          <div className="rounded-panel border border-dashed border-rule bg-sheet px-6 py-12 text-center">
            <p className="text-[15px] text-ink">Nothing ordered yet.</p>
            <p className="mx-auto mt-2 max-w-[52ch] text-[13.5px] leading-[1.55] text-ink-2">
              Point an MCP client at <span className="font-mono">/mcp</span> and ask it to
              shop for the week, or run the agent from the console. Orders land here as
              they are decided.
            </p>
            <Button
              asChild
              size="sm"
              className="mt-5 h-[38px] rounded-lg bg-[#2F5EFF] px-4 text-[13.5px] text-white hover:bg-[#254ED0]"
            >
              <Link to="/try">Open the console</Link>
            </Button>
          </div>
        )}

        {[...byWeek.keys()]
          .sort((a, b) => b - a)
          .map((n) => (
            <section key={n} className="mb-9">
              <div className="mb-3 flex items-baseline gap-3">
                <h2 className="text-[15px] font-medium tracking-[-0.015em] text-ink">Week {n}</h2>
                <span className="font-mono text-[10.5px] uppercase tracking-[0.07em] text-ink-3">
                  {familyOf(n) === 'clean' ? 'clean shelf' : `seller text: ${familyOf(n)}`}
                </span>
              </div>
              <ul className="flex flex-col gap-3">
                {(byWeek.get(n) ?? []).map((order, i) => (
                  <OrderCard key={order.order_id} order={order} index={i} reduced={reduced} />
                ))}
              </ul>
            </section>
          ))}
      </main>

      <footer className="mx-auto flex max-w-[1100px] flex-wrap items-center justify-between gap-4 px-8 py-7 text-[12.5px] text-ink-3 max-sm:px-[18px]">
        <span>A demonstration storefront. Orders reset when the instance restarts.</span>
        <span>Seller marks are drawn approximations, not official brand assets.</span>
      </footer>
    </div>
  );
}
