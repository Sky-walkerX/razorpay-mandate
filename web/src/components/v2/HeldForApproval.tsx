import { useCallback, useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { QRCodeSVG } from 'qrcode.react';
import { Smartphone, Check, Loader2, ShieldQuestion } from 'lucide-react';

import { cn } from '@/lib/utils';

/**
 * An order the gateway will not execute and has not refused.
 *
 * `afa.required` is the only clause that answers UNKNOWN. The order is not
 * forbidden, it is unauthorised so far, and the way out is a person rather than a
 * different basket. RBI requires the step above Rs 15,000 and neither AP2 nor
 * Reserve Pay can carry it, so this is the gateway holding something the rails
 * cannot.
 *
 * **The QR is the point, not decoration.** Approving on the same screen that placed
 * the order would prove nothing: the whole claim is that the credential which
 * spends and the credential which approves are different, and the clearest way to
 * show that is to make the second one arrive on a different device. The ref in the
 * URL is the capability for this one order and nothing else.
 *
 * The agent never sees this ref. The page holds it because it asked `/v1/pending`
 * with the principal's key, which no agent-facing surface accepts.
 */

const EASE = [0.22, 0.61, 0.36, 1] as const;

const rupees = (paise: number) =>
  `₹${(paise / 100).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

export interface HeldItem {
  ref: string;
  amount: number;
  threshold: number;
  status: 'pending' | 'approved' | 'rejected' | 'expired';
}

export function HeldForApproval({
  item,
  apiBase,
  principalKey,
  onApproved,
}: {
  item: HeldItem;
  apiBase: string;
  principalKey: string | null;
  onApproved: () => void;
}) {
  const [status, setStatus] = useState(item.status);
  const [working, setWorking] = useState(false);

  const url = `${window.location.origin}/approve/${item.ref}`;

  // Poll, because the approval arrives on a device this page cannot hear from.
  // Stops as soon as it is no longer pending; a resolved approval never reverts.
  const poll = useCallback(async () => {
    try {
      const res = await fetch(`${apiBase}/v1/approve/${item.ref}`);
      if (!res.ok) return;
      const body = await res.json();
      if (body.status && body.status !== 'pending') {
        setStatus(body.status);
        if (body.status === 'approved') onApproved();
      }
    } catch {
      // A dropped poll is not an outcome. The next tick asks again.
    }
  }, [apiBase, item.ref, onApproved]);

  useEffect(() => {
    if (status !== 'pending') return;
    const id = setInterval(poll, 2000);
    return () => clearInterval(id);
  }, [poll, status]);

  const approveHere = async () => {
    setWorking(true);
    try {
      const res = await fetch(`${apiBase}/v1/approve`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(principalKey ? { 'X-Principal-Key': principalKey } : {}),
        },
        body: JSON.stringify({ ref: item.ref, decision: 'approve' }),
      });
      if (res.ok) {
        setStatus('approved');
        onApproved();
      }
    } finally {
      setWorking(false);
    }
  };

  const approved = status === 'approved';

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, ease: EASE }}
      className={cn(
        'mt-4 overflow-hidden rounded-panel border',
        approved ? 'border-pass-line bg-pass-soft' : 'border-refer-line bg-refer-soft',
      )}
    >
      <div className="flex items-start gap-3 border-b border-rule-soft px-5 py-[11px]">
        <span className={approved ? 'text-pass' : 'text-refer'}>
          {approved ? <Check className="size-[17px]" /> : <ShieldQuestion className="size-[17px]" />}
        </span>
        <div className="min-w-0">
          <p className="text-[13.5px] font-semibold text-ink">
            {approved ? 'Approved. The agent can place it now.' : 'Waiting for you to approve it'}
          </p>
          <p className="mt-[2px] text-[12.5px] leading-[1.5] text-ink-2">
            {approved ? (
              <>You released this one basket. A different basket of the same value still stops here.</>
            ) : (
              <>
                {rupees(item.amount)} is over the {rupees(item.threshold)} the law says needs a
                second yes from you. The gateway has not refused it. It is holding it.
              </>
            )}
          </p>
        </div>
      </div>

      {!approved && (
        <div className="flex flex-wrap items-center gap-5 px-5 py-4">
          <div className="rounded-lg bg-bond p-2">
            <QRCodeSVG value={url} size={104} level="M" />
          </div>
          <div className="min-w-[200px] flex-1">
            <p className="flex items-center gap-1.5 text-[12.5px] font-medium text-ink">
              <Smartphone className="size-3.5" />
              Scan it with your phone
            </p>
            <p className="mt-1 text-[12px] leading-[1.5] text-ink-3">
              The agent cannot reach this page and was never given the link. Its own token is
              refused here, which is the whole point of there being two credentials.
            </p>
            <button
              onClick={approveHere}
              disabled={working}
              className={cn(
                'mt-3 inline-flex h-[32px] items-center gap-1.5 rounded-lg border border-rule',
                'bg-bond px-3 text-[12.5px] font-medium text-ink transition-colors',
                'hover:bg-sheet disabled:opacity-60',
              )}
            >
              {working ? <Loader2 className="size-3.5 animate-spin" /> : <Check className="size-3.5" />}
              Or approve it here
            </button>
          </div>
        </div>
      )}
    </motion.div>
  );
}
