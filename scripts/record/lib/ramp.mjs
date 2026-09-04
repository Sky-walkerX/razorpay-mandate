/**
 * Where the speed ramps are, and what they do to a timestamp.
 *
 * `post.mjs` speeds up two stretches of the raw capture: the unprotected agent
 * shopping to its turn limit, and the sandbox waiting on a real temperature-0
 * compile. Both are honest waits worth showing and neither is worth a minute of
 * a five-minute video.
 *
 * This lives in its own file because two things need it and they must not
 * disagree. `sync-script.mjs` first shipped without it and wrote the voiceover
 * script's timecodes straight from the raw shot durations, so a 345.5s capture
 * that cut to 4:57 produced a script claiming 5:46, with "Same AI, both sides"
 * given eighty-one seconds for a section that is thirty-seven in the video. A
 * reader would have found that by running three-quarters of a minute long.
 */

/** The ramped regions in a take, in raw seconds, earliest first. */
export function rampRegions(manifest, durationSeconds = Infinity) {
  const marks = manifest.marks ?? {};
  return Object.keys(marks)
    .filter((k) => k.endsWith('ramp_start'))
    .map((k) => {
      const end = k.replace(/ramp_start$/, 'ramp_end');
      return {
        name: k.replace(/_?ramp_start$/, '') || 'agent',
        a: marks[k] / 1000,
        b: marks[end] / 1000,
      };
    })
    .filter((r) => Number.isFinite(r.a) && Number.isFinite(r.b) && r.b > r.a + 2 && r.b < durationSeconds)
    .sort((x, y) => x.a - y.a);
}

/** Where a raw timestamp lands in the finished cut. */
export function toFinal(t, regions, ramp) {
  let out = t;
  for (const r of regions) {
    if (t <= r.a) break;
    const inside = Math.min(t, r.b) - r.a;
    out -= inside - inside / ramp;
  }
  return out;
}

/** Total seconds the ramps remove from a take. */
export function savedSeconds(regions, ramp) {
  return regions.reduce((s, r) => s + (r.b - r.a) - (r.b - r.a) / ramp, 0);
}
