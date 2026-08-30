import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import Wordmark from '../Wordmark';
import TestChip from '../TestChip';
import DecisionFeed from './DecisionFeed';
import SignedIntent from './SignedIntent';
import PolicyContract from './PolicyContract';
import AuditChain from './AuditChain';
import SyntheticNote from './SyntheticNote';
import { COUNTS } from '../../data/decisions';
import { MANDATE } from '../../data/policy';
import { rupees, rupeesParts } from '../../lib/money';

type Tab = 'overview' | 'log' | 'contract' | 'chain';

const TAB_IDS: Tab[] = ['overview', 'log', 'contract', 'chain'];

/** Deep-linkable, so a demo can open straight onto the audit chain. */
function tabFromHash(): Tab {
  if (typeof window === 'undefined') return 'overview';
  const h = window.location.hash.replace('#', '') as Tab;
  return TAB_IDS.includes(h) ? h : 'overview';
}

const TABS: [Tab, string, string?][] = [
  ['overview', 'Overview'],
  ['log', 'Decision log', String(COUNTS.evaluated)],
  ['contract', 'Policy contract'],
  ['chain', 'Audit chain'],
];

function Tiles() {
  const spent = useRef<HTMLSpanElement>(null);
  const [committed, fraction] = rupeesParts(MANDATE.committedPaise);
  const left = MANDATE.totalBudgetPaise - MANDATE.committedPaise;
  const pct = (MANDATE.committedPaise / MANDATE.totalBudgetPaise) * 100;

  // Fills once, on mount, rather than animating on every re-render.
  useEffect(() => {
    const el = spent.current;
    if (!el) return;
    const id = window.setTimeout(() => { el.style.width = `${pct}%`; }, 60);
    return () => window.clearTimeout(id);
  }, [pct]);

  return (
    <div className="tiles">
      <div className="tile">
        <div className="lb">Spent so far</div>
        <div className="vl">{committed}<small>{fraction}</small></div>
        <div className="meter"><i ref={spent as never} style={{ width: 0 }} /></div>
        <div className="fo"><b>{rupees(left)}</b> left of your {rupees(MANDATE.totalBudgetPaise)} budget</div>
      </div>
      <div className="tile">
        <div className="lb">Orders refused</div>
        <div className="vl">{COUNTS.refused}</div>
        <div className="fo">of {COUNTS.evaluated} checked · <b>each one says which limit</b></div>
      </div>
      <div className="tile">
        <div className="lb">Waiting on you</div>
        <div className="vl">{COUNTS.escalated}</div>
        <div className="fo"><b>An item we could not categorise</b> — your call</div>
      </div>
      <div className="tile">
        <div className="lb">Slowest check</div>
        <div className="vl">{COUNTS.slowestMs}<small> ms</small></div>
        <div className="fo">9 parts · <b>bounded by construction</b></div>
      </div>
    </div>
  );
}

/**
 * The operator surface. Used whole on /dashboard, and embedded on the landing
 * page so the marketing claim and the actual screen are the same component.
 */
export default function Console({ homeLink = false }: { homeLink?: boolean }) {
  const [tab, setTab] = useState<Tab>(tabFromHash);

  // Keeps the back button and a pasted link honest.
  useEffect(() => {
    const sync = () => setTab(tabFromHash());
    window.addEventListener('hashchange', sync);
    return () => window.removeEventListener('hashchange', sync);
  }, []);

  const select = (id: Tab) => {
    setTab(id);
    if (window.location.hash.replace('#', '') !== id) {
      window.history.replaceState(null, '', id === 'overview' ? ' ' : `#${id}`);
    }
  };

  return (
    <div className="app">
      <div className="app-bar">
        {homeLink ? (
          <Link className="brand" to="/"><Wordmark /> Mandate</Link>
        ) : (
          <span className="brand"><Wordmark /> Mandate</span>
        )}
        <span className="mid">
          {MANDATE.id}
          <span className="ok"><span className="pulse" style={{ width: 5, height: 5 }} />enforcing</span>
        </span>
        <span className="rr"><TestChip /></span>
      </div>

      <div className="app-tabs" role="tablist" aria-label="Console section">
        {TABS.map(([id, label, count]) => (
          <button
            key={id}
            type="button"
            role="tab"
            aria-selected={tab === id}
            onClick={() => select(id)}
          >
            {label}
            {count && <span className="cnt">{count}</span>}
          </button>
        ))}
      </div>

      <div className="app-body">
        {tab === 'overview' && (
          <>
            <Tiles />
            <div className="dgrid">
              <div className="panel">
                <div className="panel-h">
                  <h3>What you asked for</h3>
                  <span className="r">{MANDATE.signedBy} · 26 Aug</span>
                </div>
                <div className="panel-b"><SignedIntent /></div>
              </div>
              <div className="panel">
                <div className="panel-h">
                  <h3>Recent decisions</h3>
                  <span className="r">last 6 of {COUNTS.evaluated}</span>
                </div>
                <DecisionFeed limit={6} />
              </div>
            </div>
            <SyntheticNote />
          </>
        )}

        {tab === 'log' && (
          <div className="panel">
            <div className="panel-h">
              <h3>Decision log</h3>
              <span className="r">{COUNTS.evaluated} checked · hash-chained</span>
            </div>
            <DecisionFeed />
          </div>
        )}

        {tab === 'contract' && <PolicyContract />}
        {tab === 'chain' && <AuditChain />}
      </div>
    </div>
  );
}
