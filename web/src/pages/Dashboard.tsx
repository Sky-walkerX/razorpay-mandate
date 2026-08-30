import { Link } from 'react-router-dom';
import Console from '../components/console/Console';
import { MANDATE } from '../data/policy';

/**
 * The console on its own route, for the demo. Same component the landing page
 * embeds — the claim and the screen cannot drift apart.
 */
export default function Dashboard() {
  return (
    <main className="dash-page">
      <div className="wrap dash-wrap">
        <div className="dash-head">
          <Link className="back" to="/">
            <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M13 8H3M7 4 3 8l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Mandate
          </Link>
          <h1>Your agent&rsquo;s spending</h1>
          <p>
            Mandate <span className="mono">{MANDATE.id}</span>, signed {MANDATE.signedOn}.
            Every order your agent proposes is checked against the limits you approved,
            before any money moves.
          </p>
        </div>
        <Console homeLink />
      </div>
    </main>
  );
}
