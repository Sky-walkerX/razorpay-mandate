import { Link } from 'react-router-dom';
import { Download, FlaskConical } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { FEED_RUN } from '@/data/decisions';

export function DashboardTopbar() {
  return (
    <div className="flex h-16 shrink-0 items-center gap-3.5 border-b border-rule bg-bond px-7">
      <span className="text-[15px] font-semibold tracking-[-0.02em]">Overview</span>
      <span className="rounded-md bg-sunk px-2 py-[3px] font-mono text-[11px] text-ink-2">{FEED_RUN}</span>
      <span className="text-[11.5px] text-ink-3">Recorded run · test mode</span>

      <div className="ml-auto flex items-center gap-2.5">
        <Button variant="outline" size="sm" className="gap-[7px] text-[12.5px]">
          <Download className="size-[14px]" />
          Export evidence
        </Button>
        <Button asChild size="sm" className="gap-[7px] text-[12.5px]">
          <Link to="/v2">
            <FlaskConical className="size-[14px]" />
            Run simulator
          </Link>
        </Button>
      </div>
    </div>
  );
}
