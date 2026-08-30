import { DashboardSidebar } from '@/components/dashboard/DashboardSidebar';
import { DashboardTopbar } from '@/components/dashboard/DashboardTopbar';
import { KpiTiles } from '@/components/dashboard/KpiTiles';
import { SpendChart } from '@/components/dashboard/SpendChart';
import { ConstraintChecks } from '@/components/dashboard/ConstraintChecks';
import { RefusalsByConstraint } from '@/components/dashboard/RefusalsByConstraint';
import { ContainmentGauge } from '@/components/dashboard/ContainmentGauge';
import { AskMandateCard } from '@/components/dashboard/AskMandateCard';
import { DecisionsTable } from '@/components/dashboard/DecisionsTable';

/**
 * The operator console, on the shadcn + Tailwind v2 stack — the "Ledger"
 * direction. Every figure here reads from the same replayed run
 * (`data/policy.ts`, `data/decisions.ts`) the legacy `/` console and the
 * gateway simulator on `/v2` already read, so nothing shown here can drift
 * from what those screens claim.
 *
 * Decisions/Policy contract/Audit chain stay on the sidebar as a visual map of
 * what this console will hold — only Overview is wired up so far.
 */
export default function Dashboard() {
  return (
    <div data-v2 className="flex min-h-screen bg-sheet font-sans text-ink">
      <DashboardSidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <DashboardTopbar />

        <div className="flex flex-col gap-4.5 px-7 py-6">
          <KpiTiles />

          <div className="grid grid-cols-[1.66fr_1fr] gap-3.5">
            <div className="flex min-w-0 flex-col gap-3.5">
              <SpendChart />
              <ConstraintChecks />
            </div>
            <div className="flex min-w-0 flex-col gap-3.5">
              <RefusalsByConstraint />
              <ContainmentGauge />
              <AskMandateCard />
            </div>
          </div>

          <DecisionsTable />
        </div>
      </div>
    </div>
  );
}
