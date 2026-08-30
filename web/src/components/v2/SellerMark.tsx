import { cn } from '@/lib/utils';

/**
 * Seller identity.
 *
 * These are drawn approximations in each merchant's brand hue, not official
 * assets — swap in real marks before this is public. Hue names a merchant and
 * never a state: the three meaning inks stay green, ochre and carmine, and
 * every verdict still carries a shape and a word.
 *
 * `Blinkit Express` is deliberately close to `Blinkit` and deliberately wrong.
 * That is the lookalike attack, and having it visible at a glance is the point.
 */
type Glyph = 'bolt' | 'z' | 'bag';

interface Brand {
  bg: string;
  fg: string;
  glyph: Glyph;
  /** True when the name resembles an allowed seller but the account does not. */
  lookalike?: boolean;
}

const BRANDS: Record<string, Brand> = {
  Blinkit: { bg: '#F8CD46', fg: '#101010', glyph: 'bolt' },
  'Blinkit Express': { bg: '#F3D479', fg: '#57470F', glyph: 'bolt', lookalike: true },
  Zepto: { bg: '#7C3AED', fg: '#FFFFFF', glyph: 'z' },
  Instamart: { bg: '#FC8019', fg: '#FFFFFF', glyph: 'bag' },
};

function GlyphPath({ glyph, fg }: { glyph: Glyph; fg: string }) {
  if (glyph === 'bolt') return <path d="M11.2 3.6 5.6 11h3.1l-.9 5.4 5.6-7.4h-3.1z" fill={fg} />;
  if (glyph === 'z')
    return (
      <path
        d="M6.2 5.6h7.6l-5 8.8h5"
        stroke={fg}
        strokeWidth="1.7"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    );
  return (
    <path
      d="M5.6 7.4h8.8l-.9 7.2a1 1 0 0 1-1 .9H7.5a1 1 0 0 1-1-.9zM7.8 7.4V6.2a2.2 2.2 0 0 1 4.4 0v1.2"
      stroke={fg}
      strokeWidth="1.5"
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  );
}

export function SellerMark({ name, className }: { name: string; className?: string }) {
  const brand = BRANDS[name];
  if (!brand) return null;
  return (
    <svg
      viewBox="0 0 20 20"
      role="img"
      aria-label={name}
      className={cn('size-5 shrink-0 rounded-[6px]', className)}
    >
      <rect width="20" height="20" rx="5.5" fill={brand.bg} />
      <GlyphPath glyph={brand.glyph} fg={brand.fg} />
    </svg>
  );
}

/** The seller chip in the order header, flagged when the account is not on the list. */
export function SellerChip({ name }: { name: string }) {
  const lookalike = BRANDS[name]?.lookalike ?? false;
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 rounded-full border py-1 pr-3 pl-1 transition-colors',
        lookalike ? 'border-halt-line bg-halt-soft' : 'border-rule bg-raise',
      )}
    >
      <SellerMark name={name} />
      <span
        className={cn(
          'text-[12.5px] font-medium tracking-[-0.015em]',
          lookalike ? 'text-halt' : 'text-ink',
        )}
      >
        {name}
      </span>
    </span>
  );
}
