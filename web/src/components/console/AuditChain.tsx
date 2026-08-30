import { CHAIN, COUNTS } from '../../data/decisions';

export default function AuditChain() {
  return (
    <div className="panel">
      <div className="panel-h">
        <h3>Audit chain</h3>
        <span className="r">{COUNTS.evaluated} entries · sha-256 · append-only</span>
      </div>
      <ul className="chain">
        {CHAIN.map((h, i) => (
          <li key={h}>
            <span className="seq">{String(COUNTS.evaluated - i).padStart(3, '0')}</span>
            <span className="h">{h}</span>
            <span className="ok">
              <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                <path d="M3 8.5 6.2 11.5 13 4.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              linked
            </span>
          </li>
        ))}
      </ul>
      <div className="panel-b" style={{ borderTop: '1px solid var(--rule)' }}>
        <p className="note-under" style={{ marginTop: 0 }}>
          Each entry hashes the one before it. Editing entry 12 changes its hash, which
          changes entry 13, and every entry after it. Verification walks the chain
          forward from the signed policy, so a broken link is located, not merely
          detected.
        </p>
      </div>
    </div>
  );
}
