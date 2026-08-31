import evidence from '@/data/evidence.json';

/**
 * Hands the reader the exact file this page was rendered from.
 *
 * "Export evidence" sat on the old topbar as a button that did nothing. A
 * console whose argument is that every figure is traceable should not have an
 * inert control named after the tracing — so it now downloads `evidence.json`
 * itself, which `mandate evidence` writes from the signed policy and the
 * scored result directories. What the reader gets is what the page read.
 */
export function exportEvidence(): void {
  const blob = new Blob([JSON.stringify(evidence, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'mandate-evidence.json';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
