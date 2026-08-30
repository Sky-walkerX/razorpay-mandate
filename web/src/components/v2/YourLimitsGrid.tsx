import React from 'react';
import {
  Banknote,
  Receipt,
  ShoppingBag,
  Zap,
  Boxes,
  Store,
  Ban,
  Clock,
  RotateCcw,
} from 'lucide-react';
import { PARTS, type Part } from '@/data/policy';
import { cn } from '@/lib/utils';

interface LimitCardProps {
  part: Part;
  index: number;
}

const PART_ICONS: Record<number, React.ReactNode> = {
  1: <Banknote className="size-5" />,
  2: <Receipt className="size-5" />,
  3: <ShoppingBag className="size-5" />,
  4: <Zap className="size-5" />,
  5: <Boxes className="size-5" />,
  6: <Store className="size-5" />,
  7: <Ban className="size-5" />,
  8: <Clock className="size-5" />,
  9: <RotateCcw className="size-5" />,
};

const ACCENT_COLORS: Record<number, { bar: string; glow: string; text: string; bg: string }> = {
  1: { bar: 'bg-pass', glow: 'from-pass-soft/80', text: 'text-pass', bg: 'bg-pass-soft' },
  2: { bar: 'bg-pass', glow: 'from-pass-soft/80', text: 'text-pass', bg: 'bg-pass-soft' },
  3: { bar: 'bg-pass', glow: 'from-pass-soft/80', text: 'text-pass', bg: 'bg-pass-soft' },
  4: { bar: 'bg-indigo', glow: 'from-indigo-soft/80', text: 'text-indigo', bg: 'bg-indigo-soft' },
  5: { bar: 'bg-indigo', glow: 'from-indigo-soft/80', text: 'text-indigo', bg: 'bg-indigo-soft' },
  6: { bar: 'bg-indigo', glow: 'from-indigo-soft/80', text: 'text-indigo', bg: 'bg-indigo-soft' },
  7: { bar: 'bg-halt', glow: 'from-halt-soft/90', text: 'text-halt', bg: 'bg-halt-soft' },
  8: { bar: 'bg-indigo', glow: 'from-indigo-soft/80', text: 'text-indigo', bg: 'bg-indigo-soft' },
  9: { bar: 'bg-refer', glow: 'from-refer-soft/80', text: 'text-refer', bg: 'bg-refer-soft' },
};

