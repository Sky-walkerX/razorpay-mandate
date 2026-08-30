import { PARTS } from '@/data/policy';
import { readoutForPart } from '@/lib/constraintReadout';
import { StatusBadge } from './StatusBadge';
import { cn } from '@/lib/utils';

export function ConstraintChecks() {
  return (
    <div className="rounded-panel border border-rule bg-bond shadow-sheet">
      <div className="flex items-center border-b border-rule px-5 py-3.5">
        <h3 className="text-[14px] font-semibold tracking-[-0.02em]">Constraint checks</h3>
        <span className="ml-auto text-[11.5px] text-ink-3">9 parts, evaluated in order</span>
      </div>

      <div className="px-5 py-1.5">
        {PARTS.map((part) => {
          const r = readoutForPart(part);
          return (
            <div
              key={part.key}
              className="grid grid-cols-[150px_1fr_150px_78px] items-center gap-3.5 border-b border-hair py-2.25 last:border-b-0"
            >
              <div className={cn('truncate text-[12.5px]', r.status === 'halt' && 'font-medium text-halt')}>
                {part.label}
              </div>

              {part.kind === 'limit' && r.percent != null ? (
                <div className="h-1.5 rounded-full bg-hair">
                  <div
                    className={cn('h-full rounded-full', r.status === 'halt' ? 'bg-halt' : 'bg-indigo')}
                    style={{ width: `${Math.min(r.percent, 100)}%` }}
                  />
                </div>
              ) : (
                <div className="truncate font-mono text-[11px] text-ink-3">{part.bound}</div>
              )}

              <div
                className={cn(
                  'truncate text-right font-mono text-[11.5px]',
                  r.status === 'halt' ? 'font-medium text-halt' : 'text-ink-2',
                )}
              >
                {r.figure}
              </div>

              <StatusBadge
                tone={r.status}
                label={r.status === 'halt' ? 'refuses' : r.status === 'unset' ? 'unset' : 'pass'}
              />
            </div>
          );
        })}
      </div>
    </div>
  );
}
