import { Link } from 'react-router-dom';
import SiteNav from '../components/SiteNav';
import SiteFooter from '../components/SiteFooter';
import GatewayPanel from '../components/GatewayPanel';
import Reveal from '../components/Reveal';
import Console from '../components/console/Console';
import Gap from '../components/sections/Gap';
import FailureModes from '../components/sections/FailureModes';
import HowItHolds from '../components/sections/HowItHolds';
import YourLimits from '../components/sections/YourLimits';
import Proof from '../components/sections/Proof';

export default function Landing() {
  return (
    <>
      <SiteNav />
      <main id="top">
        <section className="hero">
          <div className="wrap hero-in">
            <div>
              <h1>
                A limit does not need to be persuaded.{' '}
                <em>It stops at the number you set.</em>
              </h1>
              <p className="lede">
                Mandate turns what you actually meant into a signed set of limits, then
                checks every order your agent tries to place against them in plain code.{' '}
                <b>A language model reads your words exactly once, and you approve the result.</b>{' '}
                After that it never gets a vote on whether money moves.
              </p>
              <div className="hero-cta">
                <Link className="btn btn-p" to="/dashboard">
                  Open the console
                  <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                </Link>
                <a className="btn btn-s" href="#limits">See the nine limits</a>
              </div>
              <dl className="hero-facts">
                <div className="fact">
                  <dt>The parts</dt>
                  <dd><b>Five limits, four rules.</b> A closed set of nine.</dd>
                </div>
                <div className="fact">
                  <dt>Order of precedence</dt>
                  <dd><b>Refuse beats unknown beats allow.</b> Nothing passes by default.</dd>
                </div>
                <div className="fact">
                  <dt>Credentials</dt>
                  <dd>Your agent holds <b>none</b>. Only a handle to the gateway.</dd>
                </div>
              </dl>
            </div>
            <GatewayPanel />
          </div>
        </section>

        <Gap />
        <FailureModes />
        <HowItHolds />
        <YourLimits />
        <Proof />

        <section id="console" className="dash-section">
          <div className="wrap sec">
            <Reveal className="sec-h">
              <h2>Your side of it: what the agent tried, and what the limits did.</h2>
              <p>
                One mandate, the limits you signed, and every order checked against them —
                paid, refused with the limit named, or sent to you.
              </p>
            </Reveal>
            <Reveal>
              <Console />
            </Reveal>
          </div>
        </section>
      </main>
      <SiteFooter />
    </>
  );
}
