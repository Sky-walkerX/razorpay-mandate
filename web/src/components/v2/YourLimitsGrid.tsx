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

/**
 * The ink on each part's BOUND chip. This is the only place per-part colour
 * survives, because it is the only place colour means something: `pass` for a
 * figure you set, `indigo` for a list or a clock, `halt` for a denial, `refer`
 * for a part that is implemented but carries no attack evidence.
 *
 * Hover is deliberately NOT in here. Hover is chrome — it says "this card, now"
 * and nothing about the constraint — so it is Razorpay blue on every card,
 * per `theme.css`: indigo is chrome and never carries meaning.
 *
 * This used to be a four-key record read through `group-hover/feature:${...}`
 * template strings. Tailwind generates utilities by scanning source text for
 * complete class names, and `group-hover/feature:text-pass` appears nowhere in
 * this file, so every one of those hover rules silently resolved to nothing:
 * the accent bars stayed `bg-rule` grey and the icon tiles never changed. The
 * static classes below are the fix as much as the colour is.
 */
const BOUND_INK: Record<number, { text: string; bg: string }> = {
  1: { text: 'text-pass', bg: 'bg-pass-soft' },
  2: { text: 'text-pass', bg: 'bg-pass-soft' },
  3: { text: 'text-pass', bg: 'bg-pass-soft' },
  4: { text: 'text-indigo', bg: 'bg-indigo-soft' },
  5: { text: 'text-indigo', bg: 'bg-indigo-soft' },
  6: { text: 'text-indigo', bg: 'bg-indigo-soft' },
  7: { text: 'text-halt', bg: 'bg-halt-soft' },
  8: { text: 'text-indigo', bg: 'bg-indigo-soft' },
  9: { text: 'text-refer', bg: 'bg-refer-soft' },
};

export function LimitCard({ part, index }: LimitCardProps) {
  const icon = PART_ICONS[part.n] ?? <Zap className="size-5" />;
  const ink = BOUND_INK[part.n] ?? { text: 'text-indigo', bg: 'bg-indigo-soft' };

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
      {/* Directional hover wash. Enters from the outside edge of the grid. */}
      <div
        className={cn(
          'pointer-events-none absolute inset-0 h-full w-full from-indigo-soft/70 opacity-0 transition-opacity duration-300 group-hover/feature:opacity-100',
          index < 3 ? 'bg-gradient-to-b to-transparent' : 'bg-gradient-to-t to-transparent',
        )}
      />

      {/* Card Header: Icon & Metadata Tag */}
      <div className="relative z-10 mb-5 flex items-center justify-between">
        <div
          className={cn(
            'flex size-9 items-center justify-center rounded-lg border border-rule bg-sunk text-ink-2 transition-colors duration-200',
            'group-hover/feature:border-indigo/30 group-hover/feature:bg-indigo-soft group-hover/feature:text-indigo',
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
            'absolute -left-7 inset-y-0 h-5 w-1 rounded-r-full bg-rule transition-all duration-200',
            'group-hover/feature:h-7 group-hover/feature:bg-indigo',
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
          {part.source === 'heard'
            ? 'you said it'
            : part.source === 'inferred'
              ? 'we proposed'
              : part.source === 'regulatory'
                ? 'required by law'
                : 'unset'}
        </span>
        <span
          className={cn(
            'rounded px-2 py-0.5 font-mono text-[12px] font-semibold transition-colors',
            part.bound === 'Not set'
              ? 'italic text-ink-4'
              : cn(ink.bg, ink.text)
          )}
        >
          {part.bound}
        </span>
      </div>
    </div>
  );
}

/**
 * The nine parts, as one joined surface rather than nine cards.
 *
 * The shared hairlines are the point: a closed set should look like a closed
 * set, so the cells butt against each other inside a single rounded border and
 * only the outer edge is drawn. Lives inside section 02 now, directly under the
 * twelve conditions it resolves — it used to be its own section at the foot of
 * the page, several screens away from the argument that motivates it.
 */
export function PartsGrid() {
  return (
    <div className="relative z-10 overflow-hidden rounded-2xl border border-rule bg-bond shadow-sheet">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3">
        {PARTS.map((part, index) => (
          <LimitCard key={part.key} part={part} index={index} />
        ))}
      </div>
    </div>
  );
}
