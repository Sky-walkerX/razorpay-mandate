/**
 * Small integers as words.
 *
 * This lived inside `runShape.ts` until `data/policy.ts` needed it too. Policy
 * cannot import from `runShape`, because `runShape` imports from policy, so the
 * choice was a second copy of the word list or a module neither owns. A second
 * copy is how the max-quantity-4-against-a-policy-that-says-5 bug happened, in
 * a repo whose whole argument is that nothing is retyped.
 */

const ONES = [
  'zero', 'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
  'ten', 'eleven', 'twelve', 'thirteen', 'fourteen', 'fifteen', 'sixteen',
  'seventeen', 'eighteen', 'nineteen',
];
const TENS = ['', '', 'twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'];

/**
 * "Three orders went through" is a sentence and "3 orders went through" is a
 * log line. Anything past 99 stays a numeral, which is the point at which a
 * count stops reading as prose anyway.
 */
export function spell(n: number): string {
  if (!Number.isInteger(n) || n < 0 || n > 99) return String(n);
  if (n < 20) return ONES[n];
  const t = TENS[Math.floor(n / 10)];
  const o = n % 10;
  return o === 0 ? t : `${t}-${ONES[o]}`;
}

/** Sentence-cased, for the head of a sentence. */
export function Spell(n: number): string {
  const s = spell(n);
  return s.charAt(0).toUpperCase() + s.slice(1);
}
