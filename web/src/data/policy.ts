import evidence from './evidence.json';

/**
 * The nine constraint types, in the order the gateway evaluates them.
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
  /** Whether the user said it, or the compiler proposed it at read-back. */
  source: 'heard' | 'inferred' | 'unset';
}

/** `stated` is the policy's word for it; `heard` is the interface's. */
const SOURCE = { stated: 'heard', inferred: 'inferred', unset: 'unset' } as const;

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
