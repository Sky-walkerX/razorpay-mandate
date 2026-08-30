import { Link } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import HeroScrollStage from '@/components/v2/HeroScrollStage';
import IntentScored from '@/components/v2/IntentScored';
import FailureModes from '@/components/v2/FailureModes';
import HowItHolds from '@/components/v2/HowItHolds';
import YourLimitsGrid from '@/components/v2/YourLimitsGrid';

/**
 * The default Mandate homepage on the shadcn + Motion stack.
 */
export default function Landing() {
  return (
    <div data-v2 className="min-h-screen bg-bond font-sans text-ink">
      <nav className="sticky top-0 z-50 border-b border-rule bg-bond/85 backdrop-blur-[12px]">
        <div className="mx-auto flex h-[60px] max-w-[1220px] items-center gap-[26px] px-8 max-sm:px-[18px]">
          <Link to="/" className="flex items-center gap-[9px] text-[16.5px] font-semibold tracking-[-0.04em]">
            <svg viewBox="0 0 20 20" fill="none" aria-hidden className="size-[19px]">
              <rect x=".75" y=".75" width="18.5" height="18.5" rx="4.5" stroke="currentColor" strokeWidth="1.5" />
              <path d="M5.5 13.5v-7l4.5 4 4.5-4v7" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Mandate
          </Link>
          <div className="ml-3 hidden gap-[22px] text-[13.5px] text-ink-2 lg:flex">
            <a href="#gap" className="transition-colors hover:text-ink">The gap</a>
            <a href="#modes" className="transition-colors hover:text-ink">Failure modes</a>
            <a href="#how" className="transition-colors hover:text-ink">How it holds</a>
            <a href="#limits" className="transition-colors hover:text-ink">Your limits</a>
            <Link to="/pitch" className="transition-colors hover:text-ink font-medium text-[#2F5EFF]">Pitch Deck</Link>
          </div>
          <div className="ml-auto flex items-center gap-3">
            <span className="hidden items-center gap-[7px] rounded-full border border-rule bg-sheet py-[5px] pl-[9px] pr-[11px] font-mono text-[10.5px] uppercase tracking-[0.07em] text-ink-2 sm:inline-flex">
              <span className="size-[5px] rounded-full bg-emerald-500 animate-pulse" />
              0.2ms Gateway · Deterministic
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

      <HeroScrollStage />

      <section id="gap" className="border-b border-rule">
        <div className="mx-auto max-w-[1220px] px-8 py-[88px] max-sm:px-[18px] max-md:py-14">
          <div className="max-w-[38rem]">
            <h2 className="text-balance text-[clamp(1.75rem,3.2vw,2.35rem)] font-semibold leading-[1.05] tracking-[-0.04em]">
              The payment rail holds three things. People mean considerably more.
            </h2>
            <p className="mt-[14px] text-[16.5px] leading-[1.62] text-ink-2">
              UPI Reserve Pay knows a total cap, a seller and an expiry. AP2&rsquo;s Intent Mandate
              lands in the same place. Everything meant beyond those three has been living in a
              system prompt — which makes the control protecting your money a language model&rsquo;s
              willingness to keep remembering an instruction while an attacker writes into its
              context.
            </p>
          </div>

          <div className="mt-[46px]">
            <IntentScored />
          </div>

          <div className="mt-[26px] grid gap-4 md:grid-cols-2">
            <blockquote className="rounded-xl border border-rule bg-sheet p-[22px]">
              <p className="text-[16px] leading-[1.5] tracking-[-0.022em]">
                &ldquo;Order my usual groceries before the match, under ₹2,000.&rdquo;
              </p>
              <cite className="mt-[11px] block text-[13px] not-italic leading-[1.6] text-ink-3">
                Carries a dozen unstated conditions. Nothing alcoholic. Don&rsquo;t swap the ₹80 dal
                for the ₹400 organic one. Not the seller who sent rotten produce. One order, not five.
              </cite>
            </blockquote>
            <blockquote className="rounded-xl border border-rule bg-sheet p-[22px]">
              <p className="text-[16px] leading-[1.5] tracking-[-0.022em]">
                A shopping agent holds a private mandate, reads untrusted seller-controlled text, and
                can move money.
              </p>
              <cite className="mt-[11px] block text-[13px] not-italic leading-[1.6] text-ink-3">
                All three at once, by construction. You cannot remove any one of them without
                removing the product.
              </cite>
            </blockquote>
          </div>
        </div>
      </section>

      <FailureModes />

      <HowItHolds />

      <YourLimitsGrid />

      <footer className="mx-auto flex max-w-[1220px] flex-wrap justify-between items-center gap-4 px-8 py-7 text-[12.5px] text-ink-3 max-sm:px-[18px]">
        <span>Mandate · Autonomous Agent Payment Guardrails</span>
        <span>Seller marks are drawn approximations, not official brand assets.</span>
      </footer>
    </div>
  );
}
