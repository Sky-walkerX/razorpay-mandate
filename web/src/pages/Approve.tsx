import { useCallback, useEffect, useState } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { QRCodeSVG } from 'qrcode.react';
import {
  ShieldCheck,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Clock,
  ArrowLeft,
  QrCode,
  Copy,
  Check,
  Smartphone,
  ExternalLink,
  Shield,
  FileCheck2,
  RefreshCw,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { MandateLockup } from '@/components/brand/MandateLockup';
import { SellerChip } from '@/components/v2/SellerMark';
import { rupees } from '@/lib/money';
import { API_BASE } from '@/lib/api';
import { sellerName } from '@/lib/plain';
import { PARTS } from '@/data/policy';

interface ApprovalItem {
  sku: string;
  qty: number;
  unit_price: number;
  title: string;
  quote?: string | null;
}

interface PendingApproval {
  ref: string;
  amount: number;
  threshold: number;
  merchant: string;
  items: ApprovalItem[];
  status: 'pending' | 'approved' | 'rejected' | 'expired';
  created_at: string;
  expires_at: string;
}

const EASE = [0.22, 0.61, 0.36, 1] as const;

/** Read off the signed policy, never typed. The first draft of this page said
 *  Rs 1,000 against a mandate that says Rs 15,000. */
const AFA_PART = PARTS.find((p) => p.key === 'afa.required');

/** The principal's credential, which is deliberately not the agent's token.
 *
 * A phone that scanned a QR arrives at /approve/<ref> and needs none of this: the
 * ref is the credential for that one order. This is only for the queue view, which
 * lists every held order and so must prove who is asking. It is read from the URL
 * fragment first -- a fragment is never sent to the server and never reaches an
 * access log -- and otherwise from the console session in this same browser.
 */
function principalKey(): string | null {
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const fromLink = hash.get('key');
  if (fromLink) return fromLink;
  try {
    return sessionStorage.getItem('mandate_principal_key');
  } catch {
    return null;
  }
}

export default function Approve() {
  const { ref: paramRef } = useParams<{ ref?: string }>();
  const navigate = useNavigate();

  const [activeRef, setActiveRef] = useState<string | null>(paramRef ?? null);
  const [approval, setApproval] = useState<PendingApproval | null>(null);
  const [pendingList, setPendingList] = useState<PendingApproval[]>([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [actionResult, setActionResult] = useState<'approved' | 'rejected' | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [showQrModal, setShowQrModal] = useState(false);
  const [copied, setCopied] = useState(false);
  const [noPrincipal, setNoPrincipal] = useState(false);

  useEffect(() => {
    if (paramRef) {
      setActiveRef(paramRef);
    }
  }, [paramRef]);

  // Fetch pending list when no specific ref is active
  const fetchPendingList = useCallback(async () => {
    try {
      setLoading(true);
      const key = principalKey();
      if (!key) {
        setNoPrincipal(true);
        setPendingList([]);
        return;
      }
      const res = await fetch(`${API_BASE}/v1/pending`, {
        headers: { 'X-Principal-Key': key },
      });
      if (res.status === 401) {
        setNoPrincipal(true);
        setPendingList([]);
        return;
      }
      if (res.ok) {
        setNoPrincipal(false);
        const data = await res.json();
        const list = (data.pending as PendingApproval[]) ?? [];
        setPendingList(list);
        if (!paramRef && list.length > 0) {
          setActiveRef(list[0].ref);
        }
      }
    } catch {
      setPendingList([]);
    } finally {
      setLoading(false);
    }
  }, [paramRef]);

  // Fetch specific approval details
  const fetchApprovalDetails = useCallback(async (refToFetch: string) => {
    try {
      setLoading(true);
      setErrorMessage(null);
      const res = await fetch(`${API_BASE}/v1/approve/${refToFetch}`);
      if (res.ok) {
        const data = await res.json();
        setApproval(data as PendingApproval);
        if (data.status === 'approved' || data.status === 'rejected') {
          setActionResult(data.status);
        }
      } else if (res.status === 404) {
        setErrorMessage('Approval request not found or expired.');
        setApproval(null);
      } else {
        setErrorMessage('Failed to load approval request.');
        setApproval(null);
      }
    } catch {
      setErrorMessage('Network error while fetching approval request.');
      setApproval(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (activeRef) {
      fetchApprovalDetails(activeRef);
    } else {
      fetchPendingList();
    }
  }, [activeRef, fetchApprovalDetails, fetchPendingList]);

  const handleDecision = async (decision: 'approve' | 'reject') => {
    if (!activeRef) return;
    setSubmitting(true);
    setErrorMessage(null);
    try {
      const res = await fetch(`${API_BASE}/v1/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ref: activeRef, decision }),
      });

      if (res.ok) {
        const resStatus = decision === 'approve' ? 'approved' : 'rejected';
        setActionResult(resStatus);
        if (approval) {
          setApproval({ ...approval, status: resStatus });
        }
      } else if (res.status === 409) {
        const err = await res.json();
        setErrorMessage(err.message || 'Approval was already resolved.');
      } else {
        const err = await res.json();
        setErrorMessage(err.message || 'Failed to submit decision.');
      }
    } catch {
      setErrorMessage('Network failure while submitting decision.');
    } finally {
      setSubmitting(false);
    }
  };

  const copyUrl = () => {
    navigator.clipboard.writeText(window.location.href);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const currentUrl = typeof window !== 'undefined' ? window.location.href : '';

  return (
    <div data-v2 className="min-h-screen bg-bond font-sans text-ink">
      {/* Top Navigation */}
      <nav className="sticky top-0 z-50 border-b border-rule bg-bond/85 backdrop-blur-[12px]">
        <div className="mx-auto flex h-[60px] max-w-[1100px] items-center gap-[26px] px-8 max-sm:px-[18px]">
          <Link to="/" aria-label="Mandate, by Razorpay">
            <MandateLockup />
          </Link>
          <span className="hidden text-[13.5px] text-ink-2 sm:inline">
            Out-of-band Human AFA
          </span>

          <div className="ml-auto flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowQrModal(true)}
              className="h-[38px] rounded-lg px-3 text-[13px] gap-1.5"
            >
              <Smartphone className="size-4 text-[#2F5EFF]" />
              <span className="hidden sm:inline">Phone View</span>
            </Button>
            <Button
              asChild
              variant="outline"
              size="sm"
              className="h-[38px] rounded-lg px-3.5 text-[13px]"
            >
              <Link to="/store">Store</Link>
            </Button>
            <Button
              asChild
              size="sm"
              className="h-[38px] rounded-lg bg-[#2F5EFF] hover:bg-[#254ED0] text-white px-4 text-[13.5px]"
            >
              <Link to="/try">Console</Link>
            </Button>
          </div>
        </div>
      </nav>

      {/* Main Content Area */}
      <main className="mx-auto max-w-[1100px] px-4 py-8 sm:py-12">
        <div className="mx-auto max-w-[460px]">
          {/* Breadcrumb / Status Header */}
          <div className="mb-4 flex items-center justify-between text-[12.5px] text-ink-3">
            <button
              onClick={() => {
                setActiveRef(null);
                setApproval(null);
                setActionResult(null);
                navigate('/approve');
                fetchPendingList();
              }}
              className="inline-flex items-center gap-1.5 transition-colors hover:text-ink"
            >
              <ArrowLeft className="size-3.5" />
              All pending requests
            </button>
            <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-ink-4">
              <Shield className="size-3 text-emerald-600" />
              UPI AFA Clause 2.1
            </span>
          </div>

          {/* Loading State */}
          {loading && (
            <div className="flex flex-col items-center justify-center rounded-panel border border-rule bg-raise p-12 text-center shadow-sheet">
              <RefreshCw className="size-8 animate-spin text-[#2F5EFF]" />
              <p className="mt-4 text-[14px] text-ink-2">Verifying cryptographic intent...</p>
            </div>
          )}

          {/* Error / Not Found State */}
          {!loading && errorMessage && !approval && (
            <div className="rounded-panel border border-halt-line bg-halt-soft p-8 text-center shadow-sheet">
              <XCircle className="mx-auto size-10 text-halt" />
              <h2 className="mt-3 text-[17px] font-medium text-ink">Request Not Available</h2>
              <p className="mt-2 text-[13.5px] text-ink-2">{errorMessage}</p>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  setActiveRef(null);
                  fetchPendingList();
                }}
                className="mt-5 rounded-lg text-[13px]"
              >
                View active approvals
              </Button>
            </div>
          )}

          {/* Empty Pending List State */}
          {/* Without a principal key this page cannot see the queue, which is not
              the same as the queue being empty. Saying "nothing is pending" here
              would be answering a question the page could not answer -- the shape
              that hid two outages in this project already. */}
          {!loading && !activeRef && noPrincipal && (
            <div className="rounded-panel border border-rule bg-raise p-8 text-center shadow-sheet">
              <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-refer-soft text-refer">
                <Shield className="size-6" />
              </div>
              <h2 className="mt-4 text-[18px] font-medium tracking-[-0.015em] text-ink">
                This is the approval channel
              </h2>
              <p className="mx-auto mt-2 max-w-[38ch] text-[13.5px] leading-[1.55] text-ink-2">
                It opens with your own key, not the agent's. That separation is the point:
                the agent can ask, and only you can say yes.
              </p>
              <p className="mx-auto mt-3 max-w-[38ch] text-[13px] leading-[1.55] text-ink-3">
                Scan the code shown beside a held order, or open this page from the console
                that started the session.
              </p>
              <Button
                asChild
                size="sm"
                className="mt-6 h-[40px] w-full rounded-lg bg-[#2F5EFF] text-white hover:bg-[#254ED0]"
              >
                <Link to="/try">Open the console →</Link>
              </Button>
            </div>
          )}

          {!loading && !activeRef && !noPrincipal && pendingList.length === 0 && (
            <div className="rounded-panel border border-rule bg-raise p-8 text-center shadow-sheet">
              <div className="mx-auto flex size-12 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-600">
                <ShieldCheck className="size-6" />
              </div>
              <h2 className="mt-4 text-[18px] font-medium tracking-[-0.015em] text-ink">
                No Pending Approvals
              </h2>
              <p className="mx-auto mt-2 max-w-[34ch] text-[13.5px] leading-[1.55] text-ink-2">
                All autonomous agent transactions are within limits. When an agent proposes an order
                exceeding your policy limit, an out-of-band approval prompt appears here.
              </p>
              <div className="mt-6 rounded-lg border border-rule bg-sheet p-4 text-left text-[12.5px]">
                <div className="flex items-center gap-2 font-medium text-ink">
                  <Clock className="size-3.5 text-[#2F5EFF]" />
                  AFA Policy Threshold
                </div>
                <p className="mt-1 text-ink-3">
                  Orders above {AFA_PART?.bound ?? 'the signed threshold'} need you to say yes
                  before any money moves.
                </p>
              </div>
              <Button
                asChild
                size="sm"
                className="mt-6 h-[40px] w-full rounded-lg bg-[#2F5EFF] text-white hover:bg-[#254ED0]"
              >
                <Link to="/try">Test an over-threshold order in Console →</Link>
              </Button>
            </div>
          )}

          {/* Multiple Pending List Selector */}
          {!loading && !activeRef && pendingList.length > 0 && (
            <div className="space-y-3">
              <h2 className="text-[15px] font-medium text-ink">
                Pending Approvals ({pendingList.length})
              </h2>
              {pendingList.map((item) => (
                <div
                  key={item.ref}
                  onClick={() => {
                    setActiveRef(item.ref);
                    navigate(`/approve/${item.ref}`);
                  }}
                  className="group flex cursor-pointer items-center justify-between rounded-panel border border-rule bg-raise p-4 transition-all hover:border-[#2F5EFF] hover:shadow-sheet"
                >
                  <div className="flex items-center gap-3">
                    <SellerChip name={sellerName(item.merchant)} />
                    <div>
                      <div className="font-mono text-[14px] font-medium text-ink">
                        {rupees(item.amount)}
                      </div>
                      <div className="text-[12px] text-ink-3">
                        {item.items.length} item{item.items.length === 1 ? '' : 's'}
                      </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 text-[12.5px] font-medium text-[#2F5EFF]">
                    Review
                    <ExternalLink className="size-3.5 transition-transform group-hover:translate-x-0.5" />
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Single Approval Phone Card View */}
          {!loading && approval && (
            <motion.div
              initial={{ opacity: 0, scale: 0.98, y: 6 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              transition={{ duration: 0.25, ease: EASE }}
              className="relative overflow-hidden rounded-panel border border-rule bg-raise shadow-sheet"
            >
              {/* Card Header */}
              <div className="border-b border-hair bg-sheet px-6 py-4">
                <div className="flex items-center justify-between">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/20 bg-amber-500/10 px-2.5 py-0.5 text-[11.5px] font-medium text-amber-700 dark:text-amber-400">
                    <AlertTriangle className="size-3.5" />
                    Additional Factor of Authentication
                  </span>
                  <button
                    onClick={() => setShowQrModal(true)}
                    className="inline-flex items-center gap-1 text-[11.5px] text-ink-3 hover:text-ink"
                    title="Open on phone"
                  >
                    <QrCode className="size-3.5" />
                    <span className="hidden sm:inline">Phone</span>
                  </button>
                </div>
              </div>

              {/* Amount & Merchant Hero */}
              <div className="px-6 pt-6 pb-5 text-center">
                <div className="inline-flex justify-center mb-3">
                  <SellerChip name={sellerName(approval.merchant)} />
                </div>
                <div className="font-mono text-[34px] font-semibold tracking-tight text-ink">
                  {rupees(approval.amount)}
                </div>
                <p className="mt-1.5 text-[12.5px] text-ink-2">
                  Exceeds your policy limit of{' '}
                  <span className="font-medium text-ink">{rupees(approval.threshold)}</span>
                </p>
                <div className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-slate-100 px-3 py-1 font-mono text-[10.5px] text-ink-3 dark:bg-slate-800">
                  <span>Intent Ref:</span>
                  <span className="font-semibold text-ink-2" title={approval.ref}>
                    {approval.ref.slice(0, 10)}...{approval.ref.slice(-6)}
                  </span>
                </div>
              </div>

              {/* Itemized Order Breakdown */}
              <div className="border-t border-hair px-6 py-4">
                <div className="mb-2.5 flex items-center justify-between text-[11.5px] font-medium uppercase tracking-wider text-ink-3">
                  <span>Order Items</span>
                  <span>Amount</span>
                </div>
                <ul className="divide-y divide-hair">
                  {approval.items.map((item) => (
                    <li key={item.sku} className="flex items-center justify-between py-2.5">
                      <div className="pr-3">
                        <div className="flex items-center gap-1.5 text-[13px] font-medium text-ink">
                          <span>{item.qty}&times;</span>
                          <span>{item.title}</span>
                          {item.quote && (
                            <span
                              className="inline-flex items-center gap-0.5 rounded border border-purple-500/30 bg-purple-500/10 px-1 py-0.2 text-[9.5px] font-medium text-purple-700 dark:text-purple-300"
                              title="Merchant-signed dynamic price quote"
                            >
                              <FileCheck2 className="size-2.5" />
                              Quote
                            </span>
                          )}
                        </div>
                        <div className="text-[11.5px] text-ink-3">
                          {rupees(item.unit_price)} each
                        </div>
                      </div>
                      <div className="font-mono text-[13px] font-medium text-ink">
                        {rupees(item.unit_price * item.qty)}
                      </div>
                    </li>
                  ))}
                </ul>
              </div>

              {/* Resolved / Completed Feedback */}
              <AnimatePresence>
                {actionResult && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="border-t border-hair p-6"
                  >
                    {actionResult === 'approved' ? (
                      <div className="rounded-panel border border-emerald-500/30 bg-emerald-500/10 p-4 text-center">
                        <CheckCircle2 className="mx-auto size-9 text-emerald-600" />
                        <h3 className="mt-2 text-[15px] font-medium text-ink">Order Approved</h3>
                        <p className="mt-1 text-[12.5px] text-ink-2">
                          Single-use authorization granted. The shopping agent has been cleared to
                          execute on Razorpay.
                        </p>
                      </div>
                    ) : (
                      <div className="rounded-panel border border-rose-500/30 bg-rose-500/10 p-4 text-center">
                        <XCircle className="mx-auto size-9 text-rose-600" />
                        <h3 className="mt-2 text-[15px] font-medium text-ink">Order Rejected</h3>
                        <p className="mt-1 text-[12.5px] text-ink-2">
                          Proposal declined. The payment attempt was terminated and no funds were
                          debited.
                        </p>
                      </div>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Error Notice */}
              {errorMessage && (
                <div className="border-t border-halt-line bg-halt-soft px-6 py-3 text-center text-[12.5px] text-halt">
                  {errorMessage}
                </div>
              )}

              {/* Action Buttons (only visible if still pending) */}
              {!actionResult && approval.status === 'pending' && (
                <div className="border-t border-hair bg-sheet p-6 space-y-2.5">
                  <Button
                    onClick={() => handleDecision('approve')}
                    disabled={submitting}
                    className="h-[46px] w-full rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-[14px] shadow-sm flex items-center justify-center gap-2"
                  >
                    {submitting ? (
                      <RefreshCw className="size-4 animate-spin" />
                    ) : (
                      <>
                        <Check className="size-4" />
                        Authorize {rupees(approval.amount)}
                      </>
                    )}
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => handleDecision('reject')}
                    disabled={submitting}
                    className="h-[42px] w-full rounded-lg border-rose-200 text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:border-rose-900/40 dark:hover:bg-rose-950/20 text-[13.5px] flex items-center justify-center gap-1.5"
                  >
                    <XCircle className="size-4" />
                    Reject Order
                  </Button>
                  <p className="text-center text-[11px] text-ink-4">
                    Direct cryptographic approval. The agent never receives this URL token.
                  </p>
                </div>
              )}
            </motion.div>
          )}
        </div>
      </main>

      {/* QR Code Modal for Phone Testing */}
      {showQrModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-xs">
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className="w-full max-w-[340px] rounded-panel border border-rule bg-raise p-6 text-center shadow-2xl"
          >
            <div className="flex items-center justify-between pb-3 border-b border-hair">
              <span className="text-[14px] font-medium text-ink flex items-center gap-1.5">
                <Smartphone className="size-4 text-[#2F5EFF]" />
                Scan to Approve on Phone
              </span>
              <button
                onClick={() => setShowQrModal(false)}
                className="rounded-md p-1 text-ink-3 hover:text-ink"
              >
                &times;
              </button>
            </div>
            <div className="my-5 flex justify-center rounded-lg bg-white p-4 shadow-inner">
              <QRCodeSVG value={currentUrl} size={180} level="M" />
            </div>
            <p className="text-[12px] text-ink-2">
              Scan with your mobile camera to test the authentic one-tap AFA approval experience.
            </p>
            <div className="mt-4 flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={copyUrl}
                className="w-full text-[12.5px] gap-1.5"
              >
                {copied ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
                {copied ? 'Copied' : 'Copy link'}
              </Button>
              <Button
                size="sm"
                onClick={() => setShowQrModal(false)}
                className="w-full bg-[#2F5EFF] text-white hover:bg-[#254ED0] text-[12.5px]"
              >
                Done
              </Button>
            </div>
          </motion.div>
        </div>
      )}
    </div>
  );
}