export function LimitCard({ part, index }: LimitCardProps) {
  const icon = PART_ICONS[part.n] ?? <Zap className="size-5" />;
  const styling = ACCENT_COLORS[part.n] ?? {
    bar: 'bg-indigo',
    glow: 'from-indigo-soft/80',
    text: 'text-indigo',
    bg: 'bg-indigo-soft',
  };

  // Border positions for a 3-column layout on lg screens
  const isBottomRow = index >= 6;
  const isLeftCol = index % 3 === 0;
  const isRightCol = index % 3 === 2;

  return (
    <div
      className={cn(
        'group/feature relative flex flex-col justify-between p-7 transition-colors duration-200',
        'border-b border-rule md:border-r',
        isLeftCol && 'lg:border-l-0',
        isRightCol && 'lg:border-r-0',
        isBottomRow && 'lg:border-b-0',
        'bg-bond hover:bg-raise/60'
      )}
    >
      {/* Directional hover gradient */}
      <div
        className={cn(
          'pointer-events-none absolute inset-0 h-full w-full opacity-0 transition-opacity duration-300 group-hover/feature:opacity-100',
          index < 3 ? 'bg-gradient-to-b to-transparent' : 'bg-gradient-to-t to-transparent',
          styling.glow
        )}
      />

      {/* Card Header: Icon & Metadata Tag */}
      <div className="relative z-10 mb-5 flex items-center justify-between">
        <div
          className={cn(
            'flex size-9 items-center justify-center rounded-lg border border-rule bg-sunk text-ink-2 transition-colors duration-200',
            `group-hover/feature:${styling.text}`,
            `group-hover/feature:${styling.bg}`
          )}
        >
          {icon}
        </div>
        <span className="font-mono text-[10.5px] uppercase tracking-wider text-ink-3">
          Part {part.n} · <span className="font-medium text-ink-2">{part.kind}</span>
        </span>
      </div>

      {/* Title with expanding Accent Bar */}
      <div className="relative z-10 mb-2">
        <div
          className={cn(
            'absolute -left-7 inset-y-0 h-5 w-1 rounded-r-full bg-rule transition-all duration-200 group-hover/feature:h-7',
            `group-hover/feature:${styling.bar}`
          )}
        />
        <h3 className="text-[15.5px] font-semibold tracking-[-0.02em] text-ink transition-transform duration-200 group-hover/feature:translate-x-1.5">
          {part.label}
        </h3>
      </div>

      {/* Description */}
      <p className="relative z-10 text-[12.5px] leading-relaxed text-ink-2">
        Checked against <span className="font-medium text-ink">{part.against}</span>.
      </p>

      {/* Card Footer: Bound value & Provenance */}
      <div className="relative z-10 mt-6 flex items-center justify-between border-t border-rule-soft pt-3 text-[12px]">
        <span className="font-mono text-[10px] uppercase tracking-wider text-ink-3">
          {part.source === 'heard' ? 'you said it' : part.source === 'inferred' ? 'we proposed' : 'unset'}
        </span>
        <span
          className={cn(
            'rounded px-2 py-0.5 font-mono text-[12px] font-semibold transition-colors',
            part.bound === 'Not set'
              ? 'italic text-ink-4'
              : `${styling.bg} ${styling.text}`
          )}
        >
          {part.bound}
        </span>
      </div>
    </div>
  );
}

export default function YourLimitsGrid() {
  return (
    <section id="limits" className="border-b border-rule bg-bond py-20">
      <div className="mx-auto max-w-[1220px] px-8 max-sm:px-[18px]">
        
        {/* Section Header */}
        <div className="mb-12 flex flex-col justify-between gap-6 md:flex-row md:items-end">
          <div className="max-w-[36rem]">
            <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3">
              Pre-Signed Policy Matrix
            </span>
            <h2 className="mt-2 text-balance text-[clamp(1.85rem,3.2vw,2.5rem)] font-semibold leading-[1.1] tracking-[-0.04em] text-ink">
              Nine kinds of limit.{' '}
              <span className="text-ink-3">A closed set, evaluated in bounded time.</span>
            </h2>
            <p className="mt-3 text-[15px] leading-relaxed text-ink-2">
              Five compare numbers against figures you set. Four test lists, categories and monotonic
              clocks. A closed set guarantees constant-time evaluation without unbounded execution loops.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-rule bg-sheet p-2 font-mono text-[11px] text-ink-3">
            <span className="inline-flex items-center gap-1.5 px-1.5 py-0.5">
              <span className="size-2 rounded-full bg-pass" /> 5 Numerical Limits
            </span>
            <span className="inline-flex items-center gap-1.5 px-1.5 py-0.5">
              <span className="size-2 rounded-full bg-indigo" /> 4 Deterministic Rules
            </span>
          </div>
        </div>

        {/* 3x3 Feature Grid with Hover Effect */}
        <div className="relative z-10 overflow-hidden rounded-2xl border border-rule bg-bond shadow-sheet">
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
            {PARTS.map((part, index) => (
              <LimitCard key={part.key} part={part} index={index} />
            ))}
          </div>
        </div>

        {/* Footnotes */}
        <div className="mt-6 flex flex-wrap items-center justify-between gap-4 font-mono text-[11px] text-ink-3">
          <span>Provenance: <b>Stated intent</b> compiled into signed policy hash</span>
          <span>Coverage: 100% evaluated on every proposed order</span>
        </div>
      </div>
    </section>
  );
}

