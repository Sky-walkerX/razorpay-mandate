import { PARTS } from '../../data/policy';

/**
 * The intent, with the phrases that became limits marked. Reading it back is
 * how consent gets attached to something checkable rather than to prose.
 */
const SEGMENTS: { text: string; mark?: boolean }[] = [
  { text: '“Order groceries for the week from ' },
  { text: 'Zepto, Blinkit or Instamart', mark: true },
  { text: '. Stay under ' },
  { text: '₹2,000 in total', mark: true },
  { text: ' and ' },
  { text: '₹1,000 per order', mark: true },
  { text: '. No single item over ' },
  { text: '₹500', mark: true },
  { text: '. ' },
  { text: 'Nothing alcoholic', mark: true },
  { text: '. At most ' },
  { text: '3 orders', mark: true },
  { text: '.”' },
];

export default function SignedIntent() {
  return (
    <>
      <p className="intent">
        {SEGMENTS.map((s, i) => (s.mark ? <mark key={i}>{s.text}</mark> : <span key={i}>{s.text}</span>))}
      </p>
      <ul className="kv">
        {PARTS.filter((p) => p.source !== 'unset').map((p) => (
          <li key={p.key}>
            <span className="k">{p.label}</span>
            <span className={`v${p.key === 'category.deny' ? ' deny' : ''}`}>{p.bound}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
