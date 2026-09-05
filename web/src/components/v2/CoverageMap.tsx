import { useMemo, useState } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { cn } from '@/lib/utils';

import { PARTS } from '@/data/policy';
import { CAUSE_LABEL, EDGES, FAMILIES, PART_ORDER, UNCOVERED, type Cause } from '@/data/families';

const W = 900;
const TOP = 52;
const PITCH = 42;
const BOX_H = 28;
const LX = 8;
const LW = 250;
const RW = 214;
const RX = W - RW - LX;

const famY = (i: number) => TOP + i * PITCH;
const partY = (i: number) => TOP + PITCH / 2 + i * PITCH;

/** The right column, resolved against the signed policy for label and numeral. */
const COLUMN = PART_ORDER.map((key) => {
  const part = PARTS.find((p) => p.key === key);
  return { key, n: part?.n ?? 0, uncovered: UNCOVERED.has(key) };
});

const famIndex = new Map<string, number>(FAMILIES.map((f, i) => [f.id, i]));
const partIndex = new Map<string, number>(COLUMN.map((p, i) => [p.key, i]));

const LINKS = EDGES.map((e) => ({
  f: famIndex.get(e.family) ?? 0,
  p: partIndex.get(e.part) ?? 0,
}));

const GAP_BOTTOM = partY(COLUMN.length - 1) + BOX_H;
const HEIGHT = Math.max(famY(FAMILIES.length - 1) + BOX_H, GAP_BOTTOM + 40) + 20;

function Glyph({ cause, x, y }: { cause: Cause; x: number; y: number }) {
  if (cause === 'written') {
    return <path d={`M${x},${y + 8.5}L${x + 4.5},${y}L${x + 9},${y + 8.5}Z`} fill="currentColor" />;
  }
  if (cause === 'agent') {
    return <circle cx={x + 4.5} cy={y + 4.3} r={4.3} fill="currentColor" />;
  }
  return <rect x={x} y={y} width={8.6} height={8.6} fill="currentColor" />;
}

type Hot = { kind: 'f' | 'p'; i: number } | null;

