import type { Part } from '../data/policy';
import { rupeesWhole } from './money';

/**
 * What a limit row reports: how much room this order has left against the
 * bound, or how far past it the order went.
 *
 * Every figure here is computed from the signed bound in `evidence.json` and
 * the scenario's load fraction. Nothing is retyped. The old panel drew an
 * abstract fill and named no quantity at all, which meant the row said "over
 * limit" without ever saying over by how much, the one number a person
 * actually wants.
 */
export interface Readout {
  /** The headline figure: "₹110 left", or "over ₹3,125". */
  figure: string;
  /** The bound it is measured against: "of ₹2,000", "cap 3 per mandate". */
  against: string;
  breached: boolean;
}

/**
 * The share of a limit track given to "within bound", vs. the hatched
 * over-zone past it. Shared by every progress bar so a breach always crosses
 * the same line, whichever component draws it.
 */
export const CAP_AT = 68;

/** Budget clauses carry paise. Velocity and quantity carry a plain count. */
const isMoney = (part: Part) => part.key.startsWith('budget.');

/**
 * `load` is the order's consumption as a fraction of the bound, so 1.0 sits
 * exactly on the limit and anything above it is a breach. Counts are rounded
 * because a fourth order is a whole order, never 3.99 of one.
 */
export function readoutFor(part: Part, load: number): Readout | null {
  if (part.max == null) return null;

  const money = isMoney(part);
  const used = Math.round(load * part.max);
  const bound = money ? rupeesWhole(part.max) : part.bound;

  if (used > part.max) {
    const over = used - part.max;
    return {
      figure: money ? `over ${rupeesWhole(over)}` : `over by ${over}`,
      against: `cap ${bound}`,
      breached: true,
    };
  }

  const left = part.max - used;
  return {
    figure: money ? `${rupeesWhole(left)} left` : `${left} left`,
    against: `of ${bound}`,
    breached: false,
  };
}

/**
 * The share of the track a limit's load should fill. The cap sits at a fixed
 * fraction of the track so the region past it can be drawn and labelled before
 * anything ever goes there; a breach is then visibly past a line rather than
 * merely a differently coloured bar. Overshoot is clamped so a wild load still
 * reads as "off the end" instead of blowing out the row.
 */
export function fillPercent(load: number, capAt: number): number {
  return Math.min(load, 1.5) * capAt;
}
