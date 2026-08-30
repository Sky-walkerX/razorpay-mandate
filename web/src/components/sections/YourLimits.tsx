import Reveal from '../Reveal';
import { PARTS } from '../../data/policy';

const SOURCE_WORD = { heard: 'you said it', inferred: 'we proposed it', unset: 'not set' } as const;

export default function YourLimits() {
  return (
    <section id="limits">
      <div className="wrap sec">
        <Reveal className="sec-h">
          <h2>Nine kinds of limit. A closed set, deliberately.</h2>
          <p>
            A general policy engine — Rego, Cedar, CEL — is a fortnight of work on its own
            and puts a check of unbounded cost directly in the payment path. A closed set
            buys three properties that can be stated as guarantees rather than hopes:
            checking always terminates, its cost is bounded and measurable, and the attack
            corpus can exercise every kind, so coverage is provable.
          </p>
          <p>
            They also divide cleanly by how they are checked. Five compare a number
            against a number you set — those are the limits, and an order either stays
            under or it does not. Four test a list, a category or a date — those are the
            rules, and an order either matches or it does not.
          </p>
        </Reveal>

        <Reveal>
          <div className="tblwrap">
            <div className="tblscroll">
              <table>
                <thead>
                  <tr>
                    <th>Part</th>
                    <th>Limit</th>
                    <th>Kind</th>
                    <th>Checked against</th>
                    <th>In this mandate</th>
                    <th>Where it came from</th>
                  </tr>
                </thead>
                <tbody>
                  {PARTS.map((p) => (
                    <tr key={p.key}>
                      <td><span className="ref">{p.n}</span></td>
                      <td className="nm">{p.label}</td>
                      <td><span className={`kind ${p.kind === 'rule' ? 'rule' : ''}`}>{p.kind}</span></td>
                      <td className="f">{p.against}</td>
                      <td className="k">{p.bound}</td>
                      <td><span className={`src ${p.source}`}>{SOURCE_WORD[p.source]}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="tbl-foot">
              <span><span className="kind">limit</span> a number to stay under</span>
              <span><span className="kind rule">rule</span> a list, category or date to match</span>
              <span><span className="src heard">you said it</span> in your own words</span>
              <span><span className="src inferred">we proposed it</span> shown to you before you signed</span>
            </div>
          </div>
        </Reveal>

        <Reveal>
          <p className="note-under">
            <b>A known gap, stated rather than hidden.</b> Part 9, repeat orders, is built
            and unit-tested, but no attack family targets it, so it carries no evidence
            that it works under attack. Adding a family to justify a limit is the inverse
            of how the corpus was frozen, so it stays uncovered and declared.
          </p>
          <p className="note-under">
            <b>One call worth arguing about.</b> Part 8, valid until, is filed as a rule
            because it tests the gateway&rsquo;s clock rather than a number the order
            carries. It could equally be read as a limit. The split describes how the
            checker works, so a reasonable person can move that one row.
          </p>
        </Reveal>
      </div>
    </section>
  );
}
