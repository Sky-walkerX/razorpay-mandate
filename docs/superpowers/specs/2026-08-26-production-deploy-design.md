# Production deployment layer: dashboard + Azure

Date: 2026-08-26
Status: approved, not yet implemented

## Context

`SPEC.md` and `README.md` define Mandate's core: a policy compiler, a deterministic enforcement
gateway, a hash-chained audit log, and an evaluation harness that scores containment against a seeded
attack corpus. `SPEC.md` section 6 ("Build order") schedules that core across 15 days and treats the
compiler read-back UI as the first thing to cut if time runs short. It budgets zero days for a web
frontend, an API server, or any deployment.

This spec adds that layer on top, without changing the core build order or the core's design decisions
(fail-closed rules, model compiles once then never votes again, baseline vs. enforce arm, held-out attack
families). It exists because the buildathon deliverable benefits from a live, deployed demo rather than a
local-only CLI walkthrough, and because a clean production layer is itself part of what an
architecture-focused panel evaluates.

Timeline note: all core-work commits are dated 2026-08-21 (day 1 of the original plan). Today is
2026-08-26, five calendar days later, with no further commits — so of the original 15 working days, 10
remain before the 2026-09-05 deadline. The sequencing below assumes the remaining core days (SPEC.md's
days 2-13, i.e. roughly 12 remaining working days of core content) compress into the 10 calendar days
available, with the deploy layer (days 14-17 below) appended immediately after. This is tight by design;
the user has confirmed willingness to put in the time rather than cut scope.

## Non-goals

- Not a general-purpose SaaS. Single demo deployment, single Azure Container App replica, no
  multi-tenancy, no autoscaling policy beyond Container Apps' own scale-to-zero default.
- Not a rewrite of the core `mandate` package. The API layer wraps it; no enforcement logic moves into
  the API or frontend.
- Not a from-scratch design system. The dashboard uses whatever component approach is fastest to build
  cleanly (plain CSS or a lightweight utility framework); visual polish is secondary to correctness and
  legibility on a projector.

## Architecture

```
┌─────────────────┐      ┌──────────────────────────────┐
│  React + Vite    │◄────►│  FastAPI                     │
│  demo dashboard  │ REST/│  - POST /compile              │
│  (static build,  │  WS  │  - POST /gateway/evaluate     │
│  served by       │      │  - GET  /audit (stream)       │
│  FastAPI)        │      │  - POST /harness/run          │
└─────────────────┘      │  - GET  /harness/results       │
                          │  wraps the existing            │
                          │  `mandate` package as a library│
                          └───────┬───────────────────────┘
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
              Anthropic API  Razorpay MCP   Supabase Postgres
              (compiler)     (test mode)    (policies, audit log,
                                              harness results)
```

