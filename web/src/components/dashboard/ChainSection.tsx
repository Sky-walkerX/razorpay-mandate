import { chainEntries, spell } from '@/lib/runShape';
import { PARTS, SET_PART_COUNT_TEXT } from '@/data/policy';
import { rupees } from '@/lib/money';
import { cn } from '@/lib/utils';

/**
 * The audit chain, drawn as a chain.
 *
 * Every row carries the hash that links it to the one below, joined by a
 * hairline running through the markers, so "tamper-evident" is shown rather
 * than asserted. The marker shape carries the verdict, square for allowed,
 * diamond for refused, per the rule that hue is never the only signal.
 *
 * Long stretches of identical decisions collapse to a single line stating how
 * many there were. Fifty rows differing only in a hash are fifty rows a reader
 * skips; one line saying "forty-nine more, every one refused at Part 4" is the
 * same fact and the stronger claim. `chainEntries` does the collapsing, and it
 * always leaves the newest member of a stretch drawn in full.
 */

const shortHash = (h: string) => `${h.replace(/^sha256:/, '').slice(0, 12)}…`;

/** Sequence numbers are set in mono and read as a column, so they line up. */
const pad = (n: number) => String(n).padStart(2, '0');

/** "Part 4 · Orders per mandate, 3" reads better on one line as its label. */
function partFor(reason: string) {
  return PARTS.find((p) => reason.startsWith(`Part ${p.n} `)) ?? null;
}

export function ChainSection() {
  const entries = chainEntries();

  return (
    <div className="overflow-hidden rounded-panel border border-rule bg-bond shadow-sheet">
      {entries.map((e, i) => {
        const isLast = i === entries.length - 1;

        if (e.kind === 'elision') {
          const part = partFor(e.reason);
          return (
            <div
              key={`gap-${e.fromSeq}`}
              className="grid grid-cols-[14px_1fr_auto] items-center gap-3.5 border-b border-hair bg-sheet px-5 py-2.5 last:border-b-0"
            >
              <Link tone="dim" isLast={false} />
              <span className="min-w-0 text-[12.5px] leading-[1.5] text-ink-3">
                #{pad(e.toSeq)} through #{pad(e.fromSeq)} · {spell(e.count)} more,{' '}
                {e.verdict === 'deny' ? 'every one refused' : 'every one allowed'}
                {part && ` at Part ${part.n}`}
              </span>
              <span className="font-mono text-[10.5px] text-ink-4">·······</span>
            </div>
          );
        }

        const d = e.decision;
        const refused = d.verdict === 'deny';
        const part = partFor(d.reason);

        return (
          <div
            key={d.seq}
            className={cn(
              'grid grid-cols-[14px_1fr_auto] items-center gap-3.5 border-b border-hair px-5 py-2.5 last:border-b-0',
              'sm:grid-cols-[14px_1fr_auto_auto]',
            )}
          >
            <Link tone={refused ? 'halt' : 'pass'} isLast={isLast} />

            <div className="min-w-0 text-[12.5px]">
              <span className="font-mono text-ink-3">#{pad(d.seq)}</span>{' '}
              <span className="text-ink">
                {d.items}, {d.note}
              </span>
              <span className="ml-2 text-[11.5px] text-ink-3">
                {refused
                  ? part
                    ? `refused · Part ${part.n}, ${part.label.toLowerCase()}`
                    : 'refused'
                  : `allowed · all ${SET_PART_COUNT_TEXT} passed`}
              </span>
            </div>

            <span
              className={cn(
                'text-right font-mono text-[12.5px]',
                refused ? 'text-halt line-through decoration-1' : 'text-pass',
              )}
            >
              {rupees(d.amountPaise)}
            </span>

            <span className="hidden font-mono text-[10.5px] text-ink-4 sm:inline">
              {shortHash(d.hash)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

/**
 * One link in the chain: a marker with the hairline running through it. The
 * line stops at the last row because nothing links below it.
 */
function Link({ tone, isLast }: { tone: 'pass' | 'halt' | 'dim'; isLast: boolean }) {
  return (
    <span aria-hidden className="relative flex h-full w-[14px] justify-center">
      <span
        className={cn('absolute -top-3 w-px bg-rule', isLast ? 'h-3' : '-bottom-3')}
      />
      <span
        className={cn(
          'relative size-[7px] self-center shadow-[0_0_0_3px_var(--color-bond)]',
          tone === 'pass' && 'bg-pass',
          tone === 'halt' && 'rotate-45 bg-halt',
          tone === 'dim' && 'rounded-full bg-ink-4',
        )}
      />
    </span>
  );
}
