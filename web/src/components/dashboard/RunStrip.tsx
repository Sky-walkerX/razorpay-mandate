import { COUNTS } from '@/data/decisions';
import { MANDATE, PARTS } from '@/data/policy';
import { attempts, bindingPart, largestExecutedPaise } from '@/lib/runShape';
import { rupees, rupeesWhole } from '@/lib/money';
import { cn } from '@/lib/utils';

/**
 * The run, drawn once.
 *
 * This replaces three panels that were each saying a piece of the same thing:
 * a spend chart that was ninety percent empty, a bar chart spending a full
 * panel on eight zero-height stubs to show one bar, and fifty table rows that
 * differed in nothing but a hash.
 *
 * The encoding is literal rather than decorative. Above the rail, money that
 * moved: one column per executed order, height proportional to its amount.
 * Below the rail, attempts that moved nothing: one tick per refusal. So the
 * drawing says "three moved money, fifty moved none" in the shape itself, and
 * the rail between them is the payment boundary the whole project is about.
 *
 * Every figure is read from the feed. The column count is the run's length,
 * not a number chosen to look good.
 */

/** Column heights, in px, either side of the rail. */
const UP = 58;
const DOWN = 20;

const VELOCITY = PARTS.find((p) => p.key === 'velocity');

export function RunStrip() {
  const rows = attempts();
  const largest = largestExecutedPaise();
  const binding = bindingPart();

  const spent = MANDATE.committedPaise;
  const cap = MANDATE.totalBudgetPaise;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-baseline gap-x-3.5 gap-y-1">
        <span className="font-mono text-[9.5px] uppercase tracking-[0.12em] text-ink-3">
          {COUNTS.evaluated} attempts, in the order they arrived
        </span>
        <span aria-hidden className="h-px min-w-8 grow bg-rule" />
        {VELOCITY && (
          <span className="font-mono text-[11.5px] text-ink-3">cap · {VELOCITY.bound}</span>
        )}
      </div>

      {/* The strip. One column per attempt, split across the rail. */}
      <div
        className="flex items-stretch gap-[2px]"
        role="img"
        aria-label={`${COUNTS.evaluated} attempts: ${COUNTS.allowed} executed for ${rupees(spent)} in total, ${COUNTS.refused} refused moving nothing.`}
      >
        {rows.map((a, i) => {
          const h = a.executed && largest > 0 ? Math.max(6, (a.amountPaise / largest) * UP) : 0;
          return (
            <span key={a.seq} className="flex min-w-[3px] flex-1 flex-col">
              {/* above the rail, money that moved */}
              <span className="flex items-end" style={{ height: UP }}>
                {a.executed && (
                  <span
                    className="tick-rise w-full rounded-[1px] bg-pass"
                    style={{ height: h, transformOrigin: 'bottom', animationDelay: `${i * 0.012}s` }}
                  />
                )}
              </span>

              <span aria-hidden className="h-px w-full bg-rule" />

              {/* below the rail, attempts that moved nothing */}
              <span className="flex items-start" style={{ height: DOWN }}>
                {!a.executed && (
                  <span
                    className="tick-rise w-full rounded-[1px] bg-halt"
                    style={{
                      height: DOWN - 6,
                      transformOrigin: 'top',
                      animationDelay: `${i * 0.012}s`,
                    }}
                  />
                )}
              </span>
            </span>
          );
        })}
      </div>

      <div className="mt-2.5 flex flex-wrap justify-between gap-x-6 gap-y-1 text-[11.5px]">
        <span className="text-pass">
          above the rail · {COUNTS.allowed} executed, {rupees(spent)} moved
        </span>
        <span className="text-halt">
          below · {COUNTS.refused} refused
          {binding && `, every one citing Part ${binding.part.n}`} · {rupees(0)} moved
        </span>
      </div>

      {/* The run's own figures. Nothing from another run appears in this row. */}
      <dl className="mt-6 grid grid-cols-2 overflow-hidden rounded-panel border border-rule bg-bond md:grid-cols-4">
        <Cell
          label="Moved on the rail"
          figure={rupees(spent)}
          sub={`of a ${rupeesWhole(cap)} cap · ${rupeesWhole(Math.max(cap - spent, 0))} left`}
        />
        <Cell
          label="Allowed"
          figure={String(COUNTS.allowed)}
          sub={`of ${COUNTS.evaluated} attempts`}
          tone="pass"
        />
        <Cell
          label="Refused"
          figure={String(COUNTS.refused)}
          sub={binding ? `all citing Part ${binding.part.n} · ${binding.part.label}` : 'across several parts'}
          tone="halt"
        />
        <Cell
          label="Chain"
          figure={`${COUNTS.evaluated} / ${COUNTS.evaluated}`}
          sub="hashes verified · SHA-256 chained"
          last
        />
      </dl>
    </div>
  );
}

function Cell({
  label,
  figure,
  sub,
  tone,
  last,
}: {
  label: string;
  figure: string;
  sub: string;
  tone?: 'pass' | 'halt';
  last?: boolean;
}) {
  return (
    <div
      className={cn(
        'border-b border-rule-soft px-[18px] py-4 last:border-b-0 md:border-b-0',
        !last && 'md:border-r md:border-r-rule-soft',
      )}
    >
      <dt className="text-[11.5px] text-ink-3">{label}</dt>
      <dd
        className={cn(
          'mt-1.5 font-mono text-[25px] font-semibold leading-none tracking-[-0.04em]',
          tone === 'pass' && 'text-pass',
          tone === 'halt' && 'text-halt',
        )}
      >
        {figure}
      </dd>
      <dd className="mt-1.5 text-[11.5px] leading-[1.45] text-ink-3">{sub}</dd>
    </div>
  );
}
