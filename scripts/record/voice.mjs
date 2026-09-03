#!/usr/bin/env node
/**
 * Voiceover generation against ElevenLabs.
 *
 *   node voice.mjs list                    what this account can use, Indian accents first
 *   node voice.mjs audition                short clip per candidate, from the real script
 *   node voice.mjs audition --voices a,b   only these
 *   node voice.mjs render --voice <id>     all 12 sections as separate files
 *   node voice.mjs build --voice <id>      render, then lay out to a timeline-aligned track
 *   node voice.mjs mux --voice <id>        build, then mux into final.mp4
 *
 * Sections are generated separately and placed at their own timecode rather than
 * concatenated. That is what keeps the audio locked to the picture: a section
 * that comes out half a second long cannot push everything after it out of sync,
 * and any one section can be regenerated and dropped back in on its own.
 */
import { execFileSync, spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadScript } from './lib/script.mjs';

const HERE = dirname(fileURLToPath(import.meta.url));
const REPO = join(HERE, '..', '..');
const SCRIPT = join(REPO, 'docs', 'video', 'voiceover-script.md');

const argv = process.argv.slice(2);
const cmd = argv[0] ?? 'list';
const val = (f, d) => { const i = argv.indexOf(f); return i >= 0 && argv[i + 1] ? argv[i + 1] : d; };
const has = (f) => argv.includes(f);

// Multilingual v2 rather than v3: v3 is more expressive but you lose the
// stability/similarity controls, and on technical copy full of rupee figures and
// clause names, control is worth more than range.
const MODEL = val('--model', 'eleven_multilingual_v2');
const FORMAT = 'mp3_44100_128';

function apiKey() {
  const envPath = join(REPO, '.env');
  if (existsSync(envPath)) {
    const m = readFileSync(envPath, 'utf8').match(/^ELEVEN(?:LABS)?_API_KEY\s*=\s*["']?([^"'\s]+)/m);
    if (m) return m[1];
  }
  if (process.env.ELEVENLABS_API_KEY) return process.env.ELEVENLABS_API_KEY;
  console.error(
    '\n  No ElevenLabs key found.\n' +
    '  Add ELEVENLABS_API_KEY=... to .env (it is gitignored), then re-run.\n',
  );
  process.exit(1);
}

const KEY = apiKey();
const api = async (path, init = {}) => {
  const r = await fetch(`https://api.elevenlabs.io${path}`, {
    ...init,
    headers: { 'xi-api-key': KEY, ...(init.headers ?? {}) },
  });
  if (!r.ok) throw new Error(`${path} -> ${r.status} ${(await r.text()).slice(0, 300)}`);
  return r;
};

const OUT = join(HERE, 'out', 'vo');
mkdirSync(OUT, { recursive: true });

/** Voices already on the account. */
async function myVoices() {
  const j = await (await api('/v1/voices')).json();
  return (j.voices ?? []).map((v) => ({
    id: v.voice_id,
    name: v.name,
    accent: v.labels?.accent ?? '',
    desc: v.labels?.description ?? '',
    use: v.labels?.use_case ?? '',
    category: v.category,
  }));
}

/** The shared library, which is where the Indian-English voices actually live. */
async function sharedIndian(pageSize = 40) {
  const qs = new URLSearchParams({
    page_size: String(pageSize), language: 'en', accent: 'indian',
  });
  try {
    const j = await (await api(`/v1/shared-voices?${qs}`)).json();
    return (j.voices ?? []).map((v) => ({
      id: v.voice_id, name: v.name, accent: v.accent ?? 'indian',
      desc: v.description ?? '', use: v.use_case ?? '',
      owner: v.public_owner_id, uses: v.cloned_by_count ?? v.usage_character_count_1y ?? 0,
    }));
  } catch (e) {
    console.error(`  (shared library unavailable: ${e.message.slice(0, 120)})`);
    return [];
  }
}

async function tts(voiceId, text, outPath, settings) {
  const body = {
    text,
    model_id: MODEL,
    voice_settings: settings ?? {
      // Measured-in-the-ear defaults for narration: stability high enough that
      // it does not drift between sections, low enough that it is not flat.
      stability: 0.45,
      similarity_boost: 0.8,
      style: 0.15,
      use_speaker_boost: true,
    },
  };
  const r = await api(`/v1/text-to-speech/${voiceId}?output_format=${FORMAT}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  writeFileSync(outPath, Buffer.from(await r.arrayBuffer()));
  return outPath;
}

const dur = (f) =>
  parseFloat(execFileSync('ffprobe', [
    '-v', 'error', '-show_entries', 'format=duration',
    '-of', 'default=noprint_wrappers=1:nokey=1', f,
  ]).toString().trim());

// ---------------------------------------------------------------- commands

async function cmdList() {
  const mine = await myVoices();
  const shared = await sharedIndian();
  const isIndian = (v) => /indian|india/i.test(`${v.accent} ${v.desc}`);

  console.log(`\n  on this account (${mine.length})`);
  for (const v of mine.sort((a, b) => Number(isIndian(b)) - Number(isIndian(a)))) {
    const tag = isIndian(v) ? '\x1b[32m● indian\x1b[0m' : '  ' + (v.accent || v.category || '');
    console.log(`    ${v.id}  ${v.name.padEnd(22)} ${tag}  ${v.desc}`);
  }

  if (shared.length) {
    console.log(`\n  shared library, English + Indian accent (${shared.length})`);
    for (const v of shared.slice(0, 25)) {
      console.log(`    ${v.id}  ${v.name.padEnd(22)} ${String(v.use).padEnd(16)} ${v.desc.slice(0, 60)}`);
    }
    console.log('\n  Add one to the account before rendering with it:');
    console.log('    node voice.mjs add --owner <public_owner_id> --voice <id> --name <name>');
  }
  console.log();
}

async function cmdAdd() {
  const owner = val('--owner'), voice = val('--voice'), name = val('--name', 'imported');
  if (!owner || !voice) { console.error('need --owner and --voice'); process.exit(1); }
  const r = await api(`/v1/voices/add/${owner}/${voice}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ new_name: name }),
  });
  console.log('  added:', JSON.stringify(await r.json()));
}

