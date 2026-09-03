/**
 * The shot list. One entry per beat, in the order they are recorded.
 *
 * Durations are set against measured animation periods, not taste:
 *   hero beams          4.2s loop, infinite   -> hold ~9s for two cycles
 *   lattice beam+gates  3.6s loop, infinite   -> hold ~8s for two cycles
 *   GapAndParts rows    0.32s x 12, ~0.7s cascade
 *   clause waterfall    45ms x 10 = 450ms, fires ~500ms after a verdict lands
 *   RunStrip            0.42s + 12ms x 53 = ~1.06s, on MOUNT not scroll
 *
 * Two ordering constraints are not preferences:
 *   - Shot 8 must precede shot 10. Only the ENFORCE arm writes to the
 *     storefront, so /store shows its empty state until the agent has run.
 *   - Preset #9, "Use access you cut off", is never run. It revokes the session
 *     token and everything after it fails.
 */
import { clickAt, hold, hoverAt, moveTo, scrollToSelector, smoothScrollTo } from './lib/motion.mjs';

const TRY = 'https://mandate.namankhandelwal.dev';

/** Click a /try preset row by its title. */
const preset = (page, title) =>
  page.locator('button').filter({ hasText: title }).first();

export const shots = [
  {
    id: 'hero',
    label: 'Boot loader, then the problem',
    budget: 24,
    async run({ page, base }) {
      await page.goto(base, { waitUntil: 'domcontentloaded' });
      // BootLoader: mark assembles, bar fills, plate lifts at 1900ms + 0.4s exit.
      // It plays once per tab, gated on sessionStorage, so this only works
      // because every take gets a fresh context.
      await hold(3200);
      await moveTo(page, 700, 430, 900);
      // Two full 4.2s beam cycles: blue beam to the agent, red beam to the card.
      await hold(9000);
      // A slow drift down so the frame is never dead, and so the four-node rail
      // and its "charged, uncontained" endpoint both sit centre screen.
      await smoothScrollTo(page, 260, 3800);
      await hold(4200);
    },
  },

  {
    id: 'gap',
    label: 'The rail holds three things. You meant twelve.',
    budget: 26,
    async run({ page }) {
      // Enter the section so the twelve motion.li rows cross their -60px
      // viewport margin and cascade rather than being already-visible on arrival.
      await scrollToSelector(page, '#gap', { ms: 2600, offset: 110 });
      await hold(3400);
      await scrollToSelector(page, '#gap', { ms: 2200, offset: -260 });
      // The twelve conditions, each tagged with where it can live.
      await hold(5200);
      await moveTo(page, 980, 520, 1100);
      await hold(3600);
      await smoothScrollTo(page, await yOf(page, '#gap', -640), 2600);
      await hold(4200);
    },
  },

  {
    id: 'limits',
    label: 'The ten limits the gateway implements',
    budget: 16,
    async run({ page }) {
      await scrollToSelector(page, '#limits', { ms: 2400, offset: 120 });
      await hold(2600);
      // No scroll animation here, but each card has a directional gradient
      // wash, an icon tile that turns indigo and a title that slides 1.5px.
      // A slow pass across two of them is the whole reason to stop.
      const cards = page.locator('#limits [class*="group/feature"]');
      const n = await cards.count();
      if (n >= 3) {
        await hoverAt(page, cards.nth(1), { travel: 700, dwell: 2400 });
        await hoverAt(page, cards.nth(4 % n), { travel: 900, dwell: 2600 });
      } else {
        await hold(5000);
      }
      await hold(2200);
    },
  },

  {
    id: 'how',
    label: 'The order evaluation lattice',
    budget: 20,
    async run({ page }) {
      await scrollToSelector(page, '#how', { ms: 2800, offset: 90 });
      await hold(2400);
      // Park on the lattice panel: a vertical beam travels the conduit on a
      // 3.6s loop, synchronised with the DENY / UNKNOWN / ALLOW gate cards
      // lighting in sequence as it passes. Two full cycles.
      await smoothScrollTo(page, await yOf(page, '#how', -420), 2600);
      await moveTo(page, 480, 520, 1000);
      await hold(8600);
      await moveTo(page, 900, 470, 1400);
      await hold(2200);
    },
  },

  {
    id: 'try-normal',
    label: 'A normal order goes through',
    budget: 18,
    async run({ page }) {
      // A real click on the nav CTA, so this is a client-side transition
      // rather than a reload. The in-page anchors are deliberately never
      // clicked: nothing sets scroll-behavior: smooth, so they jump.
      await smoothScrollTo(page, 0, 1400);
      await clickAt(page, page.getByRole('link', { name: 'Try it live →' }).first());
      await page.waitForURL(/\/try/, { timeout: 15000 });
      await hold(2600);
      // Establish the allowed case first, so the refusals that follow mean
      // something. Clicking a preset runs it immediately.
      await clickAt(page, preset(page, 'A normal order'), { travel: 700 });
      // One deterministic POST, no model. Then the 10-row clause waterfall at
      // 45ms a row. Do not cut for at least a second after this.
      await hold(6800);
    },
  },

  {
    id: 'try-injection',
    label: 'Hidden instructions in a review, and what Reserve Pay would have done',
    budget: 30,
    async run({ page }) {
      await clickAt(page, preset(page, 'Hidden instructions in a review'), { travel: 620 });
      await hold(3200);
      // The refusal, the hostile substring highlighted in the payload, and the
      // waterfall stopping at the clause that refused it.
      await moveTo(page, 980, 380, 1200);
      await hold(4200);
      // The Reserve Pay strip: the same basket answered as UPI Reserve Pay
      // would answer it. This is the frame the whole pitch is built on.
      const strip = page.getByText(/Reserve Pay/i).first();
      if (await strip.isVisible().catch(() => false)) {
        await hoverAt(page, strip, { travel: 900, dwell: 5200 });
      } else {
        await hold(5200);
      }
      await smoothScrollTo(page, 320, 2200);
      await hold(4200);
      await smoothScrollTo(page, 0, 1800);
      await hold(2400);
    },
  },

  {
    id: 'try-salami',
    label: 'Four small orders, and the ledger filling',
    budget: 22,
    async run({ page }) {
      await clickAt(page, preset(page, 'Split it into many small orders'), { travel: 700 });
      // Four sequential POSTs. The ledger gains four rows off one click, which
      // is the best single shot of the audit chain filling.
      await hold(5200);
      await smoothScrollTo(page, 420, 2400);
      await hold(5600);
      await smoothScrollTo(page, 760, 2200);
      await hold(4200);
      await smoothScrollTo(page, 0, 1600);
    },
  },

  {
    id: 'agent',
    label: 'Same AI, same shop, one difference',
    budget: 38,
    async run({ page, mark, skipModel, log }) {
      await clickAt(page, page.getByRole('button', { name: /Watch an AI shop/ }).first(), { travel: 800 });
      await hold(2600);
      if (skipModel) { log('    (skip-model: not pressing Run both sides)'); await hold(4000); return; }

      await clickAt(page, page.getByRole('button', { name: 'Run both sides' }).first(), { travel: 700 });
      mark('agent_start');
      // The enforced arm runs first and lands fast, because it gets refused and
      // stops. This is the good footage: refusals arriving one at a time.
      await hold(11000);

      // Everything from here to completion is the unprotected arm shopping to
      // its turn limit. Real, necessary, and dull to watch -- post ramps it.
      mark('ramp_start');
      const done = page.getByRole('button', { name: 'Run both sides' });
      await done.waitFor({ state: 'visible', timeout: 120000 }).catch(() => {});
      mark('ramp_end');

      // Land at full speed on the side-by-side: a large rupee figure on the
      // left, a small one on the right, one instruction between them.
      await hold(2500);
      await smoothScrollTo(page, 260, 1800);
      await hold(4500);
      await smoothScrollTo(page, 0, 1400);
    },
  },

  {
    id: 'sandbox',
    label: 'Write your own rules, and be refused by your own number',
    budget: 34,
    async run({ page, mark, skipModel, log }) {
      await clickAt(page, page.getByRole('button', { name: /Write your own rules/ }).first(), { travel: 800 });
      await hold(3000);
      if (skipModel) { log('    (skip-model: not compiling)'); await hold(4000); return; }

      await clickAt(page, page.getByRole('button', { name: 'Turn this into real limits' }).first(), { travel: 700 });
      // Everything until the constraints appear is a progress line. Real, and
      // worth showing that it is real, but not worth 12-60 seconds of a
      // five-minute video.
      mark('sbx_ramp_start');
      // A real Vertex compile: two readings at temperature 0, measured warm at
      // 9.7-12.5s against a 30s ceiling. It can legitimately decline, which is
      // the determinism check working, but a decline produces no constraint
      // list for the probe below -- so retry once, then move on.
      const propose = page.getByRole('button', { name: 'Propose' });
      let ready = await propose.waitFor({ state: 'visible', timeout: 34000 }).then(() => true).catch(() => false);
      if (!ready) {
        log('    compile did not produce constraints; one retry');
        await clickAt(page, page.getByRole('button', { name: /Turn this into real limits|Reading it…/ }).first());
        ready = await propose.waitFor({ state: 'visible', timeout: 34000 }).then(() => true).catch(() => false);
      }
      mark('sbx_ramp_end');
      if (!ready) { log('    compile unavailable, skipping the probe'); await hold(3000); return; }

      await hold(4200);
      // Pick something over the visitor's own per-order cap, then propose it.
      const item = page.getByLabel('Item');
      await clickAt(page, item, { travel: 700 });
      await item.selectOption({ index: await pickDearest(item) }).catch(() => {});
      await hold(1600);
      await clickAt(page, propose, { travel: 600 });
      // Deterministic, no model, under 50ms. The refusal quotes the number the
      // viewer typed, not the demo's.
      await hold(6500);
      await smoothScrollTo(page, 300, 1800);
      await hold(4000);
    },
  },

  {
    id: 'store',
    label: 'What landed, and what did not',
    budget: 20,
    async run({ page, base }) {
      // Populated by the enforce arm of shot 8.
      await page.goto(`${base}/store`, { waitUntil: 'domcontentloaded' });
      await hold(3400);
      await smoothScrollTo(page, 340, 2600);
      await hold(4200);
      // A refused card swaps its delivery footer for the clause that refused it
      // and strikes through the amount. That substitution is the page's whole
      // argument, so hold on one.
      const struck = page.locator('[class*="line-through"]').first();
      if (await struck.isVisible().catch(() => false)) {
        await hoverAt(page, struck, { travel: 900, dwell: 4200 });
      } else {
        await hold(4200);
      }
      await smoothScrollTo(page, 700, 2200);
      await hold(3400);
    },
  },

  {
    id: 'dashboard',
    label: 'Three orders went through. Fifty did not.',
    budget: 22,
    async run({ page, base }) {
      await page.goto(`${base}/dashboard`, { waitUntil: 'domcontentloaded' });
      // RunStrip is mount-triggered, not scroll-triggered: 53 columns rising on
      // a 12ms stagger, finished ~1.06s after arrival. Hold immediately.
      await hold(5200);
      await smoothScrollTo(page, 300, 2400);
      await hold(4200);
      await smoothScrollTo(page, 700, 2400);
      await hold(4000);
      await smoothScrollTo(page, 1150, 2200);
      await hold(3000);
    },
  },

  {
    id: 'rails',
    label: 'What the rails can and cannot carry',
    budget: 30,
    async run({ page, base }) {
      await page.goto(`${base}/rails`, { waitUntil: 'domcontentloaded' });
      await hold(2800);
      // The two tally cards fill cell by cell: the subtraction made visible.
      await scrollToSelector(page, '#rails', { ms: 2600, offset: 110 });
      await hold(4600);
      // The clause table, one row at a time, each with a fixed-width chip
      // reading STRUCTURAL / ON THE RAIL / PROSE ONLY / NOWHERE.
      await smoothScrollTo(page, await yOf(page, '#rails', -420), 2600);
      await hold(4800);
      await smoothScrollTo(page, await yOf(page, '#rails', -900), 2800);
      await hold(5200);
      // afa.required: RBI's own requirement, and it has nowhere to sit on
      // either rail. The gateway holds it because the rails cannot.
      const nowhere = page.getByText('NOWHERE').first();
      if (await nowhere.isVisible().catch(() => false)) {
        await hoverAt(page, nowhere, { travel: 900, dwell: 3600 });
      } else {
        await hold(3600);
      }
      await hold(2400);
    },
  },
];

/** Absolute document Y of a selector, plus an offset. */
async function yOf(page, selector, delta) {
  return page.evaluate(
    ([sel, d]) => {
      const el = document.querySelector(sel);
      const top = el ? window.scrollY + el.getBoundingClientRect().top : window.scrollY;
      return Math.max(0, top - d * -1);
    },
    [selector, delta],
  ).then((v) => v + 0);
}

/** Index of the priciest option in the sandbox item select. */
async function pickDearest(select) {
  const opts = await select.locator('option').allTextContents();
  let best = 0, bestVal = -1;
  opts.forEach((t, i) => {
    const m = t.match(/₹\s*([\d,]+(?:\.\d+)?)/);
    const v = m ? parseFloat(m[1].replace(/,/g, '')) : -1;
    if (v > bestVal) { bestVal = v; best = i; }
  });
  return best;
}

export { TRY };
