import type { ComponentType } from 'react';
import { Link } from 'react-router-dom';
import { LayoutGrid, ListChecks, FileText, Link2, FlaskConical, Settings, type LucideProps } from 'lucide-react';
import { MANDATE } from '@/data/policy';
import { COUNTS } from '@/data/decisions';
import { cn } from '@/lib/utils';

interface NavItem {
  label: string;
  icon: ComponentType<LucideProps>;
  active?: boolean;
  count?: number;
}

/** Present but inert — the decision log, contract and chain views keep their
 *  existing (legacy-styled) screens for now, so these don't link anywhere yet. */
const NAV: NavItem[] = [
  { label: 'Overview', icon: LayoutGrid, active: true },
  { label: 'Decisions', icon: ListChecks, count: COUNTS.evaluated },
  { label: 'Policy contract', icon: FileText },
  { label: 'Audit chain', icon: Link2 },
  { label: 'Simulator', icon: FlaskConical },
];

export function DashboardSidebar() {
  return (
    <aside className="flex w-[236px] shrink-0 flex-col gap-1 border-r border-rule bg-sheet px-3.5 py-5">
      <Link to="/" className="flex items-center gap-[9px] px-2 pb-5 text-[14.5px] font-semibold tracking-[-0.02em]">
        <svg viewBox="0 0 20 20" fill="none" aria-hidden className="size-[18px] text-indigo">
          <rect x=".75" y=".75" width="18.5" height="18.5" rx="4.5" stroke="currentColor" strokeWidth="1.5" />
          <path d="M5.5 13.5v-7l4.5 4 4.5-4v7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Mandate
      </Link>

      <nav className="flex flex-col gap-[2px]">
        {NAV.map(({ label, icon: Icon, active, count }) => (
          <span
            key={label}
            className={cn(
              'flex items-center gap-[10px] rounded-lg px-3 py-[9px] text-[13px]',
              active ? 'bg-indigo-soft font-medium text-indigo' : 'text-ink-2',
            )}
          >
            <Icon className="size-[17px] shrink-0" strokeWidth={1.6} />
            {label}
            {count != null && <span className="ml-auto font-mono text-[11px] text-ink-3">{count}</span>}
          </span>
        ))}
      </nav>

      <div className="mt-auto flex flex-col gap-[2px]">
        <span className="flex items-center gap-[10px] rounded-lg px-3 py-[9px] text-[13px] text-ink-2">
          <Settings className="size-[17px] shrink-0" strokeWidth={1.6} />
          Settings
        </span>

        <div className="mt-2.5 rounded-panel border border-rule bg-raise px-3.5 py-3">
          <div className="flex items-center gap-[6px]">
            <span className="size-[6px] rounded-full bg-pass" />
            <span className="font-mono text-[11px] font-medium uppercase tracking-[0.04em] text-pass">
              Enforcing
            </span>
          </div>
          <div className="mt-[7px] truncate font-mono text-[11px] text-ink-2">{MANDATE.id}</div>
          <div className="mt-[3px] text-[11px] leading-[1.5] text-ink-3">
            Signed {MANDATE.signedOn} · Ed25519 verified
          </div>
        </div>
      </div>
    </aside>
  );
}
