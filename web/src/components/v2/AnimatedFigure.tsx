import { useEffect, useState } from 'react';
import { animate, useMotionValue, useMotionValueEvent, useReducedMotion } from 'motion/react';

/**
 * A money figure that counts to its value instead of snapping to it.
 *
 * The tick is deliberately short and has no overshoot. A figure that springs
 * past its target and settles back has, for a moment, displayed an amount the
 * order never came to, which on a screen about enforcing limits is not a
 * flourish, it is a wrong number. `bounce: 0` is load-bearing here.
 *
 * The motion value drives one `setState` on a leaf element rather than a
 * template through the tree, so the per-frame cost stays where it is visible.
 */
function Ticking({
  paise,
  format,
  className,
}: {
  paise: number;
  format: (paise: number) => string;
  className?: string;
}) {
  const value = useMotionValue(paise);
  const [shown, setShown] = useState(paise);

  useMotionValueEvent(value, 'change', (v) => setShown(Math.round(v)));

  useEffect(() => {
    const controls = animate(value, paise, {
      type: 'spring',
      bounce: 0,
      visualDuration: 0.5,
    });
    return () => controls.stop();
  }, [paise, value]);

  return (
    <span className={className} style={{ fontVariantNumeric: 'tabular-nums' }}>
      {format(shown)}
    </span>
  );
}

export function AnimatedFigure({
  paise,
  format,
  className,
}: {
  paise: number;
  format: (paise: number) => string;
  className?: string;
}) {
  const reduced = useReducedMotion();

  // Rendered as a separate component so the reduced-motion path holds no motion
  // value and runs no effect at all, rather than setting state to undo itself.
  if (reduced) {
    return (
      <span className={className} style={{ fontVariantNumeric: 'tabular-nums' }}>
        {format(paise)}
      </span>
    );
  }
  return <Ticking paise={paise} format={format} className={className} />;
}
