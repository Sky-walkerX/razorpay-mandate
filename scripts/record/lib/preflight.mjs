/**
 * Refuse to record a broken site.
 *
 * This project has twice shipped a page that rendered perfectly while nothing
 * underneath it worked -- the judge console posting to the visitor's own laptop,
 * and /v1/compile answering with the signed policy's clauses because the
 * deployed service had no Vertex permission. Both survived for days precisely
 * because the failure was silent.
 *
 * Five minutes of recording is expensive enough that the same lesson applies:
 * check the plumbing loudly first, and abort rather than record around it.
 */

const ok = (s) => `  \x1b[32mok\x1b[0m    ${s}`;
const bad = (s) => `  \x1b[31mFAIL\x1b[0m  ${s}`;

async function jsonPost(url, body, ms = 45000) {
  const ctl = AbortController ? new AbortController() : null;
  const t = setTimeout(() => ctl?.abort(), ms);
  try {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctl?.signal,
    });
    let j = null;
    try { j = await r.json(); } catch { /* non-JSON body is itself the finding */ }
    return { status: r.status, json: j };
  } finally {
    clearTimeout(t);
  }
}

/**
 * Try twice before believing a model-backed endpoint is down.
 *
 * `--min-instances=1` keeps the container warm, but the first request after a
 * deploy still pays cold start, and both compile endpoints run two
 * temperature-0 readings against a 30s ceiling. Measured warm, /v1/sandbox is
 * 9.7-12.5s; measured cold, it exceeds the ceiling. A single attempt cannot
 * tell those apart, and this check exists to be believed.
 *
 * This is a retry, not a fallback: both attempts are printed, and a second
 * failure still fails.
 */
async function twice(label, attempt) {
  const first = await attempt();
  if (first.pass) return first;
  console.log(`  \x1b[33mwarm\x1b[0m  ${label} failed cold (${first.detail}) — retrying`);
  await new Promise((r) => setTimeout(r, 3000));
  return attempt();
}

export async function preflight(base, { needCalls = 60, requireReservePay = true } = {}) {
  const fails = [];
  const say = (pass, msg) => {
    console.log(pass ? ok(msg) : bad(msg));
    if (!pass) fails.push(msg);
  };

  console.log(`\npreflight against ${base}`);

  // 1. Liveness.
  let health = null;
  try {
    const r = await fetch(`${base}/health`);
    health = await r.json();
    say(r.status === 200, `/health 200 · policy ${String(health.policy_hash).slice(0, 20)}…`);
    say(health.pool_available > 5, `token pool has ${health.pool_available} left`);
  } catch (e) {
    say(false, `/health unreachable: ${e.message}`);
    return { pass: false, fails, health };
  }

  // 2. The bundle. The only way to catch a build-time constant going wrong --
  //    a wrong API base renders a flawless page that calls nobody.
  try {
    const html = await (await fetch(`${base}/`)).text();
    const asset = html.match(/\/assets\/index-[A-Za-z0-9_-]+\.js/)?.[0];
    say(!!asset, `bundle located: ${asset ?? 'NOT FOUND'}`);
    if (asset) {
      const js = await (await fetch(`${base}${asset}`)).text();
      say(!js.includes('127.0.0.1:8000'), 'bundle has no 127.0.0.1:8000');
      say(!js.includes('run.app'), 'bundle has no run.app');
      if (requireReservePay) {
        say(
          js.includes('of your limits fit on the rail'),
          'bundle carries the Reserve Pay shadow strip',
        );
      }
    }
  } catch (e) {
    say(false, `bundle check failed: ${e.message}`);
  }

  // 3. The Vertex canary. This endpoint used to lie about it.
  {
    const r = await twice('/v1/compile', async () => {
      try {
        const { status, json } = await jsonPost(`${base}/v1/compile`, {
          prompt: 'Spend at most Rs 300 on any one order, Rs 800 in total. Nothing alcoholic.',
        });
        const pass = status === 200 && json?.compiled === true && json?.fallback === false;
        const n = json?.constraints?.length;
        return {
          pass,
          detail: pass
            ? `${n} clauses, fallback=false`
            : `status=${status} kind=${json?.kind ?? '-'} ${json?.reason ?? ''}`.trim(),
        };
      } catch (e) {
        return { pass: false, detail: e.message };
      }
    });
    say(r.pass, `/v1/compile · ${r.detail}`);
  }

  // 4. The sandbox pool. It is gitignored and travels in the Docker build
  //    context, so a deploy from the wrong machine silently ships none and
  //    shot 9 has nothing to record.
  {
    const r = await twice('/v1/sandbox', async () => {
      try {
        const t0 = Date.now();
        const { status, json } = await jsonPost(`${base}/v1/sandbox`, {
          prompt: 'Spend at most Rs 300 on any one order, Rs 800 in total. Nothing alcoholic.',
        });
        const secs = ((Date.now() - t0) / 1000).toFixed(1);
        if (status === 503) {
          return {
            pass: false,
            fatal: true,
            detail: 'HTTP 503 — the sandbox pool did NOT ship with this deploy',
          };
        }
        const pass = status === 200 && !!json?.token;
        return {
          pass,
          detail: pass
            ? `token issued in ${secs}s`
            : `status=${status} kind=${json?.kind ?? '-'} ${json?.reason ?? ''} (${secs}s)`.trim(),
        };
      } catch (e) {
        return { pass: false, detail: e.message };
      }
    });
    say(r.pass, `/v1/sandbox · ${r.detail}`);
  }

  // 5. The two static surfaces the shot list ends on.
  for (const p of ['/rails', '/v1/mandate/ap2']) {
    try {
      const r = await fetch(`${base}${p}`);
      say(r.status === 200, `${p} ${r.status}`);
    } catch (e) {
      say(false, `${p} failed: ${e.message}`);
    }
  }

  // 6. The rail. Added 4 Sep, because the two new beats depend on a deployment
  //     holding Razorpay keys, and nothing on the page says whether it does.
  //     `/rails` renders identically either way: the tool counts come from
  //     evidence.json, so only the mandate button fails, and it fails mid-take.
  //     That is the same silent shape as the two failures in this file's header.
  try {
    const j = await (await fetch(`${base}/v1/rail/surface`)).json();
    say(j.mounted === true, `/mcp/razorpay mounted · ${j.total} tools, ${j.destructive} destructive`);
  } catch (e) {
    say(false, `/v1/rail/surface failed: ${e.message}`);
  }

  // Creating one is the only honest check that the keys work, so preflight
  // makes a real test-mode auth link. Every run leaves one behind.
  try {
    const r = await fetch(`${base}/v1/rail/mandate`, { method: 'POST' });
    const j = await r.json();
    say(r.status === 200 && !!j?.link?.short_url,
        `/v1/rail/mandate ${r.status} · ${j?.link?.short_url ?? j?.reason ?? 'no link'}`);
  } catch (e) {
    say(false, `/v1/rail/mandate failed: ${e.message}`);
  }

  // 7. Enough model budget for the take plus one retry.
  try {
    const j = await (await fetch(`${base}/v1/agent/families`)).json();
    say(
      (j.calls_remaining_today ?? 0) >= needCalls,
      `${j.calls_remaining_today}/${j.ceiling} model calls left today (need ≥${needCalls})`,
    );
  } catch (e) {
    say(false, `/v1/agent/families failed: ${e.message}`);
  }

  const pass = fails.length === 0;
  console.log(pass ? '\n  all checks passed\n' : `\n  ${fails.length} check(s) failed — not recording\n`);
  return { pass, fails, health };
}
