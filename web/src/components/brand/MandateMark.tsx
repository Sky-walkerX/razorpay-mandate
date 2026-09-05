/**
 * The Mandate mark: a gate.
 *
 * A navy post with a slot cut through it, and a blue beam entering the slot.
 * That is the product in three shapes, the order that satisfies the mandate
 * goes through the aperture, and anything arriving off-axis meets solid navy.
 * The faded diagonal is that blocked ray, and it is the first thing to go at
 * small sizes, which is why `blocked` defaults to off below the display sizes.
 *
 * The post sits right of centre rather than on it. Centred, the two blades and
 * the beam crossed at the same point and the whole mark read as a plus sign at
 * nav size, which is what the first cut of this shipped as.
 *
 * The 40x40 viewBox is shared with the favicon so the two can never drift.
 * Navy does the stopping and blue does the moving, everywhere, always: if a
 * future variant paints a blade blue it is saying the wrong thing.
 */
export function MandateMark({
  size = 19,
  blocked = false,
  tone = 'brand',
  className,
}: {
  size?: number;
  /** Draw the blocked ray. Legible from roughly 28px up. */
  blocked?: boolean;
  /** `brand` on light ground; `inverse` for a navy tile or a dark surface. */
  tone?: 'brand' | 'inverse';
  className?: string;
}) {
  const blade = tone === 'inverse' ? '#7EA0FF' : '#012652';
  const beam = tone === 'inverse' ? '#FFFFFF' : '#2F5EFF';

  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 40 40"
      fill="none"
      aria-hidden
      className={className}
    >
      <rect x="25.6" y="3.6" width="6.2" height="13" rx="2.4" fill={blade} />
      <rect x="25.6" y="23.4" width="6.2" height="13" rx="2.4" fill={blade} />
      <path d="M4 20h25.4" stroke={beam} strokeWidth="3.6" strokeLinecap="round" />
      {blocked && (
        <path
          d="M6.4 32 15 23.2"
          stroke={beam}
          strokeWidth="2.8"
          strokeLinecap="round"
          opacity="0.32"
        />
      )}
    </svg>
  );
}
