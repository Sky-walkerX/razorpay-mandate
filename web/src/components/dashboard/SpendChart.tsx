import { useMemo } from 'react';
import { DECISIONS } from '@/data/decisions';
import { MANDATE } from '@/data/policy';
import { buildSpendSeries } from '@/lib/constraintReadout';
import { rupees, rupeesWhole } from '@/lib/money';

const W = 800;
const H = 240;
const PAD_L = 56;
const PAD_R = 20;
const PAD_T = 18;
const PAD_B = 40;
const PLOT_W = W - PAD_L - PAD_R;
const PLOT_H = H - PAD_T - PAD_B;

function stepPath(pts: { x: number; y: number }[]): string {
  if (pts.length === 0) return '';
  let d = `M${pts[0].x},${pts[0].y}`;
  for (let i = 1; i < pts.length; i++) {
    d += ` L${pts[i].x},${pts[i - 1].y} L${pts[i].x},${pts[i].y}`;
  }
  return d;
}

export function SpendChart() {
  const total = MANDATE.totalBudgetPaise;

  const chart = useMemo(() => {
    const series = buildSpendSeries();
    const x = (seq: number) => PAD_L + (series.count > 0 ? (seq / series.count) * PLOT_W : 0);
    const y = (paise: number) => PAD_T + PLOT_H - Math.min(paise / total, 1) * PLOT_H;

    const pts = series.points.map((p) => ({ x: x(p.seq), y: y(p.paise) }));
    const linePath = stepPath(pts);
    const areaPath = `${linePath} L${pts[pts.length - 1].x},${y(0)} L${pts[0].x},${y(0)} Z`;

    const lastExecuted = [...DECISIONS]
      .filter((d) => d.executed)
      .sort((a, b) => b.seq - a.seq)[0];

    return {
      linePath,
      areaPath,
      dots: pts.slice(0, -1),
      refusedTicks: series.refusedSeqs.map((seq) => x(seq)),
      finalPaise: series.finalPaise,
      count: series.count,
      refusedCount: series.refusedSeqs.length,
      lastExecuted,
      calloutX: x(lastExecuted?.seq ?? 0),
      calloutY: y(series.finalPaise),
    };
  }, [total]);

  const gridFractions = [0, 0.25, 0.5, 0.75, 1];

  return (
    <div className="rounded-panel border border-rule bg-bond px-5 pb-4 pt-4.5 shadow-sheet">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[14px] font-semibold tracking-[-0.02em]">Spend against the mandate</h3>
        <span className="ml-auto font-mono text-[11.5px] text-ink-3">{chart.count} attempts</span>
      </div>

      <svg viewBox={`0 0 ${W} ${H}`} className="mt-2.5 w-full overflow-visible">
        {gridFractions.map((f) => {
          const gy = PAD_T + PLOT_H - f * PLOT_H;
          return (
            <g key={f}>
              <line
                x1={PAD_L}
                y1={gy}
                x2={W - PAD_R}
                y2={gy}
                stroke={f === 1 ? 'var(--color-ink-4)' : 'var(--color-rule-soft)'}
                strokeWidth={1}
                strokeDasharray={f === 1 ? '3 4' : undefined}
              />
              <text x={PAD_L - 8} y={gy + 3.5} textAnchor="end" fontSize="10.5" fill="var(--color-ink-3)" fontFamily="var(--font-mono)">
                {f === 0 ? '0' : rupeesWhole(total * f).replace('₹', '')}
              </text>
            </g>
          );
        })}
        <text x={W - PAD_R + 2} y={PAD_T + 4} fontSize="10.5" fill="var(--color-ink-3)" fontFamily="var(--font-mono)">
          total cap
        </text>

        {chart.refusedTicks.map((tx, i) => (
          <line
            key={i}
            x1={tx}
            y1={H - PAD_B + 3}
            x2={tx}
            y2={H - PAD_B + 10}
            stroke="var(--color-halt)"
            strokeWidth={1.4}
            opacity={0.55}
          />
        ))}
        {chart.refusedCount > 0 && (
          <text
            x={PAD_L + PLOT_W / 2}
            y={H - 6}
            textAnchor="middle"
            fontSize="11"
            fill="var(--color-halt)"
          >
            {chart.refusedCount} more attempt{chart.refusedCount === 1 ? '' : 's'}, every one refused at the same cap
          </text>
        )}

        <path d={chart.areaPath} fill="var(--color-pass)" opacity={0.08} />
        <path d={chart.linePath} fill="none" stroke="var(--color-pass)" strokeWidth={2.2} strokeLinejoin="round" />
        {chart.dots.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r={i === chart.dots.length - 1 ? 3.4 : 3} fill="var(--color-pass)" />
        ))}

        {chart.lastExecuted && (
          <g>
            <rect
              x={Math.min(chart.calloutX + 12, W - PAD_R - 200)}
              y={Math.max(chart.calloutY - 58, PAD_T + 4)}
              width={196}
              height={50}
              rx={9}
              fill="var(--color-bond)"
              stroke="var(--color-rule)"
            />
            <text
              x={Math.min(chart.calloutX + 24, W - PAD_R - 188)}
              y={Math.max(chart.calloutY - 58, PAD_T + 4) + 20}
              fontSize="12"
              fontWeight={600}
              fill="var(--color-ink)"
            >
              Order #{String(chart.lastExecuted.seq).padStart(2, '0')} · {chart.lastExecuted.seller}
            </text>
            <text
              x={Math.min(chart.calloutX + 24, W - PAD_R - 188)}
              y={Math.max(chart.calloutY - 58, PAD_T + 4) + 38}
              fontSize="11"
              fill="var(--color-ink-2)"
              fontFamily="var(--font-mono)"
            >
              {rupees(chart.lastExecuted.amountPaise)} → {rupees(chart.finalPaise)} total
            </text>
          </g>
        )}
      </svg>
    </div>
  );
}
