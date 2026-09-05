import { useCallback, useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { Check, X, Loader2, ShieldCheck, ShieldAlert, Pencil, RotateCcw } from 'lucide-react';

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { API_BASE } from '@/lib/api';
import { LOG_PUBLIC_KEY } from '@/data/log';
import {
  climbToRoot,
  recordHash,
  verifyConsistencyProof,
  verifyTreeHead,
  type ProofNode,
} from '@/lib/merkle';
import { rupees } from '@/lib/money';

/** Money never overshoots, so the settle curve carries every figure and verdict. */
const SETTLE = { duration: 0.32, ease: [0.22, 0.61, 0.36, 1] as const };

/**
 * The earliest head this browser has seen, kept for the append-only check.
 *
 * Module-level rather than component state so it survives the dialog closing, and
 * deliberately not persisted: a head read from storage is a head this page did not
 * witness, and the whole value of an old head is that you watched it go by.
 */
let witnessed: { size: number; root: string } | null = null;

/** One row per sibling, paced like the clause waterfall on /try. */
const ROW_MS = 90;

type StepState = 'pending' | 'pass' | 'fail';

interface Step {
  label: string;
  detail: string;
  value?: string;
  state: StepState;
}

interface Head {
  size: number;
  root: string;
  ts: string;
  sig: string;
}

interface Proof {
  seq: number;
  leaf_record_hash: string;
  tree_size: number;
  root: string;
  proof: ProofNode[];
}

function short(hash: string): string {
  const bare = hash.replace(/^sha256:/, '');
  return `${bare.slice(0, 10)}…${bare.slice(-6)}`;
}

function Row({ step, index }: { step: Step; index: number }) {
  const tone =
    step.state === 'pass' ? 'text-pass' : step.state === 'fail' ? 'text-halt' : 'text-ink-4';
  return (
    <motion.li
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...SETTLE, delay: Math.min(index, 8) * (ROW_MS / 1000) }}
      className={
        'flex items-start gap-3 rounded-md px-2.5 py-2 ' +
        (step.state === 'fail' ? 'bg-halt-soft' : '')
      }
    >
      <span className={`mt-[2px] shrink-0 ${tone}`}>
        {step.state === 'pending' ? (
          <Loader2 className="size-[15px] animate-spin" />
        ) : step.state === 'pass' ? (
          <Check className="size-[15px]" />
        ) : (
          <X className="size-[15px]" />
        )}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-baseline gap-x-2">
          <span className="text-[13px] font-medium text-ink">{step.label}</span>
          {/* Hue never carries meaning alone: the word says it too. */}
          <span className={`text-[11.5px] uppercase tracking-[0.08em] ${tone}`}>
            {step.state === 'pending' ? 'checking' : step.state === 'pass' ? 'holds' : 'broken'}
          </span>
        </span>
        <span className="mt-0.5 block text-[12px] leading-[1.5] text-ink-3">{step.detail}</span>
        {step.value && (
          <span className="mt-1 block overflow-x-auto whitespace-nowrap font-mono text-[11px] text-ink-4">
            {step.value}
          </span>
        )}
      </span>
    </motion.li>
  );
}

