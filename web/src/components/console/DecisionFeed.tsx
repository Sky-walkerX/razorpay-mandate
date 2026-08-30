import { DECISIONS, type Decision } from '../../data/decisions';
import { rupees } from '../../lib/money';

const WORD = { allow: 'allowed', deny: 'refused', unknown: 'needs you' } as const;

function Row({ d }: { d: Decision }) {
  return (
    <li className="fitem" data-v={d.verdict}>
      <span className={`badge ${d.verdict}`}>
        <s />
        {WORD[d.verdict]}
      </span>
      <span className="t">
        <span className="l1">#{d.seq} · {d.items}</span>
        <span className="l2">
          {d.reason ? <b>{d.reason}</b> : 'nothing was breached'}
        </span>
      </span>
      <span className="a">
        <span className="v">{rupees(d.amountPaise)}</span>
        <s>{d.seller} · {d.note}</s>
      </span>
    </li>
  );
}

export default function DecisionFeed({ limit }: { limit?: number }) {
  const rows = limit ? DECISIONS.slice(0, limit) : DECISIONS;
  return (
    <ul className={`feed${limit ? ' cap' : ''}`}>
      {rows.map((d) => <Row key={d.seq} d={d} />)}
    </ul>
  );
}
