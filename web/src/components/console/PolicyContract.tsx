import { LIMITS, MANDATE, RULES, type Part } from '../../data/policy';

/**
 * The one view where the machine identifiers belong: this is the document that
 * was actually signed, and its field names are part of what the signature
 * covers. Each is paired with the label used everywhere else, so the two are
 * never mistaken for different things.
 */
function Line({ p }: { p: Part }) {
  return (
    <div className="cline">
      <span className="lbl">{p.label}</span>
      <span className="key">{p.key}</span>
      <span className="val">{p.bound}</span>
      <span className="src-col">
        {p.source === 'heard' ? 'you said it' : p.source === 'inferred' ? 'we proposed it' : 'not set'}
      </span>
    </div>
  );
}

export default function PolicyContract() {
  return (
    <div className="panel">
      <div className="panel-h">
        <h3>Policy contract</h3>
        <span className="r">
          {MANDATE.policyHash.slice(0, 4)}…{MANDATE.policyHash.slice(-4)}
        </span>
      </div>
      <div className="panel-b">
        <p className="note-under" style={{ marginTop: 0, marginBottom: 16 }}>
          Signed by <span className="mono">{MANDATE.signedBy}</span> on {MANDATE.signedOn},
          compiled once at temperature 0. Changing any line below produces a different
          hash and needs a new signature — the gateway will not check an order against an
          unsigned policy.
        </p>

        <div className="contract">
          <div className="cline chead">
            <span className="lbl">Limit</span>
            <span className="key">Field in the signed policy</span>
            <span className="val">Value</span>
            <span className="src-col">Source</span>
          </div>
          <div className="cgrp">Limits — a number to stay under</div>
          {LIMITS.map((p) => <Line key={p.key} p={p} />)}
          <div className="cgrp">Rules — a list, category or date to match</div>
          {RULES.map((p) => <Line key={p.key} p={p} />)}
          <div className="cfoot">
            Amounts stored as whole paise · rupees only · policy hash {MANDATE.policyHash}
          </div>
        </div>

        <p className="note-under">
          Two limits were proposed by the compiler rather than heard from you, and both
          were shown before you signed: an expiry, because an open-ended mandate has no
          natural end, and a quantity ceiling, because “groceries for the week” implies
          one of a thing, not forty.
        </p>
      </div>
    </div>
  );
}
