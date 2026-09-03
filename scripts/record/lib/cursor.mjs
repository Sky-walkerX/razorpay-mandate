/**
 * A cursor you can actually see.
 *
 * Playwright drives the mouse over CDP. The page receives real mousemove and
 * click events -- hover states fire correctly -- but the macOS pointer never
 * moves and nothing is drawn. A screen recording of that shows a site reacting
 * to an invisible hand, which reads as a bug rather than a demo.
 *
 * So we draw one. Two decisions in here are load-bearing:
 *
 * 1. It positions itself from the page's own mousemove events rather than from
 *    explicit calls by the driver. One source of truth, no round trip per
 *    animation step, and it cannot drift out of sync with where Playwright
 *    thinks the pointer is.
 * 2. It is appended to document.body, outside React's #root, so client-side
 *    route changes cannot unmount it. addInitScript re-runs on hard
 *    navigations, so it survives those too.
 */

export const CURSOR_INIT = () => {
  const ID = '__mandate_cursor__';
  if (window.__mandateCursorInstalled) return;
  window.__mandateCursorInstalled = true;

  const install = () => {
    if (!document.body || document.getElementById(ID)) return;

    const style = document.createElement('style');
    style.textContent = `
      #${ID} {
        position: fixed; left: 0; top: 0; width: 22px; height: 22px;
        pointer-events: none; z-index: 2147483647;
        will-change: transform; transform: translate3d(-100px,-100px,0);
        transition: none;
      }
      #${ID} svg { display:block; filter: drop-shadow(0 1px 2px rgba(0,0,0,.45)); }
      #${ID}.is-down svg { transform: scale(.86); }
      #${ID} svg { transition: transform 90ms cubic-bezier(.2,0,.2,1); }
      .__mandate_ripple__ {
        position: fixed; pointer-events: none; z-index: 2147483646;
        width: 14px; height: 14px; margin: -7px 0 0 -7px; border-radius: 50%;
        border: 2px solid rgba(59,130,246,.9); background: rgba(59,130,246,.18);
        animation: __mandate_ripple__ 520ms cubic-bezier(.16,1,.3,1) forwards;
      }
      @keyframes __mandate_ripple__ {
        from { transform: scale(.3); opacity: 1; }
        to   { transform: scale(3.6); opacity: 0; }
      }
    `;
    document.head.appendChild(style);

    const el = document.createElement('div');
    el.id = ID;
    // The standard macOS arrow, drawn rather than screenshotted so it stays
    // crisp at deviceScaleFactor 2.
    el.innerHTML = `
      <svg width="22" height="22" viewBox="0 0 22 22" fill="none">
        <path d="M4.5 2.2 L4.5 17.4 L8.3 13.9 L10.8 19.4 L13.4 18.2 L10.9 12.9 L16.1 12.6 Z"
              fill="#ffffff" stroke="#111827" stroke-width="1.25" stroke-linejoin="round"/>
      </svg>`;
    document.body.appendChild(el);

    let x = -100, y = -100;
    const paint = () => { el.style.transform = `translate3d(${x}px, ${y}px, 0)`; };

    document.addEventListener('mousemove', (e) => {
      x = e.clientX; y = e.clientY; paint();
    }, { capture: true, passive: true });

    document.addEventListener('mousedown', (e) => {
      el.classList.add('is-down');
      const r = document.createElement('div');
      r.className = '__mandate_ripple__';
      r.style.left = e.clientX + 'px';
      r.style.top = e.clientY + 'px';
      document.body.appendChild(r);
      setTimeout(() => r.remove(), 560);
    }, { capture: true, passive: true });

    document.addEventListener('mouseup', () => {
      el.classList.remove('is-down');
    }, { capture: true, passive: true });
  };

  if (document.body) install();
  else document.addEventListener('DOMContentLoaded', install, { once: true });
  // The SPA swaps its tree on route changes; body itself survives, but a hard
  // navigation lands here again with no body yet.
  new MutationObserver(install).observe(document.documentElement, {
    childList: true, subtree: false,
  });
};
