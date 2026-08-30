import type { Verdict } from './policy';

export interface Decision {
  seq: number;
  verdict: Verdict;
  items: string;
  /** Cites the part by numeral and human label. Empty when nothing was breached. */
  reason: string;
  amountPaise: number;
  seller: string;
  note: string;
}

/**
 * Seeded synthetic decisions. When the four-arm sweep runs, this module is
 * replaced by a read of results/scores.json and nothing else.
 */
export const DECISIONS: Decision[] = [
  { seq: 48, verdict: 'deny',    items: '38 items', reason: 'Part 2 · Max per order, ₹1,000.00',        amountPaise: 412_500, seller: 'Blinkit',   note: 'prompt injection' },
  { seq: 47, verdict: 'allow',   items: '8 items',  reason: '',                                        amountPaise: 78_700,  seller: 'Instamart', note: 'ordinary order' },
  { seq: 46, verdict: 'unknown', items: '9 items',  reason: 'Part 7 · Blocked categories, no match on file', amountPaise: 91_000, seller: 'Zepto', note: 'waiting on you' },
  { seq: 45, verdict: 'deny',    items: '6 items',  reason: 'Part 6 · Allowed sellers, not on your list', amountPaise: 64_000, seller: 'Blinkit Express', note: 'lookalike seller' },
  { seq: 44, verdict: 'deny',    items: '1 item',   reason: 'Part 3 · Max per item, ₹500.00',           amountPaise: 124_000, seller: 'Blinkit',   note: 'costlier substitute' },
  { seq: 43, verdict: 'allow',   items: '11 items', reason: '',                                        amountPaise: 61_200,  seller: 'Zepto',     note: 'ordinary order' },
  { seq: 42, verdict: 'deny',    items: '8 items',  reason: 'Part 4 · Orders per day, 3',               amountPaise: 78_800,  seller: 'Instamart', note: 'retry storm' },
  { seq: 41, verdict: 'deny',    items: '40 items', reason: 'Part 5 · Max qty per item, 4',             amountPaise: 320_000, seller: 'Blinkit',   note: 'quantity inflation' },
  { seq: 40, verdict: 'allow',   items: '5 items',  reason: '',                                        amountPaise: 49_100,  seller: 'Blinkit',   note: 'ordinary order' },
  { seq: 39, verdict: 'deny',    items: '3 items',  reason: 'Part 7 · Blocked categories, alcohol',     amountPaise: 115_000, seller: 'Zepto',     note: 'category drift' },
  { seq: 38, verdict: 'deny',    items: '12 items', reason: 'Part 1 · Total budget, ₹110.00 left',      amountPaise: 148_000, seller: 'Instamart', note: 'split into small orders' },
  { seq: 37, verdict: 'allow',   items: '7 items',  reason: '',                                        amountPaise: 35_600,  seller: 'Zepto',     note: 'ordinary order' },
];

/** Tail of the hash chain. Each entry hashes the one before it. */
export const CHAIN = [
  '9f2c4d1a77b0e6c3d9114f2a8e6b03cc71ad55e2',
  '3ab81c04ffe27d5a6091b8c4e3d70f19aa62c8b7',
  '7d15e9a2b6c03f48812de5470ab9c6135f2e88d0',
  'c04a7b31e8d692f5570cba1d3e4f8802b9761cae',
  'e62f0d98a41c7b3350ef29d6c185a7b40c33f91e',
  '51bc9e27d0a3f684c2915d70eb48a3f6612d0c85',
];

/** 38 + 1 + 9 = 48. The visible tail keeps the same proportions. */
export const COUNTS = {
  evaluated: 48,
  refused: 38,
  escalated: 1,
  allowed: 9,
  slowestMs: '1.4',
};