One Docker image. Multi-stage build: stage 1 builds the React static bundle, stage 2 is the Python
runtime that serves both the API and the built frontend assets. One Azure Container App, one replica
(the audit log is single-writer; running multiple replicas against the same Postgres without a
coordination layer would let two replicas race on the hash chain, which is exactly the class of bug the
project is supposed to catch elsewhere — so it doesn't get introduced here).

## Components

**FastAPI layer** (`src/mandate/api/`, new)
- Thin route handlers only. Each route calls into the existing `mandate` package (compiler, gateway,
  harness) and returns Pydantic response models built from the package's existing domain models where
  possible, rather than redefining shapes.
- `POST /compile`: natural-language intent in, compiled policy + read-back text out. Does not persist
  until the human-review step confirms.
- `POST /gateway/evaluate`: a proposed money action in, a verdict (ALLOW / DENY + clause / ESCALATE)
  out. Writes to the audit log regardless of verdict.
- `GET /audit`: server-sent events or WebSocket stream of audit log entries, for the dashboard's live
  view during the demo.
- `POST /harness/run`, `GET /harness/results`: kicks off a harness run against the seeded corpus,
  returns the scored results (containment rate, false-block rate, confidence intervals) once complete.

**Persistence** (Supabase Postgres, free tier)
- Three tables: `policies` (compiled policy + hash + signature status), `audit_log` (hash-chained
  entries — this is the append-only log the core design already specifies, just given a durable home
  instead of an in-process structure), `harness_results` (one row per scored run, so the dashboard can
  show historical runs, not just the latest).
- The core package's hash-chaining logic doesn't change; only its persistence target does (Postgres
  instead of an in-memory list or local file), via a small repository/storage interface in
  `src/mandate/api/storage.py` so the core `mandate` package stays storage-agnostic.

**Frontend** (`frontend/`, new, React + Vite)
- Demo view: split-screen layout mirroring the pitch's demo moment — one pane runs a clean agent
  session, the other runs the same session against an attacked catalog. Verdicts and denial clauses
  render live as the gateway emits them.
- Audit log view: scrolling, hash-chain-verified log of every evaluated action.
- Results view: containment rate and false-block rate, both arms, with confidence intervals, pulled from
  `/harness/results`.
- No auth, no user accounts — this is a demo artifact, not a multi-user product. If a login screen is
  ever warranted, that's a separate spec.

**Deployment**
- `Dockerfile` at the repo root (multi-stage, described above).
- Azure Container App, one revision, one replica, scale-to-zero when idle to conserve the $100 credit.
- Secrets (`ANTHROPIC_API_KEY`, `RAZORPAY_KEY_ID`/`SECRET`, Supabase connection string) set as Container
  App secrets, never committed. `.env.example` stays the local-dev reference; `.env` stays gitignored
  (already true today).
- GitHub Actions workflow (or manual `az containerapp up` — decide at implementation time based on
  remaining days) builds the image and deploys on push to `main`.

## Data flow

1. User states intent in the dashboard → `POST /compile` → compiler runs once (Anthropic API, temp 0) →
   read-back text returned → user confirms in the UI → policy persisted to `policies` with its hash.
2. Agent (simulated for the demo, or a real MCP-driven agent) proposes a money action → `POST
   /gateway/evaluate` → deterministic evaluation against the signed policy in pure code (no model call)
   → verdict returned, audit entry written to `audit_log`, dashboard's live view updates via the
   `/audit` stream.
3. Harness run: `POST /harness/run` replays the seeded corpus (attack + legitimate) through both the
   baseline (observe-only) and enforce arms, scores each, writes one row to `harness_results` per arm
   per run, dashboard's results view reads the latest (or a selected historical) run.

## Error handling

- Gateway evaluation errors (e.g. Anthropic API timeout during compile, Razorpay MCP unreachable) surface
  as a distinct verdict state, not a 500 — the existing "rules fail closed" principle extends to
  infrastructure failure: if the gateway cannot evaluate, it denies, the same as if a clause were
  violated, and the audit log records *why* (infra failure vs. clause violation) so the two are never
  confused when reading results.
- Supabase connection failures: the API returns 503 with a clear message; the dashboard shows a
  visible "audit log unavailable" state rather than silently showing stale data.
- Frontend: no action is presented as having succeeded until the corresponding API call actually
  returns a verdict; no optimistic UI for anything that touches money or policy state.

## Testing

- API layer gets its own `tests/api/` using FastAPI's `TestClient`, hitting the routes with the fake
  downstream (`mandate.downstream.fake`) already in the package — no live Razorpay/Anthropic calls in
  CI.
- Storage layer (`storage.py`) gets tests against a local Postgres (Docker) in CI, not against the live
  Supabase project, so tests don't depend on network or burn Supabase's free-tier limits.
- Frontend gets minimal smoke coverage: the demo view renders and reflects a mocked verdict stream. Deep
  component testing is out of scope given the timeline — the harness's own scoring correctness is the
  test surface that actually matters for this project's argument.
- Docker image gets a healthcheck endpoint (`GET /health`) that checks Supabase connectivity, used both
  by Container Apps' own health probing and by a manual post-deploy smoke check.

## Sequencing

`SPEC.md`'s existing days 1-13 (core: catalog, evaluator, idempotency, compiler, scoring) are unchanged
by this spec. Appended after:

| Day | Work |
|---|---|
| 14 | FastAPI wrapper: `/compile`, `/gateway/evaluate`, `/audit`, `/harness/run` — wraps existing package, no new logic |
| 15 | React/Vite dashboard: split-screen demo view, live audit log, results view |
| 16 | Dockerize (multi-stage), Supabase project + schema, wire persistence via `storage.py` |
| 17 | Azure Container App deploy, secrets configuration, end-to-end smoke test on the deployed instance |
| 18 | Demo video recorded against the deployed version, architecture doc |
| 19-20 | Buffer |

## Open questions

- **GitHub Actions vs. manual deploy.** Decide once day 17 arrives based on actual days remaining;
  manual `az containerapp up` is strictly simpler and acceptable for a single-environment demo deploy.
- **Component library for the frontend.** Left unspecified deliberately — pick the fastest clean option
  when day 15 starts, not now, since it doesn't affect any decision upstream of it.
