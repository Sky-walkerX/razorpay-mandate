/**
 * RFC 6962 verification, in the browser, against a root the page computes itself.
 *
 * A port of `src/mandate/gateway/merkle.py`. The point of doing it here rather than
 * asking the service is that an endpoint answering "is this proof valid?" would be
 * the gateway vouching for itself. The page takes the proof and the signed head from
 * the service and checks both against a public key it was built with.
 *
 * Direction at each level comes from `index` and `treeSize`, never from the `dir`
 * field carried in the proof. A verifier that reads its own instructions out of the
 * document it is checking is not verifying anything.
 */
import { verifyAsync } from '@noble/ed25519';

import { pythonJsonDumps } from './canonical.ts';

const PREFIX = 'sha256:';

function hexToBytes(hex: string): Uint8Array {
  const clean = hex.startsWith(PREFIX) ? hex.slice(PREFIX.length) : hex;
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < out.length; i += 1) {
    out[i] = Number.parseInt(clean.substr(i * 2, 2), 16);
  }
  return out;
}

function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}

async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', bytes as unknown as BufferSource);
  return PREFIX + bytesToHex(new Uint8Array(digest));
}

function concat(...parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((n, p) => n + p.length, 0);
  const out = new Uint8Array(total);
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}

/** RFC 6962 leaf hash: sha256(0x00 || entry). */
export async function leafHash(record: string): Promise<string> {
  const payload = record.startsWith(PREFIX)
    ? hexToBytes(record)
    : new TextEncoder().encode(record);
  return sha256(concat(new Uint8Array([0x00]), payload));
}

/** RFC 6962 interior node: sha256(0x01 || left || right). */
export async function nodeHash(left: string, right: string): Promise<string> {
  return sha256(concat(new Uint8Array([0x01]), hexToBytes(left), hexToBytes(right)));
}

export interface ProofNode {
  node: string;
  dir?: string;
}

export interface ClimbStep {
  /** The sibling hash this level was combined with. */
  sibling: string;
  /** Whether the sibling sat to the left or the right, derived from index and size. */
  side: 'left' | 'right';
  /** The running hash after this level. */
  result: string;
}

export interface Climb {
  steps: ClimbStep[];
  /** The hash the walk arrived at. Compare it against the signed root. */
  root: string;
  /** False when the proof was longer than the tree is deep, or the walk did not finish. */
  complete: boolean;
}

/**
 * Walk a leaf up to a root, per RFC 6962 section 2.1.1, recording each level.
 *
 * This is the single implementation. `verifyInclusionProof` is a thin comparison on
 * top of it, and the interface renders the same steps, so a page cannot show one
 * walk while the verifier performs another. Two copies of this loop is precisely the
 * shape of drift that has bitten this codebase before.
 *
 * The `dir` field carried in each proof node is deliberately not read.
 */
export async function climbToRoot(
  leafRecord: string,
  index: number,
  treeSize: number,
  proof: ProofNode[],
): Promise<Climb> {
  const steps: ClimbStep[] = [];
  let fn = index;
  let sn = treeSize - 1;
  let current = await leafHash(leafRecord);

  for (const { node: sibling } of proof) {
    if (sn === 0) return { steps, root: current, complete: false };
    let side: 'left' | 'right';
    if (fn % 2 === 1 || fn === sn) {
      current = await nodeHash(sibling, current);
      side = 'left';
      while (fn !== 0 && fn % 2 === 0) {
        fn = Math.floor(fn / 2);
        sn = Math.floor(sn / 2);
      }
    } else {
      current = await nodeHash(current, sibling);
      side = 'right';
    }
    fn = Math.floor(fn / 2);
    sn = Math.floor(sn / 2);
    steps.push({ sibling, side, result: current });
  }

  return { steps, root: current, complete: sn === 0 };
}

