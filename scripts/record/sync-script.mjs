/**
 * Rewrite the voiceover script's timecodes from a take's own measured shots.
 *
 * The headings in `docs/video/voiceover-script.md` are `## M:SS - M:SS · Title`
 * and a person reads against them. They are also the only numbers in the video
 * pipeline that were maintained by hand, and on 4 Sep that is exactly what went
 * wrong: inserting one beat left two sections both claiming 0:21 and every
 * heading after them describing the old cut.
 *
 * So they are derived now, like every other number in this repo. Section N takes
 * its window from shot N of the take, in order, and the two counts must match or
 * this refuses rather than guessing which section moved.
 *
 * `assemble` still pins the audio from `shot-times.json` itself. This only fixes
 * what the reader sees, so the page and the cut agree.
 *
 *   node sync-script.mjs                 newest take, write
 *   node sync-script.mjs --check         exit 1 if the file is out of date
 *   node sync-script.mjs --take <dir>    a specific take
 */
import { readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { rampRegions, savedSeconds, toFinal } from './lib/ramp.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, 'out');
const SCRIPT = resolve(HERE, '../../docs/video/voiceover-script.md');

const mmss = (s) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

function newestTake() {
  const takes = readdirSync(OUT)
    .filter((d) => d.startsWith('take-'))
    .sort()
    .reverse();
  for (const t of takes) {
    try {
      // Skip rehearsals. `npm run fast` writes a manifest too, and it is almost
      // always the newest thing in out/, so defaulting to it would mean the
      // default path never works.
      const j = JSON.parse(readFileSync(join(OUT, t, 'shot-times.json'), 'utf8'));
      if (j.dry || j.skipModel) continue;
      return join(OUT, t);
    } catch { /* a take that never got far enough to write one */ }
  }
  throw new Error('no real take in out/ — record one, or pass --take <dir>');
}

const args = process.argv.slice(2);
const check = args.includes('--check');
const takeDir = args.includes('--take') ? args[args.indexOf('--take') + 1] : newestTake();

const times = JSON.parse(readFileSync(join(takeDir, 'shot-times.json'), 'utf8'));

// A dry rehearsal does not press the two buttons that call a model, so `agent`
// and `sandbox` measure about eight seconds each instead of roughly a hundred
// and eleven and thirty-six. Writing timecodes from one produces a script whose
// two longest sections claim eight-second windows, and a reader would discover
// that only by running out of video mid-sentence.
if (times.dry || times.skipModel) {
  console.error(
    `\n  ${takeDir.split('/').pop()} is a rehearsal (dry=${!!times.dry}, ` +
    `skipModel=${!!times.skipModel}).\n` +
    `  Its model beats are seconds long rather than minutes, so its timings are\n` +
    `  not the video's. Record a real take, or pass --take <a real one>.\n`,
  );
  process.exit(2);
}
// The script is read against `final.mp4`, not against the raw capture, so every
// timestamp has to be mapped through the ramps. Reading the raw durations
// straight out of the manifest is the bug this file shipped with: a 345.5s take
// that cut to 4:57 produced a 5:46 script, and the agent section claimed
// eighty-one seconds for thirty-seven seconds of video.
const RAMP = Number(args.includes('--ramp') ? args[args.indexOf('--ramp') + 1] : 5);
const regions = rampRegions(times, Infinity);

let raw = 0;
const shots = times.shots.map((s) => {
  const seconds = s.actual ?? (s.tEnd - s.tStart) / 1000;
  const from = raw;
  raw += seconds;
  return { id: s.id, start: toFinal(from, regions, RAMP), end: toFinal(raw, regions, RAMP) };
});

const md = readFileSync(SCRIPT, 'utf8');
const headings = [...md.matchAll(/^## (\d:\d\d)\s*[–-]\s*(\d:\d\d)\s*·\s*(.*)$/gm)];

if (headings.length !== shots.length) {
  console.error(
    `\n  ${headings.length} script sections against ${shots.length} shots.\n` +
    `  Add or remove a section so they line up; this will not guess.\n\n` +
    shots.map((s, i) => `   ${String(i + 1).padStart(2)}  ${s.id}`).join('\n') + '\n',
  );
  process.exit(1);
}

let out = md;
const rows = [];
for (const [i, h] of headings.entries()) {
  const { id, start, end } = shots[i];
  const want = `## ${mmss(start)} – ${mmss(end)} · ${h[3]}`;
  rows.push([id, h[3], h[0] === want ? '' : `was ${h[1]}–${h[2]}`, end - start]);
  out = out.replace(h[0], want);
}
const t = shots[shots.length - 1].end;

const stale = rows.filter((r) => r[2]).length;
console.log(
  `\n  ${takeDir.split('/').pop()}  ${mmss(t)} in the cut ` +
  `(${mmss(raw)} raw, ${savedSeconds(regions, RAMP).toFixed(0)}s ramped out at ${RAMP}x)\n`,
);
for (const [id, title, note, window] of rows) {
  console.log(`   ${id.padEnd(18)} ${String(Math.round(window)).padStart(3)}s  ${title.padEnd(42)} ${note}`);
}

if (check) {
  console.log(stale ? `\n  ${stale} heading(s) out of date\n` : '\n  in sync\n');
  process.exit(stale ? 1 : 0);
}

writeFileSync(SCRIPT, out);
console.log(stale ? `\n  rewrote ${stale} heading(s)\n` : '\n  already in sync\n');
