/**
 * Python's `json.dumps(obj, sort_keys=True)`, reproduced byte for byte.
 *
 * `AuditLog._hash_body` hashes `json.dumps(body, sort_keys=True, default=str)`, so a
 * browser that wants to recompute a `record_hash` has to produce the exact same
 * string Python did. Two things make `JSON.stringify` the wrong tool, and both were
 * verified against a real record rather than assumed:
 *
 *   1. Python separates with `", "` and `": "` by default. The hashed string begins
 *      `{"action": {"amount": 9500, "attempt": 1, ...`. `JSON.stringify` emits no
 *      spaces at all and hashes to something else entirely.
 *
 *   2. Python's `ensure_ascii=True` escapes every non-ASCII character to `\uXXXX`.
 *      `JSON.stringify` passes them through. This is not hypothetical: a
 *      `rail.divergence` record carries a rupee sign in its clause detail.
 *
 * Key order is Python's, which sorts by code point. JavaScript's default `sort()`
 * compares UTF-16 code units, and the two disagree only above the BMP. Audit record
 * keys are ASCII field names, so this cannot bite here, but a schema that ever grows
 * an emoji key would need `localeCompare`-free code point sorting.
 */

const ESCAPES: Record<string, string> = {
  '"': '\\"',
  '\\': '\\\\',
  '\b': '\\b',
  '\f': '\\f',
  '\n': '\\n',
  '\r': '\\r',
  '\t': '\\t',
};

function encodeString(value: string): string {
  let out = '"';
  for (const char of value) {
    const escape = ESCAPES[char];
    if (escape !== undefined) {
      out += escape;
      continue;
    }
    const code = char.codePointAt(0)!;
    if (code < 0x20) {
      out += '\\u' + code.toString(16).padStart(4, '0');
    } else if (code < 0x7f) {
      out += char;
    } else if (code > 0xffff) {
      // Python emits a surrogate pair for an astral character, and so must we.
      const offset = code - 0x10000;
      const high = 0xd800 + (offset >> 10);
      const low = 0xdc00 + (offset & 0x3ff);
      out += '\\u' + high.toString(16).padStart(4, '0');
      out += '\\u' + low.toString(16).padStart(4, '0');
    } else {
      out += '\\u' + code.toString(16).padStart(4, '0');
    }
  }
  return out + '"';
}

function encodeNumber(value: number): string {
  if (!Number.isFinite(value)) {
    // Python writes bare Infinity/NaN here. Audit records carry integer paise and
    // never reach this, so refusing is safer than guessing at a shape nobody uses.
    throw new Error(`cannot canonicalise non-finite number: ${value}`);
  }
  return Number.isInteger(value) ? String(value) : String(value);
}

/** Serialise exactly as `json.dumps(value, sort_keys=True)` would. */
export function pythonJsonDumps(value: unknown): string {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (typeof value === 'number') return encodeNumber(value);
  if (typeof value === 'string') return encodeString(value);
  if (Array.isArray(value)) {
    return '[' + value.map(pythonJsonDumps).join(', ') + ']';
  }
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return (
      '{' +
      entries.map(([k, v]) => `${encodeString(k)}: ${pythonJsonDumps(v)}`).join(', ') +
      '}'
    );
  }
  throw new Error(`cannot canonicalise value of type ${typeof value}`);
}
