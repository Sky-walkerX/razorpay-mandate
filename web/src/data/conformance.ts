import evidence from './evidence.json';

export interface ConformanceAttack {
  id: string;
  outcome: string;
  witnessExecuted: boolean;
  hardenedExecuted: boolean;
  /** What the attack tries, for someone who has never read the suite. */
  label: string;
}

/**
 * Plain-language names for the seventeen attacks.
 *
 * The suite's own ids (`quote.expired`, `replay.token`) are the right names in
 * the audit log and the wrong names on a screen, which is the same call this
 * project already made for clause ids: `plainMessage()` strips the `a.b:`
 * prefix off a refusal because the label beside it already says which limit
 * bound. An id tells a reader who already knows the suite what they already
 * knew; it tells everyone else nothing.
 *
 * The ids stay the key, so this map is checked against the run rather than
 * replacing it -- `test_every_conformance_attack_has_a_plain_english_name`
 * fails when the suite gains an attack and nobody names it here.
 */
const LABELS: Record<string, string> = {
  'replay.token': 'Reuse a cancelled token',
  'replay.intent': 'Replay an order already placed',
  'idem.forge': 'Forge a second order key',
  'race.velocity': 'Race past the order limit',
  'race.budget': 'Race past the budget',
  'capture.divergence': 'Capture more than was approved',
  'delegate.split': 'Split one basket across sessions',
  'escalate.self': 'Raise its own spending limit',
  'rail.divergence': 'Let the rail overcharge',
  'quote.forge': 'Pay against an unsigned price',
  'quote.expired': 'Pay against an expired price',
  'quote.sku_swap': "Reuse another item's price",
  'quote.merchant_swap': "Reuse another shop's price",
  'quote.requote_idem': 'Re-quote to get a fresh key',
  'approve.self': 'Approve its own held order',
  'approve.replay': 'Spend one approval twice',
  'approve.swap': 'Move an approval to another basket',
};

const raw = evidence.scoreboard.conformance;

export const CONFORMANCE = {
  total: raw.total,
  blocked: raw.blocked,
  escaped: raw.escaped,
  vacuous: raw.vacuous,
  raceTrials: raw.race_trials,
  attacks: raw.attacks.map(
    (a): ConformanceAttack => ({
      id: a.id,
      outcome: a.outcome,
      witnessExecuted: a.witness_executed,
      hardenedExecuted: a.hardened_executed,
      // Falling back to the id is deliberate: an unnamed attack shows up as
      // something a reader can report, rather than a blank chip.
      label: LABELS[a.id] ?? a.id,
    }),
  ),
};
