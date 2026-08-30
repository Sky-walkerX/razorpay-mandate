import { useCallback, useEffect, useRef, useState } from 'react';
import { LIMITS, PARTS, RULES } from '../data/policy';
import { SCENARIOS } from '../data/scenarios';
import { rupees } from '../lib/money';

type RowState = '' | 'allow' | 'deny' | 'unknown' | 'skip';

const REDUCED =
  typeof window !== 'undefined' &&
  window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/** The rating mark sits at 62% of the track, leaving room to overshoot. */
const MARK = 62;

function rowWord(kind: 'limit' | 'rule', state: RowState): string {
  if (state === 'allow') return kind === 'limit' ? 'under limit' : 'matches';
  if (state === 'deny') return kind === 'limit' ? 'over limit' : 'no match';
  if (state === 'unknown') return 'unresolved';
  if (state === 'skip') return 'not checked';
  return 'idle';
}

const VERDICT_WORD: Record<string, string> = {
  allow: 'ALLOWED',
  deny: 'REFUSED',
  unknown: 'NEEDS YOU',
};

/**
 * The gateway, running. Nine parts evaluate in order against one proposed
 * order: five limits carry a load against a number, four rules take a match.
 * The first part to fail stops the evaluation, names its clause, and leaves
 * everything after it unchecked — which is the whole argument, made visible
 * rather than asserted.
 */
export default function GatewayPanel() {
  const [active, setActive] = useState(0);
  const [states, setStates] = useState<RowState[]>(() => PARTS.map(() => ''));
  const [loads, setLoads] = useState<number[]>(() => LIMITS.map(() => 0));
  const [settled, setSettled] = useState(false);
  const timers = useRef<number[]>([]);
  const panelRef = useRef<HTMLDivElement>(null);
  const started = useRef(false);

  const sc = SCENARIOS[active];

  const clear = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };

  const run = useCallback((index: number) => {
    clear();
    const s = SCENARIOS[index];
    setActive(index);
    setSettled(false);
    setStates(PARTS.map(() => ''));
    setLoads(LIMITS.map(() => 0));

    const last = s.stopsAt < 0 ? PARTS.length - 1 : s.stopsAt;
    const step = REDUCED ? 0 : 120;

    PARTS.forEach((part, i) => {
      timers.current.push(
        window.setTimeout(() => {
          if (part.kind === 'limit' && i <= last) {
            setLoads((prev) => {
              const next = [...prev];
              next[i] = s.load[i];
              return next;
            });
          }
          setStates((prev) => {
            const next = [...prev];
            if (s.stopsAt >= 0 && i > last) next[i] = 'skip';
            else if (s.stopsAt >= 0 && i === s.stopsAt) next[i] = s.verdict;
            else next[i] = 'allow';
            return next;
          });
        }, step * (i + 1)),
      );
    });

    timers.current.push(
      window.setTimeout(() => setSettled(true), step * (PARTS.length + 1)),
    );
  }, []);

  // Runs when the panel is first seen, so the mechanism is in motion at the
  // moment someone looks at it rather than already over.
  useEffect(() => {
    const el = panelRef.current;
    const begin = () => {
      if (started.current) return;
      started.current = true;
      run(0);
    };
    if (!el || REDUCED || !('IntersectionObserver' in window)) {
      begin();
      return clear;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          window.setTimeout(begin, 380);
          io.disconnect();
        }
      },
      { threshold: 0.25 },
    );
    io.observe(el);
    const safety = window.setTimeout(begin, 1600);
    return () => {
      io.disconnect();
      window.clearTimeout(safety);
      clear();
    };
  }, [run]);

  const renderRow = (part: (typeof PARTS)[number]) => {
    const i = PARTS.indexOf(part);
    const state = states[i];
    const isStop = settled && sc.stopsAt === i;
    return (
      <li key={part.key}>
        <div className="row" data-v={state}>
          <span className="ref">{part.n}</span>
          <span className="nm">{part.label}</span>
          <span className="mid">
            {part.kind === 'limit' ? (
              <>
                <span className="track">
                  <span
                    className="fill"
                    style={{ width: `${Math.min(loads[i] ?? 0, 1.55) * MARK}%` }}
                  />
                  <span className="mk" />
                </span>
                <span className="rate">{part.bound}</span>
              </>
            ) : (
              <span className="keyv">{part.bound}</span>
            )}
          </span>
          <span className="vd">
            <s />
            {rowWord(part.kind, state)}
          </span>
        </div>
        {isStop && (
          <div className="clause open" data-v={sc.verdict}>
            <div className="clause-in">
              <span className="lab">
                Part {part.n} · {sc.verdict === 'unknown' ? 'needs your decision' : 'the limit it broke'}
              </span>
              {sc.clause}
              <br />
              <span className="actual">{sc.actual}</span>
            </div>
          </div>
        )}
      </li>
    );
  };

  return (
    <div className="sheet" ref={panelRef}>
      <div className="sheet-bar">
        <span className="t">Gateway · nine parts</span>
        <span className="r">
          <span className="pulse" />
          enforcing
        </span>
      </div>

      <div className="scen" role="tablist" aria-label="Order under test">
        {SCENARIOS.map((s, i) => (
          <button
            key={s.id}
            role="tab"
            aria-selected={i === active}
            onClick={() => run(i)}
            type="button"
          >
            <span className="k">{s.id}</span>
            <span className="n">{s.tab}</span>
          </button>
        ))}
      </div>

      <div className="action">
        <div className="action-h">
          <span className="call">{sc.call}</span>
          <span className="via">via {sc.seller}</span>
          <span className="amt">{rupees(sc.amountPaise)}</span>
        </div>
        <div className="payload">
          {sc.payload.map((seg, i) => (
            <span key={i} className={seg.hostile ? 'inj' : seg.dim ? 'dim' : undefined}>
              {seg.text}
            </span>
          ))}
        </div>
      </div>

      <div className="bank">
        <span className="t">Limits</span>
        <span className="s">a number this order has to stay under</span>
        <span className="c">{LIMITS.length}</span>
      </div>
      <ul className="rows">{LIMITS.map(renderRow)}</ul>

      <div className="bank">
        <span className="t">Rules</span>
        <span className="s">a list or a date this order has to match</span>
        <span className="c">{RULES.length}</span>
      </div>
      <ul className="rows">{RULES.map(renderRow)}</ul>

      <div className="verdict" data-v={settled ? sc.verdict : ''}>
        <span className="w">{settled ? VERDICT_WORD[sc.verdict] : 'checking'}</span>
        <span className="sub">{settled ? sc.summary : 'nine parts, in order'}</span>
        <button
          className="replay"
          type="button"
          onClick={() => run(active)}
          title="Run this order again"
          aria-label="Run this order again"
        >
          <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M13.5 8a5.5 5.5 0 1 1-1.7-3.97M13 2v3h-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        <span className="rt">
          {settled && (
            <>
              <b>{sc.ms} ms</b>
              {sc.movedPaise > 0 ? `paid ${rupees(sc.movedPaise)}` : 'no money moved'}
            </>
          )}
        </span>
      </div>
    </div>
  );
}