export function ReceiptVerifier({
  recordHashRef,
  token,
  open,
  onOpenChange,
}: {
  /** The receipt's own hash. Keyed on this rather than on a row number, because the
   *  console counts rows it displayed and the log counts records it wrote, and a
   *  refusal that never reached the audit makes the two drift apart. */
  recordHashRef: string | null;
  token: string | null;
  open: boolean;
  onOpenChange: (next: boolean) => void;
}) {
  const [steps, setSteps] = useState<Step[]>([]);
  const [verdict, setVerdict] = useState<'pass' | 'fail' | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tampered, setTampered] = useState(false);
  const [record, setRecord] = useState<Record<string, unknown> | null>(null);

  const run = useCallback(
    async (withTamper: boolean) => {
      if (!recordHashRef || !token) return;
      setSteps([]);
      setVerdict(null);
      setError(null);

      const auth = { Authorization: `Bearer ${token}` };
      let head: Head;
      let proof: Proof;
      let body: Record<string, unknown>;
      try {
        const [headRes, auditRes] = await Promise.all([
          fetch(`${API_BASE}/v1/audit/head`, { headers: auth }),
          fetch(`${API_BASE}/v1/audit`, { headers: auth }),
        ]);
        if (headRes.status === 503) {
          setError(
            'This gateway holds no log signing key, so it cannot sign a tree head. ' +
              'There is nothing here to verify against, and saying otherwise would be worse.',
          );
          return;
        }
        if (!headRes.ok || !auditRes.ok) {
          setError('The audit endpoints did not answer. Nothing was checked.');
          return;
        }
        head = await headRes.json();
        const records = (await auditRes.json()).records as Record<string, unknown>[];
        const found = records.find((r) => r.record_hash === recordHashRef);
        if (!found) {
          setError('This decision was refused before it reached the log, so there is no receipt to check.');
          return;
        }
        body = found;
        const proofRes = await fetch(
          `${API_BASE}/v1/audit/proof?seq=${found.seq as number}`,
          { headers: auth },
        );
        if (!proofRes.ok) {
          setError('The log could not produce a proof for this receipt.');
          return;
        }
        proof = await proofRes.json();
      } catch {
        setError('Could not reach the gateway. Nothing was checked.');
        return;
      }

      setRecord(body);
      const collected: Step[] = [];
      const push = (s: Step) => {
        collected.push(s);
        setSteps([...collected]);
      };

      // 1. The head, against a key this page was built with.
      if (!LOG_PUBLIC_KEY) {
        push({
          label: 'Signed tree head',
          detail: 'This build carries no log public key, so the head cannot be checked.',
          state: 'fail',
        });
        setVerdict('fail');
        return;
      }
      const headOk = await verifyTreeHead(head, LOG_PUBLIC_KEY);
      push({
        label: 'Signed tree head',
        detail: headOk
          ? `Signed by the log over ${head.size} record${head.size === 1 ? '' : 's'}, checked against a key this page shipped with, not one the server just sent.`
          : 'The signature does not match the key this page was built with.',
        value: short(head.root),
        state: headOk ? 'pass' : 'fail',
      });
      if (!headOk) {
        setVerdict('fail');
        return;
      }

      // 2. Append-only, against a head this browser watched go by.
      //
      // A different claim from the one above and the stronger one: an inclusion
      // proof says the receipt is in the log now, which a log that quietly rewrote
      // itself could still satisfy. Only this says nothing was dropped or reordered
      // since a head somebody already holds. Skipped on the first look, because
      // there is nothing yet to compare against and a tick nobody earned is worse
      // than a row that is absent.
      if (witnessed && witnessed.size < head.size) {
        const since = witnessed;
        try {
          const res = await fetch(
            `${API_BASE}/v1/audit/consistency?from=${since.size}&to=${head.size}`,
            { headers: auth },
          );
          if (res.ok) {
            const c = await res.json();
            const ok = await verifyConsistencyProof(
              since.size, head.size, since.root, head.root, c.proof ?? [],
            );
            push({
              label: 'Nothing was rewritten',
              detail: ok
                ? `The log has grown from ${since.size} to ${head.size} record${head.size === 1 ? '' : 's'} since this page first looked, and everything it held then is still there, in the same order.`
                : 'The log no longer extends the version this page saw earlier. Something before this point changed.',
              value: short(since.root),
              state: ok ? 'pass' : 'fail',
            });
            if (!ok) {
              setVerdict('fail');
              return;
            }
          }
        } catch {
          // A missing consistency endpoint is not a failed check, so nothing is
          // claimed either way.
        }
      }
      if (!witnessed) witnessed = { size: head.size, root: head.root };


      // 3. The receipt's own hash, recomputed here.
      const shown = withTamper
        ? { ...body, action: { ...(body.action as Record<string, unknown>), amount: 1 } }
        : body;
      const computed = await recordHash(shown);
      const leafMatches = computed === proof.leaf_record_hash;
      push({
        label: withTamper ? 'Receipt hash, after editing the amount' : 'Receipt hash',
        detail: leafMatches
          ? 'Recomputed in this browser from the record itself, and it matches the leaf the log published.'
          : 'Recomputed here and it no longer matches the leaf the log published. One edited field changes the hash.',
        value: short(computed),
        state: leafMatches ? 'pass' : 'fail',
      });

      // 4. Walk leaf to root. `climbToRoot` is the same function `verifyInclusionProof`
      //    uses, so the page cannot narrate one walk while the verifier does another.
      const climb = await climbToRoot(computed, proof.seq - 1, proof.tree_size, proof.proof);
      for (const step of climb.steps) {
        push({
          label: 'Combined with its neighbour',
          detail: `Hashed together with ${short(step.sibling)}, which stands for everything on its ${step.side}, to climb one level.`,
          value: short(step.result),
          state: 'pass',
        });
      }

      // 5. Does the climb land on the head the log signed?
      const rootOk = climb.complete && climb.root === head.root;
      push({
        label: 'Reaches the signed root',
        detail: rootOk
          ? 'The climb lands exactly on the root the log signed, so this receipt is in that log and has not been altered.'
          : 'The climb does not land on the signed root. This receipt is not the one the log published.',
        value: short(climb.root),
        state: rootOk ? 'pass' : 'fail',
      });
      setVerdict(rootOk ? 'pass' : 'fail');
    },
    [recordHashRef, token],
  );

  useEffect(() => {
    if (open) {
      setTampered(false);
      void run(false);
    }
  }, [open, run]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Check this receipt yourself</DialogTitle>
          <DialogDescription>
            Every step below runs in your browser. The gateway hands over the proof and its
            signed head; it is never asked whether they are good.
          </DialogDescription>
        </DialogHeader>

        {error ? (
          <p className="mt-5 rounded-panel border border-rule bg-sunk p-4 text-[13px] leading-[1.55] text-ink-2">
            {error}
          </p>
        ) : (
          <>
            <ul className="mt-5 space-y-0.5">
              {steps.map((s, i) => (
                <Row key={`${s.label}-${i}`} step={s} index={i} />
              ))}
            </ul>

            {verdict && (
              <motion.div
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={SETTLE}
                className={
                  'mt-5 flex items-start gap-3 rounded-panel border p-4 ' +
                  (verdict === 'pass'
                    ? 'border-pass-line bg-pass-soft'
                    : 'border-halt-line bg-halt-soft')
                }
              >
                <span className={verdict === 'pass' ? 'text-pass' : 'text-halt'}>
                  {verdict === 'pass' ? (
                    <ShieldCheck className="size-[18px]" />
                  ) : (
                    <ShieldAlert className="size-[18px]" />
                  )}
                </span>
                <p className="text-[13px] leading-[1.55] text-ink">
                  {verdict === 'pass' ? (
                    <>
                      <strong className="font-medium">Verified.</strong> This receipt is in the
                      gateway's log, in this position, unchanged.
                    </>
                  ) : (
                    <>
                      <strong className="font-medium">Does not verify.</strong>{' '}
                      {tampered
                        ? 'Which is the point: one edited paisa and the proof stops reaching the root.'
                        : 'The receipt and the published log disagree.'}
                    </>
                  )}
                </p>
              </motion.div>
            )}

            {record && (
              <div className="mt-5 flex flex-wrap gap-2 border-t border-rule-soft pt-4">
                <Button
                  size="sm"
                  variant="outline"
                  className="h-[34px] rounded-lg text-[12.5px]"
                  onClick={() => {
                    setTampered(true);
                    void run(true);
                  }}
                  disabled={tampered}
                >
                  <Pencil className="mr-1.5 size-3.5" />
                  Change the amount to {rupees(1)}
                </Button>
                {tampered && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="h-[34px] rounded-lg text-[12.5px]"
                    onClick={() => {
                      setTampered(false);
                      void run(false);
                    }}
                  >
                    <RotateCcw className="mr-1.5 size-3.5" />
                    Put it back
                  </Button>
                )}
              </div>
            )}
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
