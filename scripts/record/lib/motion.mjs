/**
 * The helpers that make a scripted walkthrough read as a human one.
 *
 * What makes automation look robotic is not speed, it is the absence of
 * anticipation: pointers that teleport, scrolls that land in one frame, clicks
 * that fire the instant the cursor arrives. Each helper here fixes one of
 * those.
 */

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Named waits, so the shot list reads as a shot list. */
export const hold = sleep;

const easeInOutCubic = (t) =>
  t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;

// Playwright does not expose the pointer position, so we own it.
const POS = new WeakMap();
export const posOf = (page) => POS.get(page) ?? { x: 720, y: 480 };

/**
 * Move the pointer along an eased, slightly curved path.
 *
 * The curve matters more than it sounds. A perfectly straight slide between two
 * points is the single clearest tell that nobody is holding the mouse; a real
 * hand overshoots the chord. The offset is proportional to travel distance and
 * capped, so short hops stay straight and long ones bow.
 */
export async function moveTo(page, x, y, ms = 480) {
  const from = posOf(page);
  const dx = x - from.x, dy = y - from.y;
  const dist = Math.hypot(dx, dy);
  if (dist < 1) { POS.set(page, { x, y }); return; }

  // Perpendicular bow at the midpoint, sign chosen so the path arcs the same
  // way a right-handed drag tends to.
  const bow = Math.min(dist * 0.08, 46) * (dy >= 0 ? 1 : -1);
  const mx = (from.x + x) / 2 - (dy / dist) * bow;
  const my = (from.y + y) / 2 + (dx / dist) * bow;

  const steps = Math.max(12, Math.min(48, Math.round(ms / 13)));
  const t0 = Date.now();
  for (let i = 1; i <= steps; i++) {
    const t = easeInOutCubic(i / steps);
    const u = 1 - t;
    // Quadratic bezier through the bowed midpoint.
    const px = u * u * from.x + 2 * u * t * mx + t * t * x;
    const py = u * u * from.y + 2 * u * t * my + t * t * y;
    await page.mouse.move(px, py);
    const due = t0 + (ms * i) / steps;
    const lag = due - Date.now();
    if (lag > 0) await sleep(lag);
  }
  POS.set(page, { x, y });
}

async function centreOf(locator) {
  await locator.scrollIntoViewIfNeeded().catch(() => {});
  const box = await locator.boundingBox();
  if (!box) throw new Error('element has no box: ' + locator);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/**
 * Travel to an element, settle, then click.
 *
 * The settle is the whole trick. Clicking the instant the pointer arrives reads
 * as a teleport even when the travel was smooth; a beat of stillness first
 * reads as a decision. It also gives hover transitions (200-300ms on this site)
 * time to land before the click changes the view.
 */
export async function clickAt(page, locator, { travel = 480, settle = 190 } = {}) {
  const { x, y } = await centreOf(locator);
  await moveTo(page, x, y, travel);
  await sleep(settle);
  await page.mouse.down();
  await sleep(70);
  await page.mouse.up();
}

/** Park the pointer on something and let its hover state play. */
export async function hoverAt(page, locator, { travel = 520, dwell = 900 } = {}) {
  const { x, y } = await centreOf(locator);
  await moveTo(page, x, y, travel);
  await sleep(dwell);
}

/**
 * Scroll with a requestAnimationFrame loop inside the page.
 *
 * Deliberately not page.mouse.wheel in a loop: each wheel event is a discrete
 * jump the compositor renders as a step, and on a 60fps capture the staircase
 * is obvious. A rAF loop moves once per frame, which is what a trackpad does,
 * and crosses whileInView thresholds smoothly on the way.
 */
export async function smoothScrollTo(page, targetY, ms = 1600) {
  await page.evaluate(
    ([to, dur]) =>
      new Promise((resolve) => {
        const from = window.scrollY;
        const max = document.documentElement.scrollHeight - window.innerHeight;
        const dest = Math.max(0, Math.min(to, max));
        const delta = dest - from;
        if (Math.abs(delta) < 2 || dur <= 0) { window.scrollTo(0, dest); return resolve(); }
        const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
        const t0 = performance.now();
        const step = (now) => {
          const t = Math.min(1, (now - t0) / dur);
          window.scrollTo(0, from + delta * ease(t));
          if (t < 1) requestAnimationFrame(step);
          else resolve();
        };
        requestAnimationFrame(step);
      }),
    [targetY, ms],
  );
}

/** Scroll so a selector sits `offset` px below the top of the viewport. */
export async function scrollToSelector(page, selector, { ms = 1600, offset = 90 } = {}) {
  const y = await page.evaluate(
    ([sel, off]) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      return window.scrollY + el.getBoundingClientRect().top - off;
    },
    [selector, offset],
  );
  if (y === null) throw new Error(`scrollToSelector: no match for ${selector}`);
  await smoothScrollTo(page, y, ms);
}

/** Scroll by a fraction of the viewport height. Good for a slow continuous read. */
export async function scrollBy(page, viewportFraction, ms = 1600) {
  const y = await page.evaluate(
    (f) => window.scrollY + window.innerHeight * f,
    viewportFraction,
  );
  await smoothScrollTo(page, y, ms);
}

/** Type with uneven keystrokes; a constant interval sounds like a machine. */
export async function typeHuman(page, locator, text, { wpm = 320 } = {}) {
  await locator.click();
  const base = 60000 / (wpm * 5);
  for (const ch of text) {
    await locator.press(ch === ' ' ? 'Space' : ch, { delay: 0 }).catch(async () => {
      await page.keyboard.insertText(ch);
    });
    await sleep(base * (0.55 + Math.random() * 0.9));
  }
}
