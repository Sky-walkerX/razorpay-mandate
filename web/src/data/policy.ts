/**
 * The nine constraint types, in the order the gateway evaluates them.
 *
 * Each carries two names. `label` is what a person reads — it is the only one
 * that appears in the interface. `key` is the identifier in the signed policy
 * and in the audit log, and it surfaces in exactly one place: the policy
 * contract view, where the point is to show the document that was actually
 * signed. Everywhere else, a person managing their own spending should not
 * have to read a field name to understand their own limit.
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
  /** The shape the compiler emits, for the reference table. */
  shape: string;
  /** What the constraint is evaluated against. */
  against: string;
  /** Whether the user said it, or the compiler proposed it at read-back. */
  source: 'heard' | 'inferred' | 'unset';
}

export const PARTS: Part[] = [
  {
    n: 1, key: 'budget.total', label: 'Total budget', kind: 'limit',
    bound: '₹2,000.00', shape: '{max: paise}',
    against: 'everything committed so far', source: 'heard',
  },
  {
    n: 2, key: 'budget.per_transaction', label: 'Max per order', kind: 'limit',
    bound: '₹1,000.00', shape: '{max: paise}',
    against: 'the amount of this order', source: 'heard',
  },
  {
    n: 3, key: 'budget.per_item', label: 'Max per item', kind: 'limit',
    bound: '₹500.00', shape: '{max: paise}',
    against: 'the dearest line item', source: 'heard',
  },
  {
    n: 4, key: 'velocity', label: 'Orders per day', kind: 'limit',
    bound: '3 per day', shape: '{max_actions, window}',
    against: 'orders already committed today', source: 'heard',
  },
  {
    n: 5, key: 'quantity.max_per_item', label: 'Max qty per item', kind: 'limit',
    bound: '4 per item', shape: '{max: int}',
    against: 'the quantity on each line', source: 'inferred',
  },
  {
    n: 6, key: 'merchant.allow', label: 'Allowed sellers', kind: 'rule',
    bound: 'Zepto, Blinkit, Instamart', shape: '[merchant_id]',
    against: 'the seller this order resolves to', source: 'heard',
  },
  {
    n: 7, key: 'category.deny', label: 'Blocked categories', kind: 'rule',
    bound: 'Alcohol', shape: '[category]',
    against: 'the category each item resolves to', source: 'heard',
  },
  {
    n: 8, key: 'time.window', label: 'Valid until', kind: 'rule',
    bound: '5 Sep 2026', shape: '{before, after}',
    against: "the gateway's clock", source: 'inferred',
  },
  {
    n: 9, key: 'item.deny_recent', label: 'Repeat orders', kind: 'rule',
    bound: 'Not set', shape: '{window_days, source}',
    against: 'your recent order history', source: 'unset',
  },
];

export const LIMITS = PARTS.filter((p) => p.kind === 'limit');
export const RULES = PARTS.filter((p) => p.kind === 'rule');

/** The plain-language intent this mandate was compiled from. */
export const INTENT =
  'Order groceries for the week from Zepto, Blinkit or Instamart. Stay under ' +
  '₹2,000 in total and ₹1,000 per order. No single item over ₹500. Nothing ' +
  'alcoholic. At most 3 orders.';

export const MANDATE = {
  id: 'mnd_groceries_01',
  signedBy: 'user_8f2c',
  signedOn: '26 August 2026',
  policyHash: '9f2c4d1a77b0e6c3d9114f2a8e6b03cc71ad55e2',
  totalBudgetPaise: 200_000,
  committedPaise: 189_000,
};
