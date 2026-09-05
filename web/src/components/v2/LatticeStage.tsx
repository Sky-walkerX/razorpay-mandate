import { QRCodeSVG } from 'qrcode.react';
import { Check, Lock, X } from 'lucide-react';
import { partByKey } from '@/data/policy';
import { cn } from '@/lib/utils';

/**
 * What the selected gate actually does, beside the lattice that selects it.
 *
 * The lattice has had three clickable gates and a `selectedVerdict` since it was
 * built, and selecting one changed a ring and nothing else. The middle gate in
 * particular claimed that anything unresolved "triggers human approval" while
 * the product showed that approval nowhere.
 *
 * The unknown pane is the one that earns this component. It names both halves of
 * the credential split, because only naming the friendly half ("you approve on
 * your phone") leaves out the property that makes it worth anything: the agent
 * cannot approve its own escalation. Both directions are asserted in
 * `tests/service/test_afa_loop_end_to_end.py`, so the copy is describing a tested
 * invariant rather than an intention.
 *
 * The QR is a real code for the real `/approve` page rather than a drawn
 * lookalike. A picture of a QR on a page whose whole argument is "check it
 * yourself" would be the wrong kind of prop.
 */

const AFA = partByKey('afa.required');
const PER_ITEM = partByKey('budget.per_item');

export type StageVerdict = 'deny' | 'unknown' | 'allow';

function Row({
  children,
  value,
  tone,
}: {
  children: string;
  value: string;
  tone?: 'pass' | 'halt';
}) {
  return (
    <div className="flex items-center gap-2 border-b border-hair px-[11px] py-2 text-[11.5px] last:border-b-0">
      <span className="text-ink-3">{children}</span>
      <span
        className={cn(
          'ml-auto font-mono font-semibold tabular-nums',
          tone === 'pass' && 'text-pass',
          tone === 'halt' && 'text-halt',
        )}
      >
        {value}
      </span>
    </div>
  );
}

export default function LatticeStage({ verdict }: { verdict: StageVerdict }) {
  return (
    <div className="rounded-panel border border-rule bg-sheet p-[18px]">
      <div className="font-mono text-[10px] uppercase tracking-[0.1em] text-ink-3">
        What happens
      </div>

      {verdict === 'deny' && (
        <>
          <div className="mt-2.5 text-[15px] font-semibold tracking-[-0.02em]">
            Nothing moves, and you are told why.
          </div>
          <p className="mt-1.5 max-w-[42ch] text-[12.5px] leading-[1.55] text-ink-2">
            The refusal names one limit in plain words. The agent gets that name and nothing
            else, which is enough for it to try a smaller basket.
          </p>
          <div className="mt-[15px] max-w-[340px] overflow-hidden rounded-[10px] border border-rule bg-bond">
            <Row value="₹690.20" tone="halt">
              {PER_ITEM?.label ?? 'the limit that stopped it'}
            </Row>
            <Row value={PER_ITEM?.bound ?? ''}>your limit</Row>
            <Row value="₹0.00">moved to the shop</Row>
          </div>
        </>
      )}

      {verdict === 'unknown' && (
        <>
          <div className="mt-2.5 text-[15px] font-semibold tracking-[-0.02em]">
            It waits on your phone, not in the agent&rsquo;s hands.
          </div>
          <p className="mt-1.5 max-w-[42ch] text-[12.5px] leading-[1.55] text-ink-2">
            The order is held and a request goes to you. Scan the code or open the alert on any
            device. The agent never sees the approval, and the thing that approves cannot spend.
          </p>

          <div className="mt-[15px] grid items-center gap-[18px] max-[620px]:grid-cols-1 min-[621px]:grid-cols-[auto_1fr]">
            <div>
              <div className="rounded-[10px] border border-rule bg-bond p-[7px]">
                <QRCodeSVG value="https://mandate.namankhandelwal.dev/approve" size={92} level="M" />
              </div>
              <div className="mt-[7px] text-center font-mono text-[8.5px] uppercase tracking-[0.08em] text-ink-3">
                scan to approve
              </div>
            </div>

            <div className="grid gap-[7px]">
              <div className="flex items-start gap-2 text-[12px] leading-[1.45] text-ink-2">
                <span className="flex-shrink-0 rounded-full border border-refer-line bg-refer-soft px-[7px] py-[3px] font-mono text-[9px] font-semibold tracking-[0.09em] text-refer">
                  HELD
                </span>
                <span>
                  Over the {AFA?.bound.replace(/\.00$/, '')} line, so it stops here rather than
                  going through.
                </span>
              </div>
              <div className="flex items-start gap-2 text-[12px] leading-[1.45] text-ink-2">
                <Check className="mt-[2px] size-3 flex-shrink-0 text-pass" strokeWidth={2.6} />
                <span>
                  <b className="font-semibold text-ink">Your key approves</b> and cannot spend a
                  rupee.
                </span>
              </div>
              <div className="flex items-start gap-2 text-[12px] leading-[1.45] text-ink-2">
                <X className="mt-[2px] size-3 flex-shrink-0 text-halt" strokeWidth={2.6} />
                <span>
                  <b className="font-semibold text-ink">The agent&rsquo;s key spends</b> and cannot
                  approve anything, including its own order.
                </span>
              </div>
              <div className="flex items-start gap-2 text-[12px] leading-[1.45] text-ink-2">
                <span className="mt-[1px] flex-shrink-0 text-ink-4">&middot;</span>
                <span>
                  Approving this basket releases this basket only. Another of the same value
                  stays held.
                </span>
              </div>
            </div>
          </div>
        </>
      )}

      {verdict === 'allow' && (
        <>
          <div className="mt-2.5 text-[15px] font-semibold tracking-[-0.02em]">
            The checked figure is the figure that is charged.
          </div>
          <p className="mt-1.5 max-w-[42ch] text-[12.5px] leading-[1.55] text-ink-2">
            The amount that passed every limit is the amount sent to the payment network. If what
            settles differs, the order is pulled back and the record says so.
          </p>
          <div className="mt-[15px] max-w-[340px] overflow-hidden rounded-[10px] border border-rule bg-bond">
            <Row value="₹431.00" tone="pass">
              every limit passed
            </Row>
            <Row value="₹431.00">sent to the network</Row>
            <div className="flex items-center gap-2 px-[11px] py-2">
              <span className="text-[11px] text-ink-3">receipt written</span>
              <span className="ml-auto inline-flex items-center gap-[6px] rounded-lg border border-rule bg-bond px-[9px] py-1 font-mono text-[11px] font-medium text-ink-2">
                <Lock className="size-[10px] text-ink-3" strokeWidth={2} />
                Verify
              </span>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
