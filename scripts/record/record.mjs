#!/usr/bin/env node
/**
 * Drive the Mandate site through the shot list and record it.
 *
 *   node record.mjs --preflight-only    just check the deployment
 *   node record.mjs --dry --skip-model  choreography only, no capture, no Vertex
 *   node record.mjs --dry               choreography with the real model calls
 *   node record.mjs                     the take
 *
 * Writes out/take-<ts>/{raw.mov, shot-times.json}. Every cut point post needs is
 * a mark in that manifest, measured from the first recorded frame, so nothing
 * downstream has to be eyeballed on a timeline.
 */
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { CURSOR_INIT } from './lib/cursor.mjs';
import { preflight } from './lib/preflight.mjs';
import { keepFrontmost, parkPointer } from './lib/pointer.mjs';
import { NullRecorder, Recorder, screenDeviceIndex } from './lib/recorder.mjs';
import { shots } from './shots.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const has = (f) => argv.includes(f);
const val = (f, d) => {
  const i = argv.indexOf(f);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : d;
};

const BASE = val('--base', 'https://mandate.namankhandelwal.dev').replace(/\/$/, '');
const DRY = has('--dry');
const SKIP_MODEL = has('--skip-model');
const ONLY = val('--only', null);

// The logical desktop here is 1470x956 points, so a 1440-wide window does not
// fit. 1280 is chosen deliberately: comfortably above the 1024 breakpoint that
// gates the hero beam rail, the FailureModes axis, the /try two-column split
// and LiveAgentPanel's side-by-side arms -- all of which vanish below it -- and
// well under the ~1600 where /try goes thin for want of a max-width.
const WIN = { w: 1280, h: 887, x: 95, y: 32 };

const log = (s) => console.log(s);

