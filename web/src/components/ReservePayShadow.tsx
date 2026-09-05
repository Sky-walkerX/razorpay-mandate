import { cn } from '@/lib/utils';
import { rupees } from '@/lib/money';

/**
 * What UPI Reserve Pay would have done with the same basket.
 *
 * Razorpay already ships spending limits for agents on Reserve Pay, so "we cap
 * what an agent can spend" is not a claim worth making on this page. The claim
 * is shape. A block names one payee and one total, so it reads two ways at once:
 * it lets an attack through that the mandate refuses, and it refuses a
 * legitimate order at a second shop that the mandate allows.
 *
 * Both directions are shown. Reporting only the first would overstate the rail,
 * which is the failure `mandate/policy/rails.py` exists to avoid, and a judge
 * who built Reserve Pay would spot a missing payee constraint immediately.
 */
export interface ReservePayVerdict {
  verdict: 'ALLOW' | 'DENY' | 'UNKNOWN';
  clause_id?: string | null;
  message?: string | null;
  executed: boolean;
  payee: string | null;
  block_paise: number;
  spent_paise: number;
  clauses_kept: string[];
}

function shopName(payee: string | null): string {
  if (!payee) return 'one shop';
  return payee.charAt(0).toUpperCase() + payee.slice(1);
}

export function ReservePayShadow({
  shadow,
  mandateAllowed,
  amountPaise,
}: {
  shadow: ReservePayVerdict;
  mandateAllowed: boolean;
  amountPaise: number;
}) {
  const railAllowed = shadow.verdict === 'ALLOW';
  // The two cases worth a judge's attention are the disagreements. Agreement is
  // still shown, quietly, so the panel never looks like it only speaks up when
  // the comparison flatters us.
  const differs = railAllowed !== mandateAllowed;
  const railWorse = railAllowed && !mandateAllowed;

  return (
    <div
      className={cn(
        'flex flex-wrap items-center gap-[9px] border-b px-[22px] py-[11px]',
        differs ? 'border-refer-line bg-refer-soft' : 'border-hair bg-sheet',
      )}
    >
      <span className="whitespace-nowrap rounded-full border border-rule bg-bond px-[9px] py-[2px] text-[11px] font-medium text-ink-2">
        UPI Reserve Pay
      </span>

      <span className="text-[12.5px] leading-[1.5] text-ink-2">
        {railWorse ? (
          <>
            would have <b className="font-semibold text-halt">let this through</b>. A block never
            sees categories, quantities or per-order limits, only {rupees(shadow.block_paise)}{' '}
            against {shopName(shadow.payee)}.
          </>
        ) : differs ? (
          <>
            would have <b className="font-semibold text-halt">refused it</b>. A block names one
            payee, and this order was not with {shopName(shadow.payee)}.
          </>
        ) : railAllowed ? (
          <>would have allowed it too. The rail and your limits agree here.</>
        ) : (
          <>
            would have refused it as well, on {rupees(shadow.block_paise)} against{' '}
            {shopName(shadow.payee)}.
          </>
        )}
      </span>

      <span className="ml-auto whitespace-nowrap text-[11.5px] text-ink-3">
        {shadow.clauses_kept.length} of your limits fit on the rail
      </span>

      {railWorse && (
        <span className="w-full font-mono text-[11.5px] text-ink-3">
          {rupees(amountPaise)} would have left your account.
        </span>
      )}
    </div>
  );
}
