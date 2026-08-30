import evidence from './evidence.json';
import type { Verdict } from './policy';

/**
 * One real run, replayed. `evidence.json` carries every decision from a single
 * `audit.jsonl` in order, so the feed is a replay rather than a selection and
 * there is no cherry-picking step to argue with. The run is named on screen.
 */
export interface Decision {
  seq: number;
  verdict: Verdict;
  items: string;
  /** Cites the part by numeral and human label. Empty when nothing was breached. */
  reason: string;
  amountPaise: number;
  seller: string;
  note: string;
  /** This record's link in the hash chain. */
  hash: string;
  /** Whether money actually crossed the boundary. */
  executed: boolean;
}

/** Newest first, which is the order the feed reads in. */
export const DECISIONS: Decision[] = [...evidence.feed.decisions]
  .map((d) => ({ ...d, verdict: d.verdict as Verdict }))
  .reverse();

/** The real chain, most recent first. */
export const CHAIN = DECISIONS.map((d) => d.hash.replace(/^sha256:/, ''));

export const COUNTS = evidence.feed.counts;

/** The run this console is reading, and the files it came from. */
export const SOURCE = evidence.source;

/** Containment, false block and conformance, all measured. */
export const SCOREBOARD = evidence.scoreboard;

/** Which run the feed replays, e.g. `enforce/budget_salami_005`. */
export const FEED_RUN = evidence.feed.run;
