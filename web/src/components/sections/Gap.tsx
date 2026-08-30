import Reveal from '../Reveal';

const RAIL = [
  ['Total budget', '₹2,000.00'],
  ['Seller', 'Blinkit'],
  ['Valid until', '5 Sep 2026'],
];

const MEANT = [
  ['Max per order', '₹1,000.00'],
  ['Max per item', '₹500.00'],
  ['Blocked categories', 'Alcohol'],
  ['Orders per day', '3'],
  ['Max qty per item', '4'],
];

export default function Gap() {
  return (
    <section id="gap">
      <div className="wrap sec">
        <Reveal className="sec-h">
          <h2>The payment rail holds three things. People mean considerably more.</h2>
          <p>
            UPI Reserve Pay knows a total cap, a seller and an expiry. AP2&rsquo;s Intent
            Mandate lands in the same place. Everything meant beyond those three has been
            living in a system prompt — which makes the control protecting your money a
            language model&rsquo;s willingness to keep remembering an instruction while an
            attacker writes into its context.
          </p>
        </Reveal>

        <Reveal>
          <div className="gap-grid">
            <div className="gap-col">
              <h3>What the rail can hold</h3>
              <p className="sub">Enforced by the payment network itself.</p>
              <ul className="gap-list">
                {RAIL.map(([k, v]) => (<li key={k}>{k}<span className="v">{v}</span></li>))}
              </ul>
            </div>
            <div className="gap-col">
              <h3>What the person said</h3>
              <p className="sub">Everything below the rule had nowhere to go but a prompt.</p>
              <ul className="gap-list">
                {RAIL.map(([k, v]) => (<li key={k}>{k}<span className="v">{v}</span></li>))}
                {MEANT.map(([k, v]) => (<li key={k} className="ghost">{k}<span className="v">{v}</span></li>))}
              </ul>
            </div>
          </div>
        </Reveal>

        <Reveal className="quotes">
          <blockquote className="quote">
            &ldquo;Order my usual groceries before the match, under ₹2,000.&rdquo;
            <cite>
              Carries a dozen unstated conditions. Nothing alcoholic. Don&rsquo;t swap the
              ₹80 dal for the ₹400 organic one. Not the seller who sent rotten produce.
              One order, not five.
            </cite>
          </blockquote>
          <blockquote className="quote">
            A shopping agent holds a private mandate, reads untrusted seller-controlled
            text, and can move money.
            <cite>
              All three at once, by construction. You cannot remove any one of them
              without removing the product.
            </cite>
          </blockquote>
        </Reveal>
      </div>
    </section>
  );
}