/**
 * Audition on real copy, not a generic pangram.
 *
 * The clip is section 6 -- the attack. It is the hardest thing in the script to
 * read well: a rupee figure, a millisecond figure, a product name, a clause
 * being named, and a rhetorical turn in the middle. A voice that survives it
 * will survive the rest.
 */
async function cmdAudition() {
  const script = loadScript(SCRIPT);
  const sec = script[Number(val('--section', '6')) - 1];
  const dir = join(OUT, 'audition');
  mkdirSync(dir, { recursive: true });

  let candidates;
  if (val('--voices')) {
    candidates = val('--voices').split(',').map((id) => ({ id: id.trim(), name: id.trim() }));
  } else {
    const mine = await myVoices();
    const indian = mine.filter((v) => /indian|india/i.test(`${v.accent} ${v.desc}`));
    candidates = (indian.length ? indian : mine).slice(0, 6);
  }
  if (!candidates.length) { console.error('  no candidate voices; run `list` first'); process.exit(1); }

  console.log(`\n  auditioning ${candidates.length} voice(s) on section ${sec.index}, "${sec.title}"`);
  console.log(`  ${sec.text.length} characters each · ${candidates.length * sec.text.length} credits total\n`);
  for (const v of candidates) {
    const safe = v.name.replace(/[^A-Za-z0-9]+/g, '-');
    const out = join(dir, `${safe}--${v.id}.mp3`);
    try {
      await tts(v.id, sec.text, out);
      console.log(`    ✓ ${v.name.padEnd(24)} ${dur(out).toFixed(1)}s  ${out}`);
    } catch (e) {
      console.log(`    ✗ ${v.name.padEnd(24)} ${e.message.slice(0, 100)}`);
    }
  }
  console.log(`\n  listen:  open ${dir}\n`);
}

