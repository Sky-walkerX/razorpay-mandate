import { cn } from '@/lib/utils';

export type Tone = 'pass' | 'halt' | 'refer' | 'unset';

const TONE_CLASS: Record<Tone, string> = {
  pass: 'bg-pass-soft text-pass',
  halt: 'bg-halt-soft text-halt',
  refer: 'bg-refer-soft text-refer',
  unset: 'bg-sheet text-ink-3',
};

const MARKER_CLASS: Record<Tone, string> = {
  pass: 'bg-pass',
  halt: 'rotate-45 bg-halt',
  refer: 'rounded-full bg-refer',
  unset: 'rounded-full bg-ink-4',
};

/**
 * The one badge shape used everywhere a verdict or a constraint's status is
 * named: a small marker whose shape carries the meaning, plus the word beside
 * it. Hue is never the only signal — see `styles/theme.css`.
 */
export function StatusBadge({ tone, label }: { tone: Tone; label: string }) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-[5px] whitespace-nowrap rounded-full px-[7px] py-[3px]',
        'font-mono text-[9.5px] uppercase tracking-[0.06em]',
        TONE_CLASS[tone],
      )}
    >
      <span className={cn('size-[6px] shrink-0', MARKER_CLASS[tone])} />
      {label}
    </span>
  );
}
