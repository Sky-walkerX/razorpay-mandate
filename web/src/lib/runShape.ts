import { COUNTS, DECISIONS, type Decision } from '@/data/decisions';
import { PARTS, type Part } from '@/data/policy';
import { spell } from '@/lib/spell';

// Re-exported so `ChainSection` keeps its one import site.
export { spell };

/**
 * The shape of one replayed run, derived rather than described.
 *
 * The dashboard used to state its own story in prose and draw three charts
 * beside it. This module computes the story instead: which part did the
 * refusing, how long the unbroken stretch of identical refusals ran, and how
 * the sentence at the top of the page should read. If the feed is ever
 * regenerated from a different run, the headline and the drawing follow the
 * data instead of a designer's memory of it.
 *
 * Nothing here reads a figure that is not in `evidence.json`.
 */


function sentenceCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * The page's headline, in the landing page's two-tone form: a claim, then the
 * turn that lands in `ink-3`. Both halves are counts from the feed.
 */
export function headline(): { lead: string; turn: string } {
  const { allowed, refused } = COUNTS;

  if (refused === 0) {
    return {
      lead: `${sentenceCase(spell(allowed))} ${allowed === 1 ? 'order' : 'orders'} went through.`,
      turn: 'None were refused.',
    };
  }
  if (allowed === 0) {
    return {
      lead: 'Nothing went through.',
      turn: `${sentenceCase(spell(refused))} ${refused === 1 ? 'attempt was' : 'attempts were'} refused.`,
    };
  }
  return {
    lead: `${sentenceCase(spell(allowed))} ${allowed === 1 ? 'order' : 'orders'} went through.`,
    turn: `${sentenceCase(spell(refused))} did not.`,
  };
}

/**
 * The part every refusal in this run cites, when there is exactly one. Null
 * when the refusals are split across several parts, in which case no single
 * clause can be named and the page must not pretend otherwise.
 */
export function bindingPart(): { part: Part; count: number } | null {
  const refusals = DECISIONS.filter((d) => d.verdict === 'deny');
  if (refusals.length === 0) return null;

  const reasons = new Set(refusals.map((d) => d.reason));
  if (reasons.size !== 1) return null;

  const reason = [...reasons][0];
  const part = PARTS.find((p) => reason.startsWith(`Part ${p.n} `));
  return part ? { part, count: refusals.length } : null;
}

export interface Attempt {
  seq: number;
  executed: boolean;
  amountPaise: number;
  /** Cumulative committed spend once this attempt had been evaluated. */
  runningPaise: number;
  seller: string;
  note: string;
}

/**
 * Every evaluated attempt in the order the gateway saw it, carrying the
 * running total at that point. A refused attempt holds the total flat, which
 * is the whole shape the strip is drawing.
 */
export function attempts(): Attempt[] {
  const chronological = [...DECISIONS].sort((a, b) => a.seq - b.seq);
  let running = 0;
  return chronological.map((d) => {
    if (d.executed) running += d.amountPaise;
    return {
      seq: d.seq,
      executed: d.executed,
      amountPaise: d.amountPaise,
      runningPaise: running,
      seller: d.seller,
      note: d.note,
    };
  });
}

/** The largest amount that actually moved, for scaling the strip's columns. */
export function largestExecutedPaise(): number {
  return DECISIONS.reduce((m, d) => (d.executed ? Math.max(m, d.amountPaise) : m), 0);
}

export type ChainEntry =
  | { kind: 'row'; decision: Decision }
  | {
      kind: 'elision';
      /** Newest and oldest sequence numbers inside the collapsed stretch. */
      fromSeq: number;
      toSeq: number;
      count: number;
      reason: string;
      verdict: Decision['verdict'];
    };

/**
 * The chain, with any unbroken stretch of identical decisions collapsed to one
 * line that says how long it ran.
 *
 * Fifty rows that differ in nothing but a hash are fifty rows a reader skips.
 * One line saying "forty-nine more, every one refused at Part 4" is the same
 * information and is the more striking claim. The newest member of a stretch
 * always stays drawn in full, so the collapse never hides the most recent
 * decision.
 *
 * `DECISIONS` is newest-first and the returned list keeps that order.
 */
export function chainEntries(minRun = 3): ChainEntry[] {
  const out: ChainEntry[] = [];

  for (let i = 0; i < DECISIONS.length; ) {
    const head = DECISIONS[i];
    let j = i + 1;
    while (
      j < DECISIONS.length &&
      DECISIONS[j].verdict === head.verdict &&
      DECISIONS[j].reason === head.reason
    ) {
      j++;
    }

    const runLength = j - i;
    out.push({ kind: 'row', decision: head });

    if (runLength > minRun) {
      // The head is already drawn; the elision covers everything after it.
      const rest = DECISIONS.slice(i + 1, j);
      out.push({
        kind: 'elision',
        fromSeq: rest[0].seq,
        toSeq: rest[rest.length - 1].seq,
        count: rest.length,
        reason: head.reason,
        verdict: head.verdict,
      });
    } else {
      for (let k = i + 1; k < j; k++) out.push({ kind: 'row', decision: DECISIONS[k] });
    }

    i = j;
  }

  return out;
}