async function cmdRender() {
  const voice = val('--voice');
  if (!voice) { console.error('need --voice <id>'); process.exit(1); }
  const script = loadScript(SCRIPT);
  const only = val('--only');
  const list = only ? script.filter((s) => only.split(',').includes(String(s.index))) : script;
  const dir = join(OUT, voice);
  mkdirSync(dir, { recursive: true });

  const chars = list.reduce((n, s) => n + s.text.length, 0);
  console.log(`\n  rendering ${list.length} section(s), ${chars} characters\n`);
  let over = 0;
  for (const s of list) {
    const out = join(dir, `${String(s.index).padStart(2, '0')}-${s.id}.mp3`);
    await tts(voice, s.text, out);
    const d = dur(out);
    const fit = d <= s.window;
    if (!fit) over++;
    console.log(
      `    ${String(s.index).padStart(2)} ${s.id.padEnd(24)} ${d.toFixed(1)}s / ${s.window}s ` +
      (fit ? `\x1b[32mfits\x1b[0m` : `\x1b[31mOVER by ${(d - s.window).toFixed(1)}s\x1b[0m`),
    );
  }
  console.log(over ? `\n  ${over} section(s) run past their window — trim the text or they will overlap.\n` : '\n  all sections fit.\n');
}

/**
 * Lay the sections onto one track at their own timecodes.
 *
 * adelay per input then amix, rather than concat: a section is pinned to the
 * moment its visual starts, so drift cannot accumulate down the video.
 */
async function cmdBuild() {
  const voice = val('--voice');
  if (!voice) { console.error('need --voice <id>'); process.exit(1); }
  const script = loadScript(SCRIPT);
  const dir = join(OUT, voice);
  const files = script.map((s) => {
    const f = join(dir, `${String(s.index).padStart(2, '0')}-${s.id}.mp3`);
    if (!existsSync(f)) throw new Error(`missing ${f} — run render first`);
    return { s, f };
  });

  const total = Math.max(...files.map(({ s, f }) => s.start + dur(f))) + 1;
  const inputs = files.flatMap(({ f }) => ['-i', f]);
  const chains = files.map(({ s }, i) => `[${i}:a]adelay=${Math.round(s.start * 1000)}|${Math.round(s.start * 1000)}[d${i}]`);
  const mixIn = files.map((_, i) => `[d${i}]`).join('');
  const filter =
    chains.join(';') +
    `;${mixIn}amix=inputs=${files.length}:dropout_transition=0:normalize=0[mix];` +
    `[mix]apad=whole_dur=${total.toFixed(2)},alimiter=limit=0.95[out]`;

  const out = join(dir, 'vo.wav');
  const r = spawnSync('ffmpeg', [
    '-y', ...inputs, '-filter_complex', filter, '-map', '[out]',
    '-ar', '48000', '-ac', '2', out,
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  if (r.status !== 0) { console.error(r.stderr.toString().split('\n').slice(-20).join('\n')); process.exit(1); }
  console.log(`\n  track: ${out}  (${dur(out).toFixed(1)}s)\n`);
  return out;
}

async function cmdMux() {
  const vo = await cmdBuild();
  const voice = val('--voice');
  const takes = readdirSync(join(HERE, 'out'))
    .filter((d) => d.startsWith('take-') && existsSync(join(HERE, 'out', d, 'final.mp4')))
    .map((d) => ({ d, t: statSync(join(HERE, 'out', d)).mtimeMs }))
    .sort((a, b) => b.t - a.t);
  if (!takes.length) { console.error('no take with a final.mp4'); process.exit(1); }
  const video = join(HERE, 'out', takes[0].d, 'final.mp4');
  const out = join(HERE, 'out', takes[0].d, 'pitch-with-vo.mp4');
  const r = spawnSync('ffmpeg', [
    '-y', '-i', video, '-i', vo,
    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-shortest',
    '-movflags', '+faststart', out,
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  if (r.status !== 0) { console.error(r.stderr.toString().split('\n').slice(-20).join('\n')); process.exit(1); }
  console.log(`  done: ${out}  (${dur(out).toFixed(1)}s, voice ${voice})\n`);
}

const cmds = { list: cmdList, add: cmdAdd, audition: cmdAudition, render: cmdRender, build: cmdBuild, mux: cmdMux };
if (!cmds[cmd]) { console.error(`unknown command "${cmd}". one of: ${Object.keys(cmds).join(', ')}`); process.exit(1); }
cmds[cmd]().catch((e) => { console.error('\n  ' + e.message + '\n'); process.exit(1); });
