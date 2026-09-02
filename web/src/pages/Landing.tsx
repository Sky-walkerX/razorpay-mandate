import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { MandateLockup } from '@/components/brand/MandateLockup';
import ProblemHero from '@/components/v2/ProblemHero';
import GapAndParts from '@/components/v2/GapAndParts';
import FailureModes from '@/components/v2/FailureModes';
import HowItHolds from '@/components/v2/HowItHolds';

/**
 * The default Mandate homepage on the shadcn + Motion stack.
 */
export default function Landing() {
  return (
    <div data-v2 className="min-h-screen bg-bond font-sans text-ink">
      <nav className="sticky top-0 z-50 border-b border-rule bg-bond/85 backdrop-blur-[12px]">
        <div className="mx-auto flex h-[60px] max-w-[1220px] items-center gap-[26px] px-8 max-sm:px-[18px]">
          <Link to="/" aria-label="Mandate, by Razorpay">
            <MandateLockup />
          </Link>
          <div className="ml-3 hidden gap-[22px] text-[13.5px] text-ink-2 lg:flex">
            <a href="#gap" className="transition-colors hover:text-ink">The gap</a>
            <a href="#modes" className="transition-colors hover:text-ink">Failure modes</a>
            <a href="#how" className="transition-colors hover:text-ink">How it holds</a>
            <a href="#limits" className="transition-colors hover:text-ink">Your limits</a>
            <Link to="/rails" className="transition-colors hover:text-ink">Rails &amp; regulation</Link>
            <Link to="/pitch" className="transition-colors hover:text-ink font-medium text-[#2F5EFF]">Pitch Deck</Link>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden items-center gap-[7px] rounded-full border border-rule bg-sheet py-[5px] pl-[9px] pr-[11px] font-mono text-[10.5px] uppercase tracking-[0.07em] text-ink-2 sm:inline-flex">
              <span className="size-[5px] rounded-full bg-emerald-500 animate-pulse" />
              Enforcement · No Model Call
            </span>
            <Button asChild variant="outline" size="sm" className="h-[38px] rounded-lg px-3.5 text-[13px]">
              <Link to="/dashboard">Replay</Link>
            </Button>
            <Button asChild size="sm" className="h-[38px] rounded-lg bg-[#2F5EFF] hover:bg-[#254ED0] text-white px-4 text-[13.5px] shadow-2xs">
              <Link to="/try">Try it live →</Link>
            </Button>
          </div>
        </div>
      </nav>

      <ProblemHero />

      <GapAndParts />

      <FailureModes />

      <HowItHolds />

      <footer className="mx-auto flex max-w-[1220px] flex-wrap justify-between items-center gap-4 px-8 py-7 text-[12.5px] text-ink-3 max-sm:px-[18px]">
        <span>Mandate · Autonomous Agent Payment Guardrails</span>
        <span>Seller marks are drawn approximations, not official brand assets.</span>
      </footer>
    </div>
  );
}
