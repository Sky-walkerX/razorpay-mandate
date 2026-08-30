import { citedCounts } from '@/lib/constraintReadout';

const BAR_W = 20;
const GAP = 12;
const TRACK_H = 96;
const BASE_Y = 128;

export function RefusalsByConstraint() {
  const counts = citedCounts();
  const max = Math.max(1, ...counts.map((c) => c.count));
  const totalCited = counts.reduce((s, c) => s + c.count, 0);
  const binding = [...counts].sort((a, b) => b.count - a.count)[0];
  const isSole = binding && binding.count > 0 && binding.count === totalCited;

  return (
    <div className="rounded-panel border border-rule bg-bond px-4.5 py-4 shadow-sheet">
      <h3 className="text-[13px] font-semibold tracking-[-0.02em]">Refusals by constraint</h3>

      <svg viewBox="0 0 300 170" className="mt-2.5 w-full">
        <line x1="10" y1={BASE_Y} x2="290" y2={BASE_Y} stroke="var(--color-rule)" />
        {counts.map(({ part, count }, i) => {
          const h = count > 0 ? (count / max) * TRACK_H : 2;
          const x = 16 + i * (BAR_W + GAP - 6);
          const isBinding = count > 0;
          return (
            <g key={part.key}>
              <rect
                x={x}
                y={BASE_Y - h}
                width={BAR_W}
                height={h}
                rx={2}
                fill={isBinding ? 'var(--color-halt)' : 'var(--color-rule)'}
              />
              <text
                x={x + BAR_W / 2}
                y={BASE_Y + 15}
                textAnchor="middle"
                fontSize="8.5"
                fontFamily="var(--font-mono)"
                fill={isBinding ? 'var(--color-halt)' : 'var(--color-ink-3)'}
                fontWeight={isBinding ? 600 : 400}
              >
                {part.n}
              </text>
              {isBinding && (
                <text
                  x={x + BAR_W / 2}
                  y={BASE_Y - h - 6}
                  textAnchor="middle"
                  fontSize="12"
                  fontWeight={700}
                  fontFamily="var(--font-mono)"
                  fill="var(--color-halt)"
                >
                  {count}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <div className="mt-1.5 text-[11px] leading-normal text-ink-3">
        {binding.count > 0 ? (
          <>
            {isSole ? 'Every refusal cites' : `${binding.count} of ${totalCited} refusals cite`}{' '}
            <b className="font-medium text-ink-2">
              Part {binding.part.n} · {binding.part.label}
            </b>
            .
          </>
        ) : (
          'No decision has been refused yet.'
        )}
      </div>
    </div>
  );
}
