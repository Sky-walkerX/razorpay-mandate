import Reveal from '../Reveal';

const STAGES = [
  {
    by: 'Model · temperature 0',
    model: true,
    title: 'Compile',
    body:
      'What you said becomes a fixed set of limits. The compiler marks what it heard ' +
      'against what it proposed, and refuses rather than approximating an intent that ' +
      'does not fit the nine types.',
    note: 'runs once · never asked again',
  },
  {
    by: 'You',
    title: 'Read back and sign',
    body:
      'You read your limits in plain language and sign them. Consent attaches to ' +
      'something checkable, not to prose. Signing fixes the policy hash.',
    note: 'policy hash · 9f2c…8ab1',
  },
  {
    by: 'Pure code',
    title: 'Enforce',
    body:
      'Every proposed order goes through the nine parts in pure functions with no I/O ' +
      'and no model. Allow and pay, refuse and say which limit, or come to you when ' +
      'the policy genuinely cannot decide.',
    note: 'place order · take payment · payment link',
  },
  {
    by: 'Append-only',
    title: 'Log',
    body:
      'Every decision enters a hash-chained log. Editing an earlier entry breaks every ' +
      'hash after it, so the record is tamper-evident rather than merely stored.',
    note: 'sha-256 · chained · replayable',
  },
];

export default function HowItHolds() {
  return (
    <section id="how">
      <div className="wrap sec">
        <Reveal className="sec-h">
          <h2>The model sits upstream of the money, and it goes there once.</h2>
          <p>Compiling is where interpretation is allowed to happen. Enforcing is where it is not.</p>
        </Reveal>

        <Reveal>
          <div className="pipe">
            {STAGES.map((s) => (
              <article className="stage" key={s.title} data-model={s.model ? '' : undefined}>
                <div className="st"><s />{s.by}</div>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
                <p className="note">{s.note}</p>
              </article>
            ))}
          </div>
          <p className="model-note">
            <s />
            Exactly one stage consults a language model, and it happens before anything is signed.
          </p>
        </Reveal>

        <div className="lat-wrap">
          <Reveal>
            <h3>A refusal stops everything. An unknown comes to you. Nothing passes by default.</h3>
            <p>
              Each of the nine parts answers allow, refuse or unknown, and they combine on
              a lattice rather than a score. A single refusal ends the check. Something the
              gateway cannot resolve — a product it has never seen — returns unknown, which
              comes to you and never falls through to allowed.
            </p>
            <p>This is four lines of code, which is the point. Rules fail closed; judging fails open.</p>
          </Reveal>

          <Reveal className="lat">
            <svg viewBox="0 0 520 220" role="img" aria-label="Refuse beats unknown, which beats allow">
              <defs>
                <marker id="ar" viewBox="0 0 8 8" refX="6.5" refY="4" markerWidth="6" markerHeight="6" orient="auto">
                  <path d="M0 1 6.5 4 0 7" fill="none" stroke="#8A8A93" strokeWidth="1.2" />
                </marker>
              </defs>
              <line x1="140" y1="110" x2="228" y2="110" stroke="#D9D9DE" strokeWidth="1.25" markerEnd="url(#ar)" />
              <line x1="292" y1="110" x2="380" y2="110" stroke="#D9D9DE" strokeWidth="1.25" markerEnd="url(#ar)" />

              <rect x="16" y="82" width="124" height="56" rx="8" fill="#EDF7F2" stroke="#0E7C56" />
              <rect x="34" y="103" width="8" height="8" fill="#0E7C56" />
              <text x="52" y="111" fontFamily="Geist Mono, monospace" fontSize="13" fill="#0E7C56" letterSpacing="1">ALLOW</text>
              <text x="34" y="127" fontFamily="Geist, sans-serif" fontSize="10.5" fill="#5E8D7B">pay</text>

              <rect x="228" y="82" width="124" height="56" rx="8" fill="#FBF4E7" stroke="#8A5A05" />
              <circle cx="250" cy="107" r="4.5" fill="#8A5A05" />
              <text x="264" y="111" fontFamily="Geist Mono, monospace" fontSize="13" fill="#8A5A05" letterSpacing="1">UNKNOWN</text>
              <text x="246" y="127" fontFamily="Geist, sans-serif" fontSize="10.5" fill="#A08454">come to the person</text>

              <rect x="380" y="82" width="124" height="56" rx="8" fill="#FDF0EE" stroke="#B42318" />
              <rect x="398" y="103" width="8" height="8" fill="#B42318" transform="rotate(45 402 107)" />
              <text x="416" y="111" fontFamily="Geist Mono, monospace" fontSize="13" fill="#B42318" letterSpacing="1">DENY</text>
              <text x="398" y="127" fontFamily="Geist, sans-serif" fontSize="10.5" fill="#A5736D">refuse, and say which</text>

              <text x="176" y="98" fontFamily="Geist Mono, monospace" fontSize="10" fill="#A9A9B1">&lt;</text>
              <text x="328" y="98" fontFamily="Geist Mono, monospace" fontSize="10" fill="#A9A9B1">&lt;</text>
              <line x1="16" y1="56" x2="504" y2="56" stroke="#EFEFF1" />
              <text x="16" y="182" fontFamily="Geist Mono, monospace" fontSize="11.5" fill="#4A4A52">if any(DENY): DENY</text>
              <text x="16" y="200" fontFamily="Geist Mono, monospace" fontSize="11.5" fill="#4A4A52">elif any(UNKNOWN): UNKNOWN</text>
              <text x="270" y="182" fontFamily="Geist Mono, monospace" fontSize="11.5" fill="#4A4A52">else: ALLOW</text>
              <text x="270" y="200" fontFamily="Geist Mono, monospace" fontSize="11.5" fill="#8A8A93">bounded, terminating</text>
            </svg>
            <p className="lat-cap">
              Amounts are whole paise. <span>No floats anywhere in the checking path.</span>
              <br />
              Rupees only. <span>An order in another currency is refused, never converted.</span>
            </p>
          </Reveal>
        </div>
      </div>
    </section>
  );
}
