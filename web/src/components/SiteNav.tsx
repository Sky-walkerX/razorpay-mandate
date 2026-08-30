import { Link } from 'react-router-dom';
import Wordmark from './Wordmark';
import TestChip from './TestChip';

const LINKS = [
  ['#gap', 'The gap'],
  ['#modes', 'Failure modes'],
  ['#how', 'How it holds'],
  ['#limits', 'Your limits'],
  ['#proof', 'Proof'],
];

export default function SiteNav() {
  return (
    <nav className="nav">
      <div className="wrap nav-in">
        <Link className="brand" to="/">
          <Wordmark />
          Mandate
        </Link>
        <div className="nav-links">
          {LINKS.map(([href, label]) => (
            <a key={href} href={href}>{label}</a>
          ))}
        </div>
        <div className="nav-right">
          <TestChip />
          <Link className="btn btn-p" to="/dashboard">Open console</Link>
        </div>
      </div>
    </nav>
  );
}
