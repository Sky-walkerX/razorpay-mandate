import { COUNTS, DECISIONS } from '@/data/decisions';
import { MANDATE, type Part } from '@/data/policy';
import { rupeesWhole } from './money';

export type ReadoutStatus = 'pass' | 'halt' | 'unset';

export interface PartReadout {
  /** How many logged decisions cite this part as the reason they were refused. */
  citedCount: number;
  status: ReadoutStatus;
  /** The headline figure — a fraction of the bound, or the bound itself for a rule. */
  figure: string;
  sub: string;
  /** 0-100 fill for a limit's track; null for a rule, which has no track. */
  percent: number | null;
}

/** How many of the run's logged decisions were refused by this exact part. */
function citedCount(part: Part): number {
  const needle = `Part ${part.n} `;
  return DECISIONS.reduce((n, d) => n + (d.reason.startsWith(needle) ? 1 : 0), 0);
}

/**
 * What a constraint row reports for this run, not one simulated order:
 * how much of its bound the mandate has actually used, and whether it is the
 * one refusing attempts. Everything here is aggregated from the same replayed
 * decisions the feed shows — nothing is retyped or invented for a field this
 * run's log does not carry (`quantity.max_per_item` has no logged used-count,
 * so its row states the bound rather than a fabricated one).
 */
export function readoutForPart(part: Part): PartReadout {
  const cited = citedCount(part);

  if (part.source === 'unset') {
    return { citedCount: cited, status: 'unset', figure: part.bound, sub: 'no bound was signed', percent: null };
  }

  const status: ReadoutStatus = cited > 0 ? 'halt' : 'pass';

  switch (part.key) {
    case 'budget.total': {
      const used = MANDATE.committedPaise;
      const max = part.max ?? 0;
      return {
        citedCount: cited,
        status,
        figure: `${rupeesWhole(used)} / ${rupeesWhole(max)}`,
        sub: `${rupeesWhole(Math.max(max - used, 0))} left`,
        percent: max > 0 ? (used / max) * 100 : 0,
      };
    }

    case 'budget.per_transaction':
    case 'budget.per_item': {
      const used = DECISIONS.reduce((m, d) => Math.max(m, d.amountPaise), 0);
      const max = part.max ?? 0;
      return {
        citedCount: cited,
        status,
        figure: `${rupeesWhole(used)} / ${rupeesWhole(max)}`,
        sub: 'largest order this run',
        percent: max > 0 ? (used / max) * 100 : 0,
      };
    }

    case 'velocity': {
      const used = COUNTS.allowed;
      const max = part.max ?? 0;
      const atCap = used >= max;
      return {
        citedCount: cited,
        status: atCap ? 'halt' : 'pass',
        figure: `${used} / ${max}${atCap ? ' · at cap' : ''}`,
        sub: atCap ? `${cited} attempts refused past this cap` : 'room left',
        percent: max > 0 ? (used / max) * 100 : 0,
      };
    }

    case 'merchant.allow': {
      const sellers = new Set(DECISIONS.map((d) => d.seller));
      return {
        citedCount: cited,
        status,
        figure: part.bound,
        sub: `${sellers.size} seller${sellers.size === 1 ? '' : 's'} used, all on the list`,
        percent: null,
      };
    }

    // A rule matches rather than measures, so it has no fraction to report.
    // Its figure is the bound itself — the list, the category, the date — and
    // the line under it says how many of the run's refusals cited it. Both
    // halves read as standalone phrases, because they are set on their own
    // lines rather than run together in a sentence.
    default:
      if (part.kind === 'limit') {
        return { citedCount: cited, status, figure: part.bound, sub: 'not exceeded in this run', percent: null };
      }
      return {
        citedCount: cited,
        status,
        figure: part.bound,
        sub:
          cited === 0
            ? `no refusal in this run cited it`
            : `${cited} of ${COUNTS.evaluated} refusals cite it`,
        percent: null,
      };
  }
}
