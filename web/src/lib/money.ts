/**
 * All money in this app is integer paise, matching the gateway. No floats
 * anywhere near an amount — the compiler, the evaluator and the audit log all
 * agree on paise, and the only place a decimal point appears is here, at the
 * moment a number becomes text on a screen.
 */

const inr = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

const inrWhole = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 });

/** 412500 -> "₹4,125.00" */
export function rupees(paise: number): string {
  return `₹${inr.format(paise / 100)}`;
}

/** 189000 -> "₹1,890" — for tile figures, where the paise are noise. */
export function rupeesWhole(paise: number): string {
  return `₹${inrWhole.format(Math.round(paise / 100))}`;
}

/** Splits "₹1,890.00" into ["₹1,890", ".00"] so the paise can be set smaller. */
export function rupeesParts(paise: number): [string, string] {
  const whole = Math.trunc(paise / 100);
  const frac = Math.abs(paise % 100);
  return [`₹${inrWhole.format(whole)}`, `.${String(frac).padStart(2, '0')}`];
}