async function main() {
  if (has('--preflight-only')) {
    const r = await preflight(BASE);
    process.exit(r.pass ? 0 : 1);
  }

  if (!DRY && !has('--skip-preflight')) {
    const r = await preflight(BASE);
    if (!r.pass) {
      console.error('Refusing to record against a deployment that failed preflight.');
      process.exit(1);
    }
  }

  const stamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
  const outDir = join(HERE, 'out', `take-${stamp}`);
  mkdirSync(outDir, { recursive: true });

  // Park the real pointer before anything is launched. ffmpeg's
  // -capture_cursor 0 does not suppress it on macOS 26, and it never moves
  // during a take, so it would otherwise sit motionless in frame. Doing it now
  // rather than after launch means no subprocess spawns once the browser has
  // focus.
  // Outside the window on both axes, so it cannot land in the crop and cannot
  // raise a real hover on the page either.
  const PARK = { x: WIN.x + WIN.w + 60, y: WIN.y + WIN.h - 20 };
  log(`  real pointer parked off-frame at (${PARK.x},${PARK.y}): ${parkPointer(PARK.x, PARK.y) ? 'yes' : 'NO'}`);

  const browser = await chromium.launch({
    headless: false,
    args: [
      `--window-position=${WIN.x},${WIN.y}`,
      `--window-size=${WIN.w},${WIN.h}`,
      '--hide-crash-restore-bubble',
      '--disable-session-crashed-bubble',
      '--disable-infobars',
      '--no-default-browser-check',
      '--no-first-run',
    ],
  });

  const context = await browser.newContext({
    viewport: null,           // fill the real window; inherits the display's 2x
    // Non-negotiable. Under prefers-reduced-motion every motion component on
    // this site is SKIPPED, not shortened, and design.css clamps CSS animation
    // to .001ms. Forcing it here means the machine's own setting cannot reach
    // the page and silently flatten the entire recording.
    reducedMotion: 'no-preference',
    colorScheme: 'light',
    locale: 'en-IN',
    timezoneId: 'Asia/Kolkata',
  });

  // Runs at document-start on every hard navigation, and the node it appends
  // lives on document.body, outside React's #root, so SPA route changes cannot
  // unmount it either.
  await context.addInitScript(CURSOR_INIT);

  const page = await context.newPage();
  await page.goto(`${BASE}/health`, { waitUntil: 'domcontentloaded' }).catch(() => {});

  // Self-calibrating capture rect. Measuring the window rather than assuming a
  // chrome height means this survives a Chromium update or a different display.
  const geo = await page.evaluate(() => ({
    sx: window.screenX, sy: window.screenY,
    ow: window.outerWidth, oh: window.outerHeight,
    iw: window.innerWidth, ih: window.innerHeight,
    dpr: window.devicePixelRatio,
  }));
  log(`\n  window ${geo.ow}x${geo.oh} at (${geo.sx},${geo.sy}) · viewport ${geo.iw}x${geo.ih} · dpr ${geo.dpr}`);
  if (geo.iw < 1024) {
    console.error(`  viewport is ${geo.iw}px wide — below the 1024 breakpoint. The hero beams, the`);
    console.error('  FailureModes axis and the side-by-side agent arms will all be missing.');
    process.exit(1);
  }

  // Calibration happened on /health; leave it before recording starts, or the
  // first seconds of the take are a JSON blob.
  await page.goto('about:blank', { waitUntil: 'domcontentloaded' }).catch(() => {});

  // Four points off the bottom: the window has rounded corners and the desktop
  // shows through them otherwise.
  const rect = { x: geo.sx, y: geo.sy, w: geo.ow, h: geo.oh - 4 };
  // The browser must be, and stay, the frontmost window: avfoundation records
  // whatever composites over the crop region.
  const appPath = chromium.executablePath().replace(/\/Contents\/MacOS\/.*$/, '');
  const stopRaising = DRY ? () => {} : keepFrontmost(appPath, PARK, 2000);
  await page.bringToFront();
  await new Promise((r) => setTimeout(r, 1200));

  const rec = DRY
    ? new NullRecorder()
    : new Recorder(join(outDir, 'raw.mov'), rect, {
        fps: Number(val('--fps', '60')),
        scale: geo.dpr,
        device: await screenDeviceIndex(),
      });

  const marks = {};
  const mark = (name) => {
    marks[name] = rec.now();
    log(`      · mark ${name} @ ${(marks[name] / 1000).toFixed(1)}s`);
  };

  const list = ONLY ? shots.filter((s) => ONLY.split(',').includes(s.id)) : shots;
  const rows = [];

  await rec.start();
  const runAll = async () => {
    for (const shot of list) {
      // Cheap and idempotent. avfoundation captures the composited screen, so
      // anything that steals focus mid-take lands in the video instead of the
      // site.
      const tStart = rec.now();
      log(`\n  [${(tStart / 1000).toFixed(1).padStart(6)}s] ${shot.id} — ${shot.label}`);
      try {
        await shot.run({ page, base: BASE, mark, log, skipModel: SKIP_MODEL });
      } catch (e) {
        log(`      !! ${shot.id} failed: ${e.message}`);
        rows.push({ id: shot.id, label: shot.label, budget: shot.budget, tStart, tEnd: rec.now(), error: e.message });
        continue;
      }
      const tEnd = rec.now();
      const actual = (tEnd - tStart) / 1000;
      const drift = actual - shot.budget;
      log(`      ${actual.toFixed(1)}s (budget ${shot.budget}s, ${drift >= 0 ? '+' : ''}${drift.toFixed(1)}s)`);
      rows.push({ id: shot.id, label: shot.label, budget: shot.budget, tStart, tEnd, actual });
    }
  };

  try {
    await runAll();
  } finally {
    const total = rec.now();
    stopRaising();
    await rec.stop();
    const manifest = {
      base: BASE, dry: DRY, skipModel: SKIP_MODEL,
      startedAt: new Date().toISOString(),
      rect, viewport: { w: geo.iw, h: geo.ih }, dpr: geo.dpr,
      totalMs: total, marks, shots: rows,
    };
    writeFileSync(join(outDir, 'shot-times.json'), JSON.stringify(manifest, null, 2));
    log(`\n  total ${(total / 1000).toFixed(1)}s across ${rows.length} shots`);
    log(`  manifest -> ${join(outDir, 'shot-times.json')}`);
    const failed = rows.filter((r) => r.error);
    if (failed.length) log(`  \x1b[31m${failed.length} shot(s) errored: ${failed.map((f) => f.id).join(', ')}\x1b[0m`);
    await browser.close();
  }
}

main().catch((e) => { console.error(e); process.exit(1); });