/** Verify an inclusion proof against an expected root. */
export async function verifyInclusionProof(
  leafRecord: string,
  index: number,
  treeSize: number,
  proof: ProofNode[],
  expectedRoot: string,
): Promise<boolean> {
  if (index < 0 || treeSize <= 0 || index >= treeSize) return false;
  const climb = await climbToRoot(leafRecord, index, treeSize, proof);
  return climb.complete && climb.root === expectedRoot;
}

/**
 * Recompute a record's own hash the way `AuditLog._hash_body` did.
 *
 * This is what makes tampering visible: edit a rupee in the record and the leaf no
 * longer hashes to the value the proof was built for, so the path stops reaching the
 * root. `record_hash` is excluded because the hash cannot cover itself.
 */
export async function recordHash(record: Record<string, unknown>): Promise<string> {
  const body: Record<string, unknown> = { ...record };
  delete body.record_hash;
  return sha256(new TextEncoder().encode(pythonJsonDumps(body)));
}

/**
 * Verify the log's signed tree head against a public key the page was built with.
 *
 * The signed message is `f"{size}:{root}:{ts}"` (server.py), signed by a key
 * deliberately distinct from the issuer's so the issuer key can stay offline.
 *
 * `publicKeyHex` must come from `evidence.json`, which `mandate evidence` fills from
 * the key file at build time. Fetching it from the service that produced the
 * signature would be checking a signature against a key the signer chose, which is
 * not a check at all. A production key that differs from the built-in one fails
 * here, loudly, which is the correct outcome.
 */
export async function verifyTreeHead(
  head: { size: number; root: string; ts: string; sig: string },
  publicKeyHex: string,
): Promise<boolean> {
  const message = new TextEncoder().encode(`${head.size}:${head.root}:${head.ts}`);
  try {
    return await verifyAsync(hexToBytes(head.sig), message, hexToBytes(publicKeyHex));
  } catch {
    return false;
  }
}

/**
 * Verify that a log of `secondSize` is an append-only extension of one of
 * `firstSize`, per RFC 6962 section 2.1.2.
 *
 * A different claim from inclusion, and the stronger one. An inclusion proof says
 * a receipt is in the log *now*, which a log that quietly rewrote itself could
 * still satisfy. Only this says nothing was dropped or reordered since a head
 * somebody already wrote down. It is the reason holding an old head is worth
 * anything at all.
 *
 * A port of `verify_consistency_proof` in merkle.py, including that a `firstSize`
 * which is a power of two omits its own root from the proof because the verifier
 * can supply it.
 */
export async function verifyConsistencyProof(
  firstSize: number,
  secondSize: number,
  firstRoot: string,
  secondRoot: string,
  proof: ProofNode[],
): Promise<boolean> {
  if (firstSize < 1 || firstSize > secondSize) return false;
  if (firstSize === secondSize) return proof.length === 0 && firstRoot === secondRoot;

  const nodes = proof.map((p) => p.node);
  let fn = firstSize - 1;
  let sn = secondSize - 1;
  while (fn % 2 === 1) {
    fn = Math.floor(fn / 2);
    sn = Math.floor(sn / 2);
  }

  let node: string;
  if (fn !== 0) {
    if (!nodes.length) return false;
    node = nodes.shift()!;
  } else {
    node = firstRoot;
  }

  let fr = node;
  let sr = node;
  while (sn !== 0) {
    if (!nodes.length) return false;
    if (fn % 2 === 1 || fn === sn) {
      const next = nodes.shift()!;
      fr = await nodeHash(next, fr);
      sr = await nodeHash(next, sr);
      while (fn !== 0 && fn % 2 === 0) {
        fn = Math.floor(fn / 2);
        sn = Math.floor(sn / 2);
      }
    } else {
      const next = nodes.shift()!;
      sr = await nodeHash(sr, next);
    }
    fn = Math.floor(fn / 2);
    sn = Math.floor(sn / 2);
  }

  return nodes.length === 0 && fr === firstRoot && sr === secondRoot;
}
