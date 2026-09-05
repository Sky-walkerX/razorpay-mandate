import { Link } from 'react-router-dom';
import { motion, useReducedMotion } from 'motion/react';
import { Button } from '@/components/ui/button';

const EASE = [0.22, 0.61, 0.36, 1] as const;

/**
 * The way in to /store.
 *
 * The storefront had exactly one inbound link in the whole app -- on /approve,
 * which is itself a page you arrive at by scanning a QR from /try. So the
 * screen that shows an agent shopping a whole week, and the one place an order
 * placed by someone else's MCP client becomes visible, was three hops from
 * anywhere and in nobody's path.
 *
 * The nav link is the fix. This card is what makes anyone press it: a route in
 * a menu says a page exists, and says nothing about why it is worth opening.
 */
export default function StoreCard() {
  const reduced = useReducedMotion();

  return (
    <section className="border-b border-rule bg-bond py-20">
      <div className="mx-auto max-w-[1220px] px-8 max-sm:px-[18px]">
        <motion.div
          className="grid overflow-hidden rounded-panel border border-rule bg-raise shadow-sheet md:grid-cols-[minmax(0,1fr)_300px]"
          initial={reduced ? false : { opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, margin: '-60px' }}
          transition={{ duration: 0.45, ease: EASE }}
        >
          <div className="p-7 max-sm:p-6">
            <span className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
              The shop’s side of it
            </span>
            <h2 className="mt-2 max-w-[520px] text-[21px] font-semibold leading-[1.2] tracking-[-0.026em] text-ink">
              Watch it shop for a week, from behind the counter.
            </h2>
            <p className="mt-[10px] max-w-[480px] text-[13.5px] leading-[1.6] text-ink-2">
              Orders arrive from three places — the console’s agent, a client someone pointed at the
              MCP endpoint, or a direct call. Each row says which it was, and what the gateway
              decided about it.
            </p>
            <div className="mt-[18px] flex flex-wrap items-center gap-[10px]">
              <Button asChild size="sm" className="h-[38px] rounded-lg bg-[#2F5EFF] px-4 text-[13.5px] text-white hover:bg-[#254ED0]">
                <Link to="/store">Open the shop</Link>
              </Button>
              <span className="text-[12.5px] text-ink-3">
                no session needed — it is the shop’s own record
              </span>
            </div>
          </div>

          <div className="flex flex-col justify-center gap-[7px] border-rule-soft bg-sheet p-5 max-md:border-t md:border-l">
            <Row source="MCP client" verdict="₹431.00" tone="pass" />
            <Row source="Console agent" verdict="refused" tone="halt" />
            <Row source="Direct API" verdict="₹198.00" tone="pass" />
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function Row({ source, verdict, tone }: { source: string; verdict: string; tone: 'pass' | 'halt' }) {
  const skin =
    tone === 'pass' ? 'border-pass-line bg-pass-soft text-pass' : 'border-halt-line bg-halt-soft text-halt';
  return (
    <div className={`flex items-center justify-between rounded-md border px-[10px] py-2 ${skin}`}>
      <span className="font-mono text-[10.5px] text-ink-2">{source}</span>
      <span className="font-mono text-[10.5px]">{verdict}</span>
    </div>
  );
}
