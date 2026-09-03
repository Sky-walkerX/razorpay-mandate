import { MandateMark } from './MandateMark';
import { cn } from '@/lib/utils';

/**
 * Mark, wordmark, hairline, attribution — in that order, always.
 *
 * "by Razorpay" sits behind a rule and one weight down because it is a credit,
 * not a claim: this is a Razorpay AI Buildathon entry, and the attribution
 * should read the way a byline does rather than the way a first-party product
 * name would. Nothing here renders the Razorpay logotype.
 *
 * This replaced three hand-copied SVGs in `Landing`, `JudgeConsole` and
 * the dashboard sidebar that had already drifted apart in size and colour.
 */
export function MandateLockup({
  size = 'md',
  attribution = true,
  className,
}: {
  size?: 'sm' | 'md';
  /** Off in tight chrome — a sidebar rail, a mobile bar. */
  attribution?: boolean;
  className?: string;
}) {
  const sm = size === 'sm';

  return (
    <span className={cn('flex items-center gap-[9px]', className)}>
      <MandateMark size={sm ? 17 : 19} />
      <span
        className={cn(
          'font-semibold tracking-[-0.04em] text-navy',
          sm ? 'text-[14.5px]' : 'text-[16.5px]',
        )}
      >
        Mandate
      </span>
      {/* The credit is the first thing to go when the bar is tight — which is
          what the prop above already says, except a phone cannot pass a prop.
          At 390 the home bar was 2px wider than the viewport with this in it. */}
      {attribution && (
        <>
          <span aria-hidden className="h-[13px] w-px bg-rule max-sm:hidden" />
          <span
            className={cn(
              'text-ink-3 max-sm:hidden',
              sm ? 'text-[11.5px]' : 'text-[12.5px]',
            )}
          >
            by Razorpay
          </span>
        </>
      )}
    </span>
  );
}
