import evidence from './evidence.json';

/**
 * The gateway log's Ed25519 public key, pinned at build time.
 *
 * `mandate evidence` reads this from `.mandate/keys/log_public.key` and writes it
 * into `evidence.json`, so the browser ships with it and never asks for it.
 *
 * That is the whole point of the receipt verifier. Fetching the key from the same
 * service that produced the signature would be checking a signature against a key
 * the signer chose, which verifies nothing. Pinning means a deployment signing with
 * a different key fails visibly here rather than passing quietly, and that is the
 * correct outcome, not a bug to work around.
 *
 * Null when the repo held no log keypair at build time. The verifier then says it
 * cannot check the head, rather than showing a tick it did not earn.
 */
export const LOG_PUBLIC_KEY: string | null = evidence.log?.public_key ?? null;
