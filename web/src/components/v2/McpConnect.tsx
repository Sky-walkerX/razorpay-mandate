import { useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { Check, Copy, Lock } from 'lucide-react';
import { API_BASE } from '@/lib/api';
import { SURFACE } from '@/data/alignment';
import { cn } from '@/lib/utils';

const EASE = [0.22, 0.61, 0.36, 1] as const;

/**
 * How to point your own client at this gateway.
 *
 * "The agent holds no Razorpay credentials, only a handle to the gateway" was
 * the reason the MCP surface was built, and it is the one claim a judge can
 * disprove themselves rather than take on trust. It reached the interface as a
 * single sentence in the /store empty state -- on a page with one inbound link,
 * and only while nobody had ordered anything yet.
 *
 * The two surfaces authenticate differently and the copy says so, because
 * getting it wrong wastes the reader's first attempt:
 *
 *   /mcp           streamable HTTP, so it needs the MCP handshake. A bare curl
 *                  gets `Missing session ID`. Point a real client at it.
 *   /mcp/razorpay  mounted stateless, so `tools/list` answers a plain POST with
 *                  no handshake and no credential -- curl-able exactly the way
 *                  `mcp.razorpay.com/mcp` is, which is the whole comparison.
 *                  `tools/call` needs a bearer, and refuses with a named clause.
 *
 * The URLs are built from `API_BASE` and the page's own origin rather than
 * typed, for the reason `lib/api.ts` exists at all.
 */

const ORIGIN =
  API_BASE || (typeof window !== 'undefined' ? window.location.origin : '');

const TOOLS: { name: string; note: string; spends?: boolean }[] = [
  { name: 'search_catalog', note: 'the shelf, with descriptions, sellers and reviews' },
  { name: 'create_order', note: 'the basket, as {sku, qty}', spends: true },
  { name: 'check_budget', note: 'what is left under each limit' },
  { name: 'list_orders', note: 'what this session has bought' },
  { name: 'explain_refusal', note: 'why a limit refused, in full' },
  { name: 'get_mandate', note: 'the signed policy and its hash' },
];

const CLIENT_CONFIG = `{
  "mcpServers": {
    "mandate": {
      "url": "${'{origin}'}/mcp",
      "headers": { "Authorization": "Bearer <your token>" }
    }
  }
}`;

const LIST_CURL = `curl -s ${'{origin}'}/mcp/razorpay \\
  -H 'content-type: application/json' \\
  -H 'accept: application/json, text/event-stream' \\
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'`;

const REFUSAL = `{
  "allowed": false,
  "tool": "create_payment_link",
  "verdict": "DENY",
  "clause": "authentication",
  "message": "this surface reaches a real Razorpay
              account and needs a mandate token."
}`;

export default function McpConnect() {
  const reduced = useReducedMotion();

  return (
    <section id="connect" className="border-b border-rule bg-sheet py-20">
      <div className="mx-auto max-w-[1220px] px-8 max-sm:px-[18px]">

        <div className="max-w-[700px]">
          <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
            Test it yourself
          </span>
          <h2 className="mt-2 text-[clamp(1.7rem,3vw,1.9rem)] font-semibold leading-[1.12] tracking-[-0.032em] text-ink">
            Point your own client at it.
          </h2>
          <p className="mt-3 text-[14.5px] leading-[1.6] text-ink-2">
            The agent holds no Razorpay credentials — only a handle to this gateway. The handle is
            a URL, so you can hold it too. Two surfaces are open, and neither has a second path to
            the rail behind it.
          </p>
        </div>

        <div className="mt-7 grid gap-4 lg:grid-cols-2">

          <Card
            reduced={reduced}
            delay={0}
            title="The shopping surface"
            chip="6 tools · 1 spends"
            blurb="What an agent gets instead of your keys. Streamable HTTP, so it needs the MCP handshake and a bearer — point a real client at it rather than curl."
            url={`${ORIGIN}/mcp`}
          >
            <ul className="mt-4 flex flex-col gap-2">
              {TOOLS.map((t) => (
                <li key={t.name} className="flex items-baseline gap-[9px]">
                  <span
                    className={cn(
                      'mt-[6px] size-[5px] shrink-0 rounded-full',
                      t.spends ? 'bg-indigo' : 'bg-ink-4',
                    )}
                  />
                  <span className="text-[12.5px] leading-[1.45]">
                    <span className="font-mono text-ink">{t.name}</span>
                    {t.spends ? (
                      <span className="ml-[7px] rounded-full border border-indigo/25 bg-indigo-soft px-[7px] py-px font-mono text-[9.5px] tracking-[0.05em] text-indigo">
                        MOVES MONEY
                      </span>
                    ) : null}
                    <span className="text-ink-3"> — {t.note}</span>
                  </span>
                </li>
              ))}
            </ul>
            <Code label="claude_desktop_config.json" text={CLIENT_CONFIG.replace(/\{origin\}/g, ORIGIN)} />
            <p className="mt-3 text-[12.5px] leading-[1.5] text-ink-3">
              <span className="font-mono text-ink-2">create_order</span> takes a SKU and a quantity
              and nothing else. There is no price field to lie in — the gateway prices the basket
              from its own catalog, and that resolved figure is the one that reaches the rail.
            </p>
          </Card>

          <Card
            reduced={reduced}
            delay={0.08}
            title="Razorpay’s own surface, mediated"
            chip={`${SURFACE.total} tools`}
            blurb="The same tools Razorpay’s public MCP server offers, behind the mandate. Mounted stateless, so one curl lists them — exactly as it lists the real one’s."
            url={`${ORIGIN}/mcp/razorpay`}
          >
            <div className="mt-4 grid grid-cols-3 gap-2">
              <Count n={SURFACE.bound.length} tone="indigo" label="checked against the mandate" />
              <Count n={SURFACE.refused.length} tone="halt" label="refused — no limit can decide them" />
              <Count n={SURFACE.passthroughCount} tone="plain" label="read-only, passed through" />
            </div>
            <Code label="tools/list · no credential needed" text={LIST_CURL.replace(/\{origin\}/g, ORIGIN)} />
            <p className="mt-3 text-[12.5px] leading-[1.5] text-ink-3">
              Calling one is where it differs. The list is open; spending is not.
            </p>
            <Code label="tools/call · without a token" text={REFUSAL} tone="halt" />
          </Card>

        </div>

        <div className="mt-4 flex items-center gap-[14px] rounded-panel border border-pass-line bg-pass-soft px-[22px] py-[17px] max-sm:px-5">
          <Lock aria-hidden className="size-[17px] shrink-0 text-pass" strokeWidth={2} />
          <p className="text-[13.5px] leading-[1.55] text-ink-2">
            <b className="text-ink">Every tool that moves money reaches the same check.</b> Break the
            gateway’s decision and the rail stops for both surfaces — there is no second path to
            Razorpay, and a tool nobody has classified is refused rather than forwarded.
          </p>
        </div>

      </div>
    </section>
  );
}

function Card({
  title, chip, blurb, url, children, reduced, delay,
}: {
  title: string; chip: string; blurb: string; url: string;
  children: React.ReactNode; reduced: boolean | null; delay: number;
}) {
  return (
    <motion.div
      // `min-w-0` is load-bearing, not tidiness. A grid item defaults to
      // `min-width: auto`, so the widest <pre> in here sets the card's floor and
      // the card pushes the page 97px past a 390 viewport. The code blocks
      // scroll inside themselves instead.
      className="min-w-0 rounded-panel border border-rule bg-raise p-6 shadow-sheet max-sm:p-5"
      initial={reduced ? false : { opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.45, delay, ease: EASE }}
    >
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-[16px] font-semibold tracking-[-0.02em] text-ink">{title}</h3>
        <span className="shrink-0 rounded-full border border-rule bg-sunk px-[9px] py-[3px] font-mono text-[10px] text-ink-2">
          {chip}
        </span>
      </div>
      <p className="mb-4 mt-[9px] text-[13px] leading-[1.55] text-ink-2">{blurb}</p>
      <CopyRow url={url} />
      {children}
    </motion.div>
  );
}

function CopyRow({ url }: { url: string }) {
  const [done, setDone] = useState(false);
  return (
    <div className="flex items-center gap-[10px] rounded-lg border border-rule bg-bond py-[9px] pl-[13px] pr-[10px]">
      <span className="grow overflow-hidden text-ellipsis whitespace-nowrap font-mono text-[12.5px] text-ink">
        {url}
      </span>
      <button
        type="button"
        aria-label={`Copy ${url}`}
        onClick={() => {
          navigator.clipboard?.writeText(url).then(
            () => { setDone(true); window.setTimeout(() => setDone(false), 1600); },
            () => undefined,
          );
        }}
        className="inline-flex shrink-0 items-center gap-[6px] rounded-md border border-rule bg-sheet px-[9px] py-1 text-[11.5px] text-ink-2 transition-colors hover:border-ink-4 hover:text-ink"
      >
        {done ? <Check aria-hidden className="size-3 text-pass" strokeWidth={2.6} />
              : <Copy aria-hidden className="size-3" strokeWidth={2} />}
        {done ? 'Copied' : 'Copy'}
      </button>
    </div>
  );
}

function Code({ label, text, tone = 'plain' }: { label: string; text: string; tone?: 'plain' | 'halt' }) {
  return (
    <div
      className={cn(
        'mt-3 overflow-hidden rounded-lg border',
        tone === 'halt' ? 'border-halt-line bg-halt-soft' : 'border-rule bg-bond',
      )}
    >
      <div
        className={cn(
          'border-b px-3 py-[7px]',
          tone === 'halt' ? 'border-halt-line/60 bg-halt-soft' : 'border-rule-soft bg-sheet',
        )}
      >
        <span
          className={cn(
            'font-mono text-[10px] uppercase tracking-[0.1em]',
            tone === 'halt' ? 'text-halt' : 'text-ink-3',
          )}
        >
          {label}
        </span>
      </div>
      <pre
        className={cn(
          'overflow-x-auto px-[14px] py-[13px] font-mono text-[11.5px] leading-[1.65]',
          tone === 'halt' ? 'text-halt' : 'text-ink',
        )}
      >
        {text}
      </pre>
    </div>
  );
}

function Count({ n, label, tone }: { n: number; label: string; tone: 'indigo' | 'halt' | 'plain' }) {
  const skin =
    tone === 'indigo' ? 'border-indigo/25 bg-indigo-soft text-indigo'
    : tone === 'halt' ? 'border-halt-line bg-halt-soft text-halt'
    : 'border-rule bg-sunk text-ink';
  return (
    <div className={cn('rounded-lg border px-3 py-[11px]', skin)}>
      <div className="text-[19px] font-semibold tracking-[-0.03em]">{n}</div>
      <div className="mt-[3px] text-[11.5px] leading-[1.35] text-ink-2">{label}</div>
    </div>
  );
}
