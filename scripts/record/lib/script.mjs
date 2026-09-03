/**
 * The voiceover script is the single source of truth, and it is the markdown
 * file a human edits -- not a duplicated JSON of the same lines.
 *
 * Sections are `## M:SS - M:SS · Title` and the spoken text is the blockquote
 * lines under each. Everything else in the file is direction for the person
 * reading it and never reaches the synthesiser.
 */
import { readFileSync } from 'node:fs';

const secs = (mmss) => {
  const [m, s] = mmss.split(':').map(Number);
  return m * 60 + s;
};

export function loadScript(path) {
  const raw = readFileSync(path, 'utf8');
  const parts = raw.split(/^## (?=\d)/m).slice(1);
  return parts.map((part, i) => {
    const head = part.split('\n')[0];
    const m = head.match(/^(\d:\d\d)\s*[–-]\s*(\d:\d\d)\s*·\s*(.*)$/);
    if (!m) throw new Error(`unparseable section heading: ${head}`);
    const text = part
      .split('\n')
      .filter((l) => l.startsWith('> '))
      .map((l) => l.slice(2).trim())
      .join('\n')
      .replace(/\n{2,}/g, '\n\n')   // blank blockquote lines are paragraph breaks
      .replace(/\n(?!\n)/g, ' ')    // wrapped lines are one sentence
      .trim();
    return {
      index: i + 1,
      id: m[3].toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
      title: m[3],
      start: secs(m[1]),
      end: secs(m[2]),
      get window() { return this.end - this.start; },
      text,
      words: text.split(/\s+/).length,
    };
  });
}