export default function CoverageMap() {
  const reduced = useReducedMotion();
  const [hot, setHot] = useState<Hot>(null);

  const live = useMemo(() => {
    if (!hot) return null;
    const edges = new Set<number>();
    const fams = new Set<number>();
    const parts = new Set<number>();
    LINKS.forEach((l, i) => {
      if ((hot.kind === 'f' && l.f === hot.i) || (hot.kind === 'p' && l.p === hot.i)) {
        edges.add(i);
        fams.add(l.f);
        parts.add(l.p);
      }
    });
    if (hot.kind === 'f') fams.add(hot.i);
    else parts.add(hot.i);
    return { edges, fams, parts };
  }, [hot]);

  const nodeOpacity = (kind: 'f' | 'p', i: number) => {
    if (!live) return 'opacity-100';
    const on = kind === 'f' ? live.fams.has(i) : live.parts.has(i);
    return on ? 'opacity-100' : 'opacity-25 transition-opacity duration-200';
  };

  return (
    <div>
      <div className="-mx-1 overflow-x-auto px-1 pb-1">
        <svg
          viewBox={`0 0 ${W} ${HEIGHT}`}
          className="h-auto w-full min-w-[700px] select-none"
          role="img"
          aria-label={
            `${FAMILIES.length} attack families connected to the parts they target. ` +
            'Every part has a family pointing at it except repeat orders, which has none.'
          }
          onMouseLeave={() => setHot(null)}
        >
          <text
            x={LX + 2}
            y={30}
            className="fill-ink-3 font-mono text-[10px] uppercase tracking-[0.1em]"
          >
            attack family · 12 items each
          </text>
          <text
            x={RX + 2}
            y={30}
            className="fill-ink-3 font-mono text-[10px] uppercase tracking-[0.1em]"
          >
            the part that answers it
          </text>

          {/* Bezier curves */}
          {LINKS.map((l, i) => {
            const y1 = famY(l.f) + BOX_H / 2;
            const y2 = partY(l.p) + BOX_H / 2;
            const x1 = LX + LW;
            const mid = (x1 + RX) / 2;
            const on = live?.edges.has(i);

            return (
              <g key={i}>
                <motion.path
                  d={`M${x1},${y1}C${mid},${y1} ${mid},${y2} ${RX},${y2}`}
                  fill="none"
                  stroke={on ? 'var(--color-indigo)' : 'var(--color-rule)'}
                  strokeWidth={on ? 2 : 1.1}
                  className={cn('transition-all duration-200', live && !on && 'opacity-20')}
                  initial={reduced ? false : { pathLength: 0 }}
                  whileInView={reduced ? undefined : { pathLength: 1 }}
                  viewport={{ once: true, amount: 0.3 }}
                  transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1], delay: 0.1 + i * 0.03 }}
                />
              </g>
            );
          })}

          {/* Left Column: Attack Families */}
          {FAMILIES.map((f, i) => {
            const isHovered = hot?.kind === 'f' && hot.i === i;
            const isLinked = live?.fams.has(i);

            return (
              <g
                key={f.id}
                tabIndex={0}
                className={cn(
                  'cursor-pointer outline-none transition-all duration-200',
                  nodeOpacity('f', i),
                  isHovered || isLinked ? 'text-ink font-semibold' : 'text-ink-2'
                )}
                onMouseEnter={() => setHot({ kind: 'f', i })}
                onFocus={() => setHot({ kind: 'f', i })}
                onBlur={() => setHot(null)}
              >
                <rect
                  x={LX}
                  y={famY(i)}
                  width={LW}
                  height={BOX_H}
                  rx={7}
                  className={cn(
                    'transition-all duration-200',
                    isHovered
                      ? 'fill-indigo-soft stroke-indigo'
                      : isLinked
                      ? 'fill-sheet stroke-ink'
                      : 'fill-sheet stroke-rule hover:stroke-ink-3'
                  )}
                />
                <g className={isHovered ? 'text-indigo' : 'text-ink-3'}>
                  <Glyph cause={f.cause} x={LX + 12} y={famY(i) + 10} />
                </g>
                <text x={LX + 28} y={famY(i) + 18} className="fill-current font-mono text-[11px]">
                  {f.id}
                </text>
                {f.heldOut && (
                  <text
                    x={LX + LW - 11}
                    y={famY(i) + 18}
                    textAnchor="end"
                    className="fill-ink-4 font-mono text-[9px] tracking-[0.08em]"
                  >
                    HELD OUT
                  </text>
                )}
              </g>
            );
          })}

          {/* Right Column: the limits that answer, counted off PARTS. */}
          {COLUMN.map((p, i) => {
            const isHovered = hot?.kind === 'p' && hot.i === i;
            const isLinked = live?.parts.has(i);

            return (
              <g
                key={p.key}
                tabIndex={0}
                className={cn(
                  'cursor-pointer outline-none transition-all duration-200',
                  p.uncovered ? 'text-refer' : 'text-ink-2',
                  nodeOpacity('p', i),
                  isHovered || isLinked ? 'text-ink font-semibold' : ''
                )}
                onMouseEnter={() => setHot({ kind: 'p', i })}
                onFocus={() => setHot({ kind: 'p', i })}
                onBlur={() => setHot(null)}
              >
                <rect
                  x={RX}
                  y={partY(i)}
                  width={RW}
                  height={BOX_H}
                  rx={7}
                  strokeDasharray={p.uncovered ? '4 3' : undefined}
                  className={cn(
                    'transition-all duration-200',
                    p.uncovered
                      ? isHovered
                        ? 'fill-refer-soft stroke-refer ring-2 ring-refer/20'
                        : 'fill-refer-soft stroke-refer-line'
                      : isHovered
                      ? 'fill-indigo-soft stroke-indigo'
                      : isLinked
                      ? 'fill-sheet stroke-ink'
                      : 'fill-sheet stroke-rule hover:stroke-ink-3'
                  )}
                />
                <text x={RX + 12} y={partY(i) + 18} className="fill-current font-mono text-[11px]">
                  {p.key}
                </text>
                <text
                  x={RX + RW - 11}
                  y={partY(i) + 18}
                  textAnchor="end"
                  className="fill-ink-4 font-mono text-[9.5px]"
                >
                  {p.n}
                </text>
              </g>
            );
          })}

          {/* Declared gap under Part 9 */}
          <path
            d={`M${RX + 14},${GAP_BOTTOM}V${GAP_BOTTOM + 12}`}
            fill="none"
            strokeDasharray="3 3"
            className="stroke-refer-line"
            strokeWidth={1.1}
          />
          <text x={RX + 14} y={GAP_BOTTOM + 26} className="fill-refer font-mono text-[11px]">
            No family targets this.
          </text>
          <text x={RX + 14} y={GAP_BOTTOM + 40} className="fill-refer text-[11px]">
            Implemented, unit-tested, declared.
          </text>
        </svg>
      </div>

      <div className="mt-5 flex flex-wrap items-center gap-x-6 gap-y-2 border-t border-rule-soft pt-4 text-[12px] text-ink-2">
        {(['written', 'agent', 'rail'] as const).map((cause) => (
          <span key={cause} className="inline-flex items-center gap-2">
            <svg viewBox="0 0 10 10" className="size-[9px] text-ink-3" aria-hidden>
              <g className="text-ink-3">
                <Glyph cause={cause} x={0.5} y={0.7} />
              </g>
            </svg>
            <span className="font-mono text-xs">{CAUSE_LABEL[cause].toLowerCase()}</span>
          </span>
        ))}
        <span className="inline-flex items-center gap-2 font-mono text-xs text-refer">
          <span className="inline-block h-[9px] w-[15px] rounded-[2px] border border-dashed border-refer-line bg-refer-soft" />
          no family targets it (declared gap)
        </span>
      </div>
    </div>
  );
}
