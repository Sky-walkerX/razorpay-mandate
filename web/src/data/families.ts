/**
 * The ten attack families, and which of the nine parts each one targets.
 *
 * Both halves are transcribed from `SPEC.md` — the family table in §5.1 and the
 * constraint table in §3 — and the counts agree with `corpus/corpus.json`, which
 * holds 180 items: ten families at twelve, plus sixty legitimate. Nothing here
 * is a guess about coverage. If a family is added to the corpus it has to be
 * added here too, and the map will show it dangling until an edge is drawn.
 *
 * `held_out` marks the three families that never ran during development and were
 * run once, at the end. `budget.salami` carries an asterisk the README states
 * plainly: it was repaired after being seen to fail, so its number dates to the
 * repair rather than to a locked drawer.
 */

/**
 * Who causes the failure in the world, which is not the same question as who
 * wrote the JSON. Every family in a red-team corpus is authored by definition;
 * this is the grouping the section argues, and `price.flip` is the one a
 * reasonable person can move.
 */
export type Cause = 'written' | 'agent' | 'rail';

export interface Family {
  id: string;
  cause: Cause;
  /** Held out of development entirely, run once at the end. */
  heldOut?: boolean;
  /** Reached the rail in `enforce` despite every constraint passing. */
  escaped?: boolean;
}

/**
 * Ordered so the three causes stay contiguous and the edges below cross as
 * little as possible. The order is presentational; the set is not.
 */
export const FAMILIES: Family[] = [
  { id: 'injection.description', cause: 'written' },
  { id: 'injection.seller_name', cause: 'written' },
  { id: 'injection.review', cause: 'written', heldOut: true },
  { id: 'merchant.lookalike', cause: 'written' },
  { id: 'category.laundering', cause: 'written' },
  { id: 'price.unit_confusion', cause: 'agent', heldOut: true },
  { id: 'budget.salami', cause: 'agent', heldOut: true },
  { id: 'price.flip', cause: 'rail', escaped: true },
  { id: 'retry.storm', cause: 'rail' },
  { id: 'time.boundary', cause: 'rail' },
];

/** Twelve items per family, and sixty legitimate items alongside them. */
export const ITEMS_PER_FAMILY = 12;

export const CAUSE_LABEL: Record<Cause, string> = {
  written: 'Someone writes it',
  agent: 'The agent does it',
  rail: 'The rail does it',
};

/**
 * The nine parts in the order that keeps the map close to planar. Keys, not
 * labels — the labels and reference numerals are read from the signed policy
 * through `data/policy`, so a bound renamed there renames itself here.
 */
export const PART_ORDER = [
  'budget.per_transaction',
  'merchant.allow',
  'category.deny',
  'budget.per_item',
  'quantity.max_per_item',
  'budget.total',
  'velocity',
  'time.window',
  'item.deny_recent',
] as const;

/**
 * Family to part, from the `Targets` column of SPEC.md §3.
 *
 * `item.deny_recent` appears in no row on purpose. It is implemented and
 * unit-tested and no family targets it, so it carries no containment evidence.
 * Adding a family to justify a constraint inverts the order the corpus was
 * frozen in, so it stays uncovered and declared.
 */
export const EDGES: ReadonlyArray<{ family: string; part: string }> = [
  { family: 'injection.description', part: 'budget.per_transaction' },
  { family: 'injection.seller_name', part: 'budget.per_transaction' },
  { family: 'injection.review', part: 'budget.per_transaction' },
  { family: 'price.flip', part: 'budget.per_transaction' },
  { family: 'merchant.lookalike', part: 'merchant.allow' },
  { family: 'category.laundering', part: 'category.deny' },
  { family: 'price.unit_confusion', part: 'budget.per_item' },
  { family: 'price.unit_confusion', part: 'quantity.max_per_item' },
  { family: 'budget.salami', part: 'budget.total' },
  { family: 'budget.salami', part: 'velocity' },
  { family: 'retry.storm', part: 'velocity' },
  { family: 'time.boundary', part: 'time.window' },
];

/** The parts no family targets. Derived, so it cannot drift out of date. */
export const UNCOVERED: ReadonlySet<string> = new Set(
  PART_ORDER.filter((key) => !EDGES.some((e) => e.part === key)),
);
