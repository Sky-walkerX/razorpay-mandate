import evidence from './evidence.json';
import { spell, Spell } from '@/lib/spell';

/**
 * The constraint types, in the order the gateway evaluates them.
 *
 * Every bound, date and provenance flag here is read from `evidence.json`,
 * which `mandate evidence` writes from the signed `policies/policy.yaml`.
 * Nothing on this screen is retyped. It used to be: the interface claimed a
 * max quantity of 4 against a policy that says 5, a hash that matched no
 * document, and a signing date two weeks out.
 *
 * Each part carries two names. `label` is what a person reads and is the only
 * one that appears in the interface. `key` is the identifier in the signed
 * policy and the audit log, and it surfaces only in the policy contract view,
 * where the point is to show the document that was actually signed.
 */

export type Kind = 'limit' | 'rule';
export type Verdict = 'allow' | 'deny' | 'unknown';

export interface Part {
  /** Reference numeral. Stable, and cited in every refusal. */
  n: number;
  /** Identifier in the signed policy. Shown only in the contract view. */
  key: string;
  /** What a person reads. */
  label: string;
  kind: Kind;
  /** The bound, already formatted for reading. */
  bound: string;
  /**
   * The bound as a number — integer paise for the budget clauses, a plain count
   * for velocity and quantity, and null for the four rules, which match rather
   * than measure. Read from the signed policy so headroom can be computed from
   * it instead of a figure retyped into a component.
   */
  max: number | null;
  /** The shape the compiler emits, for the reference table. */
  shape: string;
  /** What the constraint is evaluated against. */
  against: string;
  /**
   * Where the clause came from. `regulatory` is neither heard nor guessed: RBI's
   * Digital Payments E-mandate Framework, 2026 imposes it whether or not anyone
   * asked, so the read-back labels it instead of offering it for confirmation.
   */
  source: 'heard' | 'inferred' | 'regulatory' | 'unset';
}

/** `stated` is the policy's word for it; `heard` is the interface's. */
const SOURCE = {
  stated: 'heard',
  inferred: 'inferred',
  regulatory: 'regulatory',
  unset: 'unset',
} as const;

export const PARTS: Part[] = evidence.policy.parts.map((p) => ({
  n: p.n,
  key: p.key,
  label: p.label,
  kind: p.kind as Kind,
  bound: p.bound,
  max: p.max ?? null,
  shape: p.shape,
  against: p.against,
  source: SOURCE[p.source as keyof typeof SOURCE],
}));

/**
 * Two counts, and they are different numbers on purpose.
 *
 * `PART_COUNT` is how many kinds of limit the gateway implements and evaluates
 * on every order — ten. `SET_PART_COUNT` is how many of them this mandate
 * actually sets — nine, because `item.deny_recent` carries `source: 'unset'`.
 *
 * The web used to say "nine" in twenty-five places while rendering ten cards,
 * so a visitor who counted the cards concluded the copy was lying. Both numbers
 * are now counted rather than typed, which means a policy that switches
 * `item.deny_recent` on moves every sentence without anyone editing a
 * component. `test_no_tsx_spells_out_how_many_limits_the_policy_carries`
 * keeps it that way.
 */
export const PART_COUNT = PARTS.length;
export const SET_PART_COUNT = PARTS.filter((p) => p.source !== 'unset').length;

/** The same two counts as words, for prose. `Part…Word` leads a sentence. */
export const PART_COUNT_TEXT = spell(PART_COUNT);
export const PART_COUNT_TEXT_CAP = Spell(PART_COUNT);
export const SET_PART_COUNT_TEXT = spell(SET_PART_COUNT);
export const SET_PART_COUNT_TEXT_CAP = Spell(SET_PART_COUNT);

export const LIMITS = PARTS.filter((p) => p.kind === 'limit');
export const RULES = PARTS.filter((p) => p.kind === 'rule');

/** The plain-language intent this mandate was compiled from. */
export const INTENT = evidence.policy.source_text;

const totalBudget = evidence.policy.parts.find((p) => p.key === 'budget.total');

export const MANDATE = {
  id: evidence.policy.mandate_id,
  signedBy: evidence.policy.principal,
  signedOn: evidence.policy.signed_on,
  policyHash: evidence.policy.policy_hash.replace(/^sha256:/, ''),
  totalBudgetPaise: totalBudget?.max ?? 0,
  /** What this run actually spent, summed from the orders that executed. */
  committedPaise: evidence.feed.decisions
    .filter((d) => d.executed)
    .reduce((sum, d) => sum + d.amountPaise, 0),
};
