/**
 * Where the gateway API lives, decided once.
 *
 * The app is a single-origin SPA: `mandate serve --static-dir web/dist` serves
 * the bundle and the `/v1/*` endpoints from the same process, so in every
 * deployed configuration the right base is the empty string. Only the Vite dev
 * server is a different origin, because it serves the bundle on :5173 while the
 * daemon runs on :8000.
 *
 * This used to be decided by sniffing `window.location`, copied into three
 * components:
 *
 *     port === '8000' || port === '8811' || hostname.includes('run.app')
 *       ? '' : import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'
 *
 * That enumerates the hosts it knows about and sends every other host to the
 * visitor's own laptop. It was correct on `*.run.app` and on localhost:8000 and
 * silently wrong the moment a custom domain was put in front of Cloud Run:
 * `mandate.namankhandelwal.dev` matched no branch, so the judge console posted
 * `/v1/sessions` to `http://127.0.0.1:8000` on the judge's machine and every
 * call failed. The page rendered perfectly, which is why it went unnoticed.
 *
 * `import.meta.env.DEV` is the honest signal — it is true exactly when Vite is
 * serving, is fixed at build time, and knows nothing about hostnames. A build
 * can still be pointed anywhere with `VITE_API_URL`.
 */
export const API_BASE: string =
  import.meta.env.VITE_API_URL || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '');
