import { Link } from 'react-router-dom';

export default function SiteFooter() {
  return (
    <footer>
      <div className="wrap foot">
        <p className="l">
          <b>Mandate</b> — a policy compiler and enforcement gateway for AI agents that
          spend money. Built for the Razorpay AI Buildathon 2026, Track 01. Test mode
          only; no real money moves, and every figure shown here is from a seeded
          synthetic run.
        </p>
        <div className="r">
          <a href="#gap">The gap</a>
          <a href="#how">How it holds</a>
          <a href="#limits">Your limits</a>
          <Link to="/dashboard">Console</Link>
        </div>
      </div>
    </footer>
  );
}
