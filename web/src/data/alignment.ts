import evidence from './evidence.json';

/**
 * Where this mandate lives once it leaves the gateway — on a rail, and under
 * the regulation.
 *
 * Every fate, count and status here is read from `evidence.json`, which
 * `mandate evidence` writes from `mandate.policy.rails` and
 * `mandate.policy.regulatory` against the signed policy. Nothing on this screen
 * is retyped, and a compliance table is the last place in the repo a retyped
 * claim should be allowed to survive: nobody checks one against running code,
 * which is exactly why it gets written optimistically.
 * `tests/harness/test_evidence.py` compares this payload against the modules.
 *
 * The two halves answer opposite questions and are kept apart for that reason.
 * `rails` asks whether a rail can carry our clause. `regulatory` asks whether
 * we carry a regulator's obligation. One word, "held", would otherwise mean two
 * different things in two adjacent tables.
 */

/** How a rail carries a clause, worst to best. */
export type Fate = 'none' | 'prose' | 'ap2' | 'rail';

/** How this component stands against one obligation. */
export type Status = 'held' | 'partial' | 'gap' | 'out_of_scope';

export interface ClauseFate {
  clause: string;
  /** What a person reads. Matches the part label used everywhere else. */
  label: string;
  statedByUser: boolean;
  ap2: Fate;
  ap2Note: string;
  reservePay: Fate;
  reservePayNote: string;
}

const a = evidence.alignment;

export const FATES: ClauseFate[] = a.rails.fates.map((f) => ({
  clause: f.clause,
  label: f.label,
  statedByUser: f.stated_by_user,
  ap2: f.ap2 as Fate,
  ap2Note: f.ap2_note,
  reservePay: f.reserve_pay as Fate,
  reservePayNote: f.reserve_pay_note,
}));

export const RAILS = {
  totalClauses: a.rails.total_clauses,
  ap2Held: a.rails.ap2_held,
  ap2Lost: a.rails.ap2_lost,
  reservePayHeld: a.rails.reserve_pay_held,
  reservePayLost: a.rails.reserve_pay_lost,
  /** Clauses AP2 keeps only as words inside the intent description. */
  ap2Prose: a.rails.fates.filter((f) => f.ap2 === 'prose').length,
};

export interface Requirement {
  key: string;
  source: string;
  requirement: string;
  status: Status;
  mechanism: string;
  clause: string | null;
}

export const REQUIREMENTS: Requirement[] = a.regulatory.requirements.map((r) => ({
  key: r.key,
  source: r.source,
  requirement: r.requirement,
  status: r.status as Status,
  mechanism: r.mechanism,
  clause: r.clause ?? null,
}));

export const POSTURE = {
  held: a.regulatory.held,
  partial: a.regulatory.partial,
  gaps: a.regulatory.gaps,
  outOfScope: a.regulatory.out_of_scope,
};

export const CITATIONS: Record<
  string,
  { title: string; issued: string; note: string; checked: string }
> = a.regulatory.citations;

/** Stated, not mapped. The protocol is announced and unpublished. */
export const UAP = a.regulatory.uap_status;

/**
 * A Reserve Pay block names one payee. This mandate allows three, so the
 * projection reports the two it drops rather than collapsing the list quietly
 * to its first element.
 */
export const RESERVE_PAY = {
  payee: a.reserve_pay.payee,
  overflow: a.reserve_pay.payee_overflow,
  blockedPaise: a.reserve_pay.blocked_amount.value,
  expiry: a.reserve_pay.expiry,
};

export const AP2_EXPORT = {
  intentMandate: a.ap2_export.intent_mandate,
  paymentConstraints: a.ap2_export.payment_constraints,
  endpoint: a.ap2_export.endpoint,
  cli: a.ap2_export.cli,
};

export const MANDATE_ID = evidence.policy.mandate_id;
export const POLICY_HASH = evidence.policy.policy_hash.replace(/^sha256:/, '');

/**
 * Razorpay's own agent surface, and what a mandate in front of it does.
 *
 * Counted off the pinned tool snapshot and the upstream's own `destructiveHint`
 * annotations rather than described, so the page cannot claim a count Razorpay
 * does not make about itself. `mandate evidence` writes it; the numbers move
 * when Razorpay's surface moves, and the classification test goes red first.
 */
export interface RefusedTool {
  tool: string;
  reason: string;
}

const s = a.razorpay_surface;

export const SURFACE = {
  endpoint: s.endpoint,
  mediatedPath: s.mediated_path,
  total: s.total,
  destructive: s.destructive,
  readOnly: s.read_only,
  bound: s.bound as string[],
  refused: s.refused as RefusedTool[],
  passthroughCount: s.passthrough_count,
  /** Of this mandate's limits, how many a call carrying only an amount can reach. */
  evaluatedOnRawCall: s.limits_on_a_raw_call.evaluated,
  notApplicableOnRawCall: s.limits_on_a_raw_call.not_applicable,
  notApplicableIds: s.limits_on_a_raw_call.not_applicable_ids as string[],
};

/**
 * What it costs to express this mandate as blocks on the rail.
 *
 * A block names one payee and carries its own amount, so an allowlist of three
 * merchants under one total has two representations and both are wrong: one
 * block refuses two allowed shops, and one block per shop blocks three times the
 * money. Reporting only the first overstates the rail's rigidity; reporting only
 * the second hides that blocked funds are money the user cannot spend elsewhere.
 */
export const EXPOSURE = {
  payees: a.reserve_pay_exposure.payees,
  mandateCapPaise: a.reserve_pay_exposure.mandate_cap,
  blocksNeeded: a.reserve_pay_exposure.blocks_needed,
  blockedTotalPaise: a.reserve_pay_exposure.blocked_total,
  refusedPayees: a.reserve_pay_exposure.refused_payees as string[],
};
