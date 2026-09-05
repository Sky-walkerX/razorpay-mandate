/**
 * What changed between one attempt and the next.
 *
 * The agent is not repaired by the gateway. It is refused, it reads the clause,
 * and it picks a different basket on its own. That behaviour is real and measured
 * (six of twelve `enforce` traces read DENY then ALLOW), but on screen it arrived
 * as two rows a viewer had to compare by eye. This names the difference so the
 * cause and the effect sit next to each other.
 *
 * Deliberately says nothing about *why* it changed. The gateway names the limit
 * that stopped it; what the agent does next is the model's choice, and claiming the
 * gateway steered the repair would be the wrong story about the wrong component.
 */

export interface BasketLine {
  sku: string;
  qty: number;
  title?: string;
}

const name = (line: BasketLine) => line.title || line.sku;

/** Join a few phrases the way a person would say them out loud. */
function sentence(parts: string[]): string {
  if (parts.length === 1) return parts[0];
  if (parts.length === 2) return `${parts[0]} and ${parts[1]}`;
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

/**
 * A plain description of the change, or null when nothing worth naming moved.
 *
 * Null rather than "no change" on purpose: an unchanged retry is a real thing an
 * agent does, and a row reading "changed nothing" invites a viewer to read it as a
 * repair that failed rather than as a repeat.
 */
export function describeRepair(
  before: { merchant?: string; items?: BasketLine[] } | undefined,
  after: { merchant?: string; items?: BasketLine[] } | undefined,
): string | null {
  if (!before?.items || !after?.items) return null;

  const was = new Map(before.items.map((i) => [i.sku, i]));
  const now = new Map(after.items.map((i) => [i.sku, i]));
  const parts: string[] = [];

  for (const [sku, line] of was) {
    const kept = now.get(sku);
    if (!kept) {
      parts.push(`dropped ${name(line)}`);
    } else if (kept.qty < line.qty) {
      parts.push(`cut ${name(line)} from ${line.qty} to ${kept.qty}`);
    } else if (kept.qty > line.qty) {
      parts.push(`raised ${name(line)} from ${line.qty} to ${kept.qty}`);
    }
  }

  for (const [sku, line] of now) {
    if (!was.has(sku)) parts.push(`added ${line.qty} × ${name(line)}`);
  }

  if (before.merchant && after.merchant && before.merchant !== after.merchant) {
    parts.push(`moved to ${after.merchant}`);
  }

  if (!parts.length) return null;
  // Four changes is already more than a row can carry legibly, and the tail is
  // rarely the interesting one.
  const shown = parts.slice(0, 3);
  const rest = parts.length - shown.length;
  return sentence(shown) + (rest > 0 ? `, and ${rest} more change${rest > 1 ? 's' : ''}` : '');
}
