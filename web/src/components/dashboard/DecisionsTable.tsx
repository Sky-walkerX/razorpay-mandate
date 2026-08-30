import { DECISIONS } from '@/data/decisions';
import { rupees } from '@/lib/money';
import { cn } from '@/lib/utils';
import { StatusBadge } from './StatusBadge';

const WORD = { allow: 'allowed', deny: 'refused', unknown: 'needs you' } as const;

function cap(s: string) {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export function DecisionsTable({ limit = 7 }: { limit?: number }) {
  const rows = DECISIONS.slice(0, limit);

  return (
    <div className="rounded-panel border border-rule bg-bond shadow-sheet">
      <div className="flex items-center border-b border-rule px-5 py-3.5">
        <h3 className="text-[14px] font-semibold tracking-[-0.02em]">Recent decisions</h3>
        <span className="ml-auto text-[11.5px] text-ink-3">
          last {rows.length} of {DECISIONS.length}
        </span>
      </div>

      <div>
        {rows.map((d) => (
          <div
            key={d.seq}
            className={cn(
              'grid grid-cols-[92px_1fr_auto] items-center gap-3.5 px-5 py-2.5',
              'border-b border-hair last:border-b-0',
              d.verdict === 'deny' && 'bg-halt-soft/60',
              d.verdict === 'unknown' && 'bg-refer-soft/60',
            )}
          >
            <StatusBadge
              tone={d.verdict === 'allow' ? 'pass' : d.verdict === 'deny' ? 'halt' : 'refer'}
              label={WORD[d.verdict]}
            />

            <div className="min-w-0 truncate text-[13px]">
              #{String(d.seq).padStart(2, '0')} · {d.items}
              <span className="ml-2 text-[11.5px] text-ink-3">
                {d.reason || 'nothing was breached'}
              </span>
            </div>

            <div className={cn('text-right font-mono text-[13px]', d.verdict === 'deny' && 'text-halt line-through decoration-1')}>
              {rupees(d.amountPaise)}
              <span className="mt-0.5 block font-mono text-[10px] font-normal text-ink-3 no-underline">
                {cap(d.seller)} · {d.note}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
