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

/**
 * Verify an inclusion proof against an expected root, per RFC 6962 section 2.1.1.
 *
 * Mirrors `verify_inclusion_proof` in merkle.py line for line, including that the
 * `dir` field on each proof node is ignored.
 */
export async function verifyInclusionProof(
  leafRecord: string,
  index: number,
  treeSize: number,
  proof: ProofNode[],
  expectedRoot: string,
): Promise<boolean> {
  if (index < 0 || treeSize <= 0 || index >= treeSize) return false;

  let fn = index;
  let sn = treeSize - 1;
  let current = await leafHash(leafRecord);

  for (const sibling of proof.map((p) => p.node)) {
    if (sn === 0) return false; // proof longer than the tree is deep
    if (fn % 2 === 1 || fn === sn) {
      current = await nodeHash(sibling, current);
      while (fn !== 0 && fn % 2 === 0) {
        fn = Math.floor(fn / 2);
        sn = Math.floor(sn / 2);
      }
    } else {
      current = await nodeHash(current, sibling);
    }
    fn = Math.floor(fn / 2);
    sn = Math.floor(sn / 2);
  }

  return sn === 0 && current === expectedRoot;
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
