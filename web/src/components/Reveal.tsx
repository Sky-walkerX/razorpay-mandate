import { useEffect, useRef, type ReactNode } from 'react';

/** Set once, at module load, before anything paints. */
const CAN_OBSERVE =
  typeof window !== 'undefined' &&
  'IntersectionObserver' in window &&
  !window.matchMedia('(prefers-reduced-motion: reduce)').matches;

if (CAN_OBSERVE) document.documentElement.classList.add('io');

/**
 * Scroll-in wrapper. The hidden state lives behind `html.io`, which is only set
 * when an observer will actually arrive to remove it — so if this never runs,
 * the content is simply there. A safety timer covers the case where the
 * observer exists but never fires (a short page, a stubbed environment).
 */
export default function Reveal({
  children,
  as: Tag = 'div',
  className = '',
}: {
  children: ReactNode;
  as?: 'div' | 'section' | 'article';
  className?: string;
}) {
  const ref = useRef<HTMLElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (!CAN_OBSERVE) {
      el.classList.add('in');
      return;
    }
    const show = () => el.classList.add('in');
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          show();
          io.disconnect();
        }
      },
      { rootMargin: '0px 0px -8% 0px', threshold: 0.06 },
    );
    io.observe(el);
    const safety = window.setTimeout(show, 1800);
    return () => {
      io.disconnect();
      window.clearTimeout(safety);
    };
  }, []);

  return (
    <Tag ref={ref as never} className={`reveal ${className}`.trim()}>
      {children}
    </Tag>
  );
}
