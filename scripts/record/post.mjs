#!/usr/bin/env node
/**
 * Turn raw.mov into final.mp4, using cut points computed from the take.
 *
 *   node post.mjs                       most recent take
 *   node post.mjs --take out/take-...   a specific one
 *   node post.mjs --ramp 6              a harder speed-up on the slow arm
 *
 * The only edit made is a speed ramp across the stretch of shot 8 where the
 * unprotected agent is shopping to its turn limit. Those marks were written by
 * the driver at capture time, so nothing here is eyeballed on a timeline. The
 * enforced arm's refusals and the final side-by-side both stay at 1x, because
 * they are the argument; the ramp only covers the part where a spinner is the
 * only thing moving.
 */
import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync, readdirSync, readFileSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const argv = process.argv.slice(2);
const val = (f, d) => { const i = argv.indexOf(f); return i >= 0 && argv[i + 1] ? argv[i + 1] : d; };

import { rampRegions, savedSeconds } from './lib/ramp.mjs';

const RAMP = Number(val('--ramp', '5'));
const WIDTH = Number(val('--width', '1920'));

function latestTake() {
  const outDir = join(HERE, 'out');
  const takes = readdirSync(outDir)
    .filter((d) => d.startsWith('take-') && existsSync(join(outDir, d, 'raw.mov')))
    .map((d) => ({ d, t: statSync(join(outDir, d)).mtimeMs }))
    .sort((a, b) => b.t - a.t);
  if (!takes.length) throw new Error('no take with a raw.mov under out/');
  return join(outDir, takes[0].d);
}

const take = val('--take', null) ?? latestTake();
const raw = join(take, 'raw.mov');
const out = join(take, 'final.mp4');
const manifest = JSON.parse(readFileSync(join(take, 'shot-times.json'), 'utf8'));

console.log(`\n  take     ${take}`);
console.log(`  source   ${raw}`);

// The captured duration, straight from the file rather than from our own clock:
// screencapture finalises a moment after SIGINT, so the file is usually a touch
// longer than the driver's last mark.
const probe = execFileSync('ffprobe', [
  '-v', 'error', '-show_entries', 'format=duration',
  '-of', 'default=noprint_wrappers=1:nokey=1', raw,
]).toString().trim();
const dur = parseFloat(probe);
console.log(`  duration ${dur.toFixed(1)}s`);

// Every mark pair named <prefix>ramp_start / <prefix>ramp_end becomes a
// sped-up region. Two exist: the unprotected agent shopping to its turn limit,
// and the sandbox waiting on a real temperature-0 compile. Both are honest
// waits worth showing, and neither is worth a minute of a five-minute video.
// Shared with sync-script.mjs, which needs the same mapping to place the
// voiceover's timecodes in the cut rather than in the raw capture.
const regions = rampRegions(manifest, dur);

let filter;
if (regions.length) {
  // Normal segments are whatever falls between the ramped ones.
  const parts = [];
  let cursor = 0;
  const saved = savedSeconds(regions, RAMP);
  for (const r of regions) {
    if (r.a > cursor + 0.05) parts.push({ from: cursor, to: r.a, speed: 1 });
    parts.push({ from: r.a, to: r.b, speed: RAMP, name: r.name });
    cursor = r.b;
  }
  parts.push({ from: cursor, to: null, speed: 1 });

  for (const r of regions) {
    console.log(`  ramp     ${r.name.padEnd(6)} ${r.a.toFixed(1)}s -> ${r.b.toFixed(1)}s at ${RAMP}x`);
  }
  console.log(`  saves    ${saved.toFixed(1)}s`);
  console.log(`  final    ~${(dur - saved).toFixed(1)}s`);

  const chains = parts.map((p, i) => {
    const trim = p.to === null ? `trim=${p.from}` : `trim=${p.from}:${p.to}`;
    const pts = p.speed === 1 ? 'setpts=PTS-STARTPTS' : `setpts=(PTS-STARTPTS)/${p.speed}`;
    return `[0:v]${trim},${pts}[v${i}]`;
  });
  const labels = parts.map((_, i) => `[v${i}]`).join('');
  filter =
    chains.join(';') +
    `;${labels}concat=n=${parts.length}:v=1:a=0[cat];` +
    `[cat]scale=${WIDTH}:-2:flags=lanczos[out]`;
} else {
  console.log('  ramp     none (no usable ramp marks in the manifest) — straight encode');
  filter = `[0:v]scale=${WIDTH}:-2:flags=lanczos[out]`;
}

const args = [
  '-y', '-i', raw,
  '-filter_complex', filter,
  '-map', '[out]',
  '-an',                       // voiceover is added later
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '18',
  '-pix_fmt', 'yuv420p',       // universal playback, including Keynote/QuickTime
  '-movflags', '+faststart',
  out,
];

console.log('\n  encoding…');
const r = spawnSync('ffmpeg', args, { stdio: ['ignore', 'ignore', 'pipe'] });
if (r.status !== 0) {
  console.error(r.stderr?.toString().split('\n').slice(-25).join('\n'));
  process.exit(1);
}
const finalDur = execFileSync('ffprobe', [
  '-v', 'error', '-show_entries', 'format=duration',
  '-of', 'default=noprint_wrappers=1:nokey=1', out,
]).toString().trim();
const mb = (statSync(out).size / 1e6).toFixed(1);
console.log(`\n  done  ${out}`);
console.log(`        ${parseFloat(finalDur).toFixed(1)}s · ${mb} MB · ${WIDTH}px wide\n`);
