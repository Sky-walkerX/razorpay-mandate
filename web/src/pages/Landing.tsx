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
          {/* Two real pages, and every label pinned with `whitespace-nowrap`.
              This row carried six links, a badge and two buttons inside 1220px
              with nothing stopping a label from breaking, so four of them wrapped
              onto a second line and the bar grew past its own 60px. The four that
              went — The gap, Failure modes, How it holds, Your limits — all
              scrolled to sections of this same page, which a visitor reaches by
              scrolling anyway. */}
          <div className="ml-3 hidden gap-[22px] text-[13.5px] text-ink-2 lg:flex">
            <Link to="/rails" className="whitespace-nowrap transition-colors hover:text-ink">Rails &amp; regulation</Link>
            <Link to="/pitch" className="whitespace-nowrap font-medium text-[#2F5EFF] transition-colors hover:text-ink">Pitch deck</Link>
          </div>
          <div className="ml-auto flex items-center gap-3">
            {/* "Enforcement · No Model Call" named the mechanism to someone who
                already knew the product. The claim worth making is that an AI
                picks the basket and plain code decides whether it may be paid
                for, so that is what it now says. */}
            <span className="hidden items-center gap-[7px] whitespace-nowrap rounded-full border border-rule bg-sheet py-[5px] pl-[10px] pr-[13px] text-[12px] text-ink-2 sm:inline-flex">
              <span className="size-[5px] rounded-full bg-emerald-500 animate-pulse" />
              Approvals run without AI
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
