import { PARTS } from '@/data/policy';
import { readoutForPart } from '@/lib/constraintReadout';
import { bindingPart } from '@/lib/runShape';
import { StatusBadge } from './StatusBadge';
import { cn } from '@/lib/utils';

/**
 * The parts as they stood when the run ended.
 *
 * One joined surface with shared hairlines rather than nine cards, matching
 * `PartsGrid` on the landing page: a closed set should look like a closed set.
 * The part that did the refusing is the only cell carrying `halt` ink, so the
 * grid answers "which one bound?" before any of it is read.
 *
 * Figures come from `readoutForPart`, which aggregates the same replayed
 * decisions the strip above draws, so no cell can disagree with the drawing.
 */
export function PartsAtEnd() {
  const binding = bindingPart();

  return (
    <div className="overflow-hidden rounded-panel border border-rule bg-bond shadow-sheet">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3">
        {PARTS.map((part) => {
          const r = readoutForPart(part);
          const isBinding = binding?.part.key === part.key;

          return (
            <div
              key={part.key}
              className={cn(
                'flex flex-col gap-1 border-b border-rule-soft p-[18px] last:border-b-0',
                'sm:border-r sm:[&:nth-child(2n)]:border-r-0 sm:[&:nth-last-child(-n+1)]:border-b-0',
                'lg:[&:nth-child(2n)]:border-r lg:[&:nth-child(3n)]:border-r-0 lg:[&:nth-last-child(-n+3)]:border-b-0',
                isBinding && 'bg-halt-soft',
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span
                  className={cn(
                    'font-mono text-[9.5px] uppercase tracking-[0.1em]',
                    isBinding ? 'text-halt' : 'text-ink-4',
                  )}
                >
                  Part {part.n} · {part.kind}
                </span>
                <StatusBadge
                  tone={r.status}
                  label={r.status === 'halt' ? 'refuses' : r.status === 'unset' ? 'unset' : 'pass'}
                />
              </div>

              <div
                className={cn(
                  'text-[13.5px] font-medium tracking-[-0.02em]',
                  isBinding && 'text-halt',
                )}
              >
                {part.label}
              </div>

              <div
                className={cn(
                  'font-mono text-[11.5px]',
                  isBinding ? 'text-halt' : 'text-ink-3',
                )}
              >
                {r.figure}
              </div>

              {/* A limit gets its track; a rule has nothing to fill. */}
              {r.percent != null ? (
                <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-hair">
                  <div
                    className={cn('h-full rounded-full', isBinding ? 'bg-halt' : 'bg-indigo')}
                    style={{ width: `${Math.min(r.percent, 100)}%` }}
                  />
                </div>
              ) : (
                <div className="mt-1.5 text-[11.5px] leading-[1.45] text-ink-4">{r.sub}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
